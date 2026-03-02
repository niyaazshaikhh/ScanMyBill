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
        self.base_dir = Path(settings.uploads_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, data: bytes, filename: str, subdir: str = '') -> str:
        safe_name = ''.join(char for char in filename if char.isalnum() or char in ('-', '_', '.'))
        suffix = Path(safe_name).suffix.lower()
        object_name = f'{uuid4().hex}{suffix}'

        target_dir = self.base_dir / subdir if subdir else self.base_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / object_name
        target_path.write_bytes(data)
        return str(target_path.as_posix())

    def read_bytes(self, stored_path: str) -> bytes:
        return Path(stored_path).read_bytes()

    def local_processing_path(self, stored_path: str) -> str:
        return stored_path

    def delete_file(self, stored_path: str) -> None:
        target = Path(stored_path)
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
