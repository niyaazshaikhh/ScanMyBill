from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token, hash_token
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f'{settings.api_v1_prefix}/auth/login')


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get('sub')
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    token_hash = hash_token(token)
    jti = payload.get('jti')
    if isinstance(jti, str) and jti:
        revoked = db.scalar(
            select(RevokedToken.id).where(
                or_(RevokedToken.token_hash == token_hash, RevokedToken.jti == jti)
            )
        )
    else:
        revoked = db.scalar(select(RevokedToken.id).where(RevokedToken.token_hash == token_hash))

    if revoked:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(allowed_roles: list[UserRole]) -> Callable:
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Insufficient permissions',
            )
        return current_user

    return checker
