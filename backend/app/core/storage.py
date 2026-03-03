from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import uuid4

import boto3

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save_bytes(self, data: bytes, filename: str, subdir: str = '') -> str:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, stored_path: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def local_processing_path(self, stored_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, stored_path: str) -> None:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        configured = Path(settings.uploads_dir)
        candidate = configured if configured.is_absolute() else backend_root / configured
        resolved = candidate.resolve()
        if backend_root.resolve() not in (resolved, *resolved.parents):
            raise ValueError('UPLOADS_DIR must be within backend directory for local storage.')

        self.base_dir = resolved
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_subdir(self, subdir: str) -> Path:
        if not subdir:
            return Path()

        raw = Path(subdir.replace('\\', '/'))
        if raw.is_absolute() or '..' in raw.parts:
            raise ValueError('Invalid upload subdir path.')

        safe_parts: list[str] = []
        for part in raw.parts:
            if part in {'', '.'}:
                continue
            cleaned = ''.join(char for char in part if char.isalnum() or char in {'-', '_'})
            if not cleaned:
                raise ValueError('Invalid upload subdir segment.')
            safe_parts.append(cleaned)
        return Path(*safe_parts) if safe_parts else Path()

    def _resolve_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        candidate = path.resolve() if path.is_absolute() else (self.base_dir / path).resolve()
        if self.base_dir not in (candidate, *candidate.parents):
            raise ValueError('Resolved storage path is outside upload directory.')
        return candidate

    def save_bytes(self, data: bytes, filename: str, subdir: str = '') -> str:
        safe_name = ''.join(char for char in filename if char.isalnum() or char in ('-', '_', '.'))
        if not safe_name:
            safe_name = 'file'
        suffix = Path(safe_name).suffix.lower()
        object_name = f'{uuid4().hex}{suffix}'

        safe_subdir = self._sanitize_subdir(subdir)
        target_dir = self.base_dir / safe_subdir if safe_subdir else self.base_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / object_name
        target_path.write_bytes(data)
        return str(target_path.as_posix())

    def read_bytes(self, stored_path: str) -> bytes:
        return self._resolve_path(stored_path).read_bytes()

    def local_processing_path(self, stored_path: str) -> str:
        return str(self._resolve_path(stored_path).as_posix())

    def delete_file(self, stored_path: str) -> None:
        target = self._resolve_path(stored_path)
        if target.exists():
            target.unlink()


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        if not settings.aws_s3_bucket:
            raise ValueError('AWS_S3_BUCKET must be configured for S3 storage')
        self.bucket = settings.aws_s3_bucket
        self.client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    def save_bytes(self, data: bytes, filename: str, subdir: str = '') -> str:
        safe_name = ''.join(char for char in filename if char.isalnum() or char in ('-', '_', '.'))
        suffix = Path(safe_name).suffix.lower()
        object_name = f"{subdir.strip('/')}/{uuid4().hex}{suffix}" if subdir else f'{uuid4().hex}{suffix}'
        self.client.put_object(Bucket=self.bucket, Key=object_name, Body=data)
        return object_name

    def read_bytes(self, stored_path: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=stored_path)
        return obj['Body'].read()

    def local_processing_path(self, stored_path: str) -> str:
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(self.read_bytes(stored_path))
        temp_file.close()
        return temp_file.name

    def delete_file(self, stored_path: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=stored_path)


_storage_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _storage_instance
    if _storage_instance is None:
        if settings.storage_backend.lower() == 's3':
            _storage_instance = S3Storage()
        else:
            _storage_instance = LocalStorage()
    return _storage_instance


def remove_temp_file(file_path: str) -> None:
    if file_path.startswith(tempfile.gettempdir()) and os.path.exists(file_path):
        os.remove(file_path)
