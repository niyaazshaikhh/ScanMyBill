from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

SECRET_KEY = os.getenv('SECRET_KEY', settings.secret_key)
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def get_password_hash(password: str) -> str:
    # Backward-compatible alias used by existing auth code.
    return hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


def _build_token_payload(
    data: dict[str, Any],
    token_type: str,
    expires_delta: timedelta,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    payload = data.copy()
    payload.update(
        {
            'jti': str(uuid4()),
            'type': token_type,
            'iat': now,
            'exp': now + expires_delta,
        }
    )
    return payload


def create_access_token(
    data: dict[str, Any] | None = None,
    *,
    subject: str | None = None,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    payload: dict[str, Any] = dict(data or {})
    if subject:
        payload['sub'] = subject
    if role:
        payload['role'] = role
    if 'sub' not in payload:
        raise ValueError('Access token payload must include "sub"')
    expire_delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = _build_token_payload(payload, token_type='access', expires_delta=expire_delta)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict[str, Any] | None = None,
    *,
    subject: str | None = None,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    payload: dict[str, Any] = dict(data or {})
    if subject:
        payload['sub'] = subject
    if role:
        payload['role'] = role
    if 'sub' not in payload:
        raise ValueError('Refresh token payload must include "sub"')
    expire_delta = expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = _build_token_payload(payload, token_type='refresh', expires_delta=expire_delta)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def decode_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    token_type = payload.get('type')
    if token_type and token_type != 'access':
        raise JWTError('Invalid token type')
    return payload


def hash_token(token: str) -> str:
    return sha256(token.encode('utf-8')).hexdigest()
