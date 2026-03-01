from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from typing import Any
from uuid import uuid4

import bcrypt
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

SECRET_KEY = os.getenv('SECRET_KEY', settings.secret_key)
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def create_access_token(
    subject: str,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode: dict[str, Any] = {
        'sub': subject,
        'exp': expire,
        'iat': now,
        'jti': str(uuid4()),
    }
    if role:
        to_encode['role'] = role
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def hash_token(token: str) -> str:
    return sha256(token.encode('utf-8')).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
