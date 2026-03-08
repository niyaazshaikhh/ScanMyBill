from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, hash_token, utc_now
from app.core.validators import ensure_password_strength
from app.models.user import User

PASSWORD_RESET_TOKEN_EXPIRY_MINUTES = 30
FRONTEND_RESET_PASSWORD_URL = 'https://app.scanmybill.xyz/reset-password'


def create_reset_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.reset_token = hash_token(token)
    user.reset_token_expiry = utc_now() + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRY_MINUTES)
    db.commit()
    return token


def build_password_reset_link(token: str) -> str:
    return f'{FRONTEND_RESET_PASSWORD_URL}?token={quote_plus(token)}'


def verify_reset_token(db: Session, token: str) -> User | None:
    token_hash = hash_token(token)
    now = utc_now()

    user = db.scalar(
        select(User).where(
            User.reset_token == token_hash,
            User.reset_token_expiry.is_not(None),
            User.reset_token_expiry > now,
        )
    )
    if user:
        return user

    expired_user = db.scalar(
        select(User).where(
            User.reset_token == token_hash,
            User.reset_token_expiry.is_not(None),
            User.reset_token_expiry <= now,
        )
    )
    if expired_user:
        expired_user.reset_token = None
        expired_user.reset_token_expiry = None
        db.commit()

    return None


def reset_user_password(db: Session, token: str, new_password: str) -> bool:
    try:
        ensure_password_strength(new_password)
    except ValueError:
        return False

    user = verify_reset_token(db, token)
    if not user:
        return False

    user.hashed_password = get_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    return True
