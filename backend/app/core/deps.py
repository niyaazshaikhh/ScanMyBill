from collections.abc import Callable

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth_exceptions import AuthException
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token, hash_token
from app.models.revoked_token import RevokedToken
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f'{settings.api_v1_prefix}/auth/login',
    auto_error=False,
)


def get_current_user(
    db: Session = Depends(get_db), token: str | None = Depends(oauth2_scheme)
) -> User:
    if not token:
        raise AuthException(
            message='Not authenticated',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    try:
        payload = decode_token(token)
    except ExpiredSignatureError as exc:
        raise AuthException(
            message='Access token has expired',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc
    except JWTError as exc:
        raise AuthException(
            message='Could not validate credentials',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc

    token_type = payload.get('type')
    if token_type not in (None, 'access'):
        raise AuthException(
            message='Invalid token type',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    try:
        user_id: str | None = payload.get('sub')
        if user_id is None:
            raise AuthException(
                message='Could not validate credentials',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={'WWW-Authenticate': 'Bearer'},
            )
    except (TypeError, ValueError) as exc:
        raise AuthException(
            message='Could not validate credentials',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc

    token_hash = hash_token(token)
    jti = payload.get('jti')

    blacklisted = False
    if isinstance(jti, str) and jti:
        blacklisted = (
            db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.token == jti))
            is not None
        )

    if isinstance(jti, str) and jti:
        revoked = db.scalar(
            select(RevokedToken.id).where(
                or_(RevokedToken.token_hash == token_hash, RevokedToken.jti == jti)
            )
        )
    else:
        revoked = db.scalar(select(RevokedToken.id).where(RevokedToken.token_hash == token_hash))

    if blacklisted or revoked:
        raise AuthException(
            message='Token has been revoked',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthException(
            message='Could not validate credentials',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return user


def require_roles(allowed_roles: list[UserRole]) -> Callable:
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AuthException(
                message='Insufficient permissions',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return current_user

    return checker
