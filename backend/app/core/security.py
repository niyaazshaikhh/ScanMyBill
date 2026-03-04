from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

SECRET_KEY = settings.secret_key
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days
SESSION_INACTIVITY_TIMEOUT_MINUTES = settings.session_inactivity_timeout_minutes
ACCESS_TOKEN_REFRESH_THRESHOLD_SECONDS = settings.access_token_refresh_threshold_minutes * 60
REFRESH_COOKIE_NAME = 'refresh_token'

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def inactivity_timeout_delta() -> timedelta:
    return timedelta(minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES)


def _normalize_bcrypt_password(password: str) -> str:
    # bcrypt only accepts up to 72 bytes.
    return password.encode('utf-8')[:72].decode('utf-8', 'ignore')


def hash_password(password: str) -> str:
    normalized = _normalize_bcrypt_password(password)
    return pwd_context.hash(normalized)


def get_password_hash(password: str) -> str:
    # Backward-compatible alias used by existing auth code.
    return hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        normalized = _normalize_bcrypt_password(plain)
        return pwd_context.verify(normalized, hashed)
    except (ValueError, TypeError):
        return False


def _build_token_payload(
    data: dict[str, Any],
    token_type: str,
    expires_delta: timedelta,
) -> dict[str, Any]:
    now = utc_now()
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


def decode_token(token: str, *, verify_exp: bool = True) -> dict[str, Any]:
    if verify_exp:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={'verify_exp': False})


def decode_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    token_type = payload.get('type')
    if token_type and token_type != 'access':
        raise JWTError('Invalid token type')
    return payload


def datetime_from_claim(payload: dict[str, Any], claim: str) -> datetime | None:
    raw = payload.get(claim)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except ValueError:
            return None
    return None


def seconds_until_expiry(payload: dict[str, Any], *, now: datetime | None = None) -> int | None:
    exp_at = datetime_from_claim(payload, 'exp')
    if exp_at is None:
        return None
    current = now or utc_now()
    return int((exp_at - current).total_seconds())


def is_token_close_to_expiry(
    payload: dict[str, Any],
    *,
    threshold_seconds: int = ACCESS_TOKEN_REFRESH_THRESHOLD_SECONDS,
    now: datetime | None = None,
) -> bool:
    seconds_left = seconds_until_expiry(payload, now=now)
    if seconds_left is None:
        return False
    return seconds_left <= max(0, threshold_seconds)


def hash_token(token: str) -> str:
    return sha256(token.encode('utf-8')).hexdigest()
