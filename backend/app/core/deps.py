from collections.abc import Callable
from datetime import datetime

from fastapi import Depends, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth_exceptions import AuthException
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    datetime_from_claim,
    decode_token,
    hash_token,
    inactivity_timeout_delta,
    is_token_close_to_expiry,
    utc_now,
)
from app.models.revoked_token import RevokedToken
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User, UserRole
from app.models.user_session import UserSession

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f'{settings.api_v1_prefix}/auth/login',
    auto_error=False,
)
REFRESH_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    same_site = settings.cookie_samesite.lower()
    if same_site not in {'lax', 'strict', 'none'}:
        same_site = 'lax'

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=same_site,
        max_age=REFRESH_COOKIE_MAX_AGE,
        expires=REFRESH_COOKIE_MAX_AGE,
        path='/',
    )


def _extract_expiry(payload: dict) -> datetime:
    exp_at = datetime_from_claim(payload, 'exp')
    if exp_at is not None:
        return exp_at
    return utc_now()


def _blacklist_jti(db: Session, jti: str) -> None:
    if not db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.token == jti)):
        db.add(TokenBlacklist(token=jti))


def _blacklist_token(db: Session, user_id: str, token: str, payload: dict) -> None:
    token_hash = hash_token(token)
    jti = payload.get('jti') if isinstance(payload.get('jti'), str) else None

    conditions = [RevokedToken.token_hash == token_hash]
    if jti:
        conditions.append(RevokedToken.jti == jti)

    if db.scalar(select(RevokedToken.id).where(or_(*conditions))):
        return

    db.add(
        RevokedToken(
            user_id=user_id,
            token_hash=token_hash,
            jti=jti,
            expires_at=_extract_expiry(payload),
        )
    )


def _is_session_expired(session: UserSession, now: datetime) -> bool:
    return session.inactive_expires_at <= now or session.refresh_expires_at <= now or not session.is_active


def get_current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
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
    session_id = payload.get('sid') if isinstance(payload.get('sid'), str) else None

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

    now = utc_now()

    if session_id:
        session = db.scalar(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
            )
        )
        if not session:
            raise AuthException(
                message='Session not found',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={'WWW-Authenticate': 'Bearer'},
            )

        if _is_session_expired(session, now):
            session.revoke()
            if isinstance(jti, str) and jti:
                _blacklist_jti(db, jti)
            _blacklist_token(db, user_id, token, payload)
            db.commit()
            raise AuthException(
                message='Session expired due to inactivity',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={'WWW-Authenticate': 'Bearer'},
            )

        session.last_activity_at = now
        session.inactive_expires_at = now + inactivity_timeout_delta()

        # Sliding session: rotate tokens when access token is near expiry.
        if is_token_close_to_expiry(payload, now=now):
            refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
            if refresh_token:
                try:
                    refresh_payload = decode_token(refresh_token)
                except JWTError:
                    refresh_payload = None

                if refresh_payload and refresh_payload.get('type') == 'refresh':
                    refresh_user_id = refresh_payload.get('sub')
                    refresh_session_id = refresh_payload.get('sid')
                    refresh_jti = refresh_payload.get('jti')
                    refresh_hash = hash_token(refresh_token)

                    if (
                        isinstance(refresh_user_id, str)
                        and refresh_user_id == user_id
                        and isinstance(refresh_session_id, str)
                        and refresh_session_id == session_id
                        and isinstance(refresh_jti, str)
                        and session.refresh_jti == refresh_jti
                        and session.refresh_token_hash == refresh_hash
                    ):
                        new_access_token = create_access_token(
                            subject=user.id,
                            role=user.role.value,
                            data={'sid': session_id},
                        )
                        new_refresh_token = create_refresh_token(
                            subject=user.id,
                            role=user.role.value,
                            data={'sid': session_id},
                        )
                        new_refresh_payload = decode_token(new_refresh_token)
                        new_refresh_jti = new_refresh_payload.get('jti')

                        if isinstance(new_refresh_jti, str) and new_refresh_jti:
                            _blacklist_jti(db, refresh_jti)
                            _blacklist_token(db, user_id, refresh_token, refresh_payload)

                            session.refresh_jti = new_refresh_jti
                            session.refresh_token_hash = hash_token(new_refresh_token)
                            session.refresh_expires_at = _extract_expiry(new_refresh_payload)
                            session.last_activity_at = now
                            session.inactive_expires_at = now + inactivity_timeout_delta()

                            _set_refresh_cookie(response, new_refresh_token)
                            response.headers['X-Access-Token'] = new_access_token
                            response.headers['X-Token-Refreshed'] = '1'

        db.commit()

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
