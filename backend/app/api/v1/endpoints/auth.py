import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from google.auth.transport import requests
from google.oauth2 import id_token
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth_exceptions import AuthException
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_COOKIE_NAME,
    create_access_token,
    create_refresh_token,
    datetime_from_claim,
    decode_token,
    get_password_hash,
    hash_token,
    inactivity_timeout_delta,
    utc_now,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.revoked_token import RevokedToken
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.schemas.admin import AdminLoginRequest
from app.schemas.auth import (
    CreateAccountRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleAuthRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.schemas.user import (
    ForgotPasswordRequest as UserForgotPasswordRequest,
    ResetPasswordRequest as UserResetPasswordRequest,
    UserCreate,
    UserLogin,
)
from app.services.admin_bootstrap import default_admin_identity, ensure_default_admin_user

router = APIRouter(prefix='/auth')
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 15
REFRESH_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _auth_error(
    message: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    *,
    headers: dict[str, str] | None = None,
) -> AuthException:
    return AuthException(
        message=message,
        status_code=status_code,
        headers=headers or {},
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_admin_id(admin_id: str) -> str:
    return admin_id.strip().lower()


def _create_local_account(email: str, password: str, full_name: str, db: Session) -> User:
    normalized_email = _normalize_email(email)
    normalized_name = full_name.strip()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        if existing.hashed_password:
            raise _auth_error('Email already exists', status.HTTP_400_BAD_REQUEST)

        # Upgrade OAuth-only account to include password login.
        existing.full_name = normalized_name
        existing.hashed_password = get_password_hash(password)
        db.commit()
        db.refresh(existing)
        return existing

    user = User(
        email=normalized_email,
        full_name=normalized_name,
        hashed_password=get_password_hash(password),
        role=UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    same_site = settings.cookie_samesite.lower()
    if same_site not in {'lax', 'strict', 'none'}:
        same_site = 'lax'
    if same_site == 'none' and not settings.cookie_secure:
        # Browsers reject SameSite=None unless Secure is set.
        same_site = 'lax'

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=same_site,
        max_age=REFRESH_COOKIE_MAX_AGE,
        expires=REFRESH_COOKIE_MAX_AGE,
        domain=settings.cookie_domain,
        path='/',
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path='/', domain=settings.cookie_domain)


def _extract_expiry(payload: dict) -> datetime:
    exp_at = datetime_from_claim(payload, 'exp')
    if exp_at is not None:
        return exp_at
    return utc_now()


def _is_jti_blacklisted(db: Session, jti: str) -> bool:
    if db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.token == jti)):
        return True
    return db.scalar(select(RevokedToken.id).where(RevokedToken.jti == jti)) is not None


def _blacklist_jti(db: Session, jti: str) -> None:
    existing = db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.token == jti))
    if not existing:
        db.add(TokenBlacklist(token=jti))


def _blacklist_legacy_token(db: Session, user_id: str, token: str, payload: dict) -> None:
    token_hash = hash_token(token)
    jti = payload.get('jti') if isinstance(payload.get('jti'), str) else None

    existing_conditions = [RevokedToken.token_hash == token_hash]
    if jti:
        existing_conditions.append(RevokedToken.jti == jti)

    existing = db.scalar(select(RevokedToken.id).where(or_(*existing_conditions)))
    if existing:
        return

    db.add(
        RevokedToken(
            user_id=user_id,
            token_hash=token_hash,
            jti=jti,
            expires_at=_extract_expiry(payload),
        )
    )


def _create_session_response(user: User, response: Response, db: Session) -> TokenResponse:
    now = utc_now()
    session_id = str(uuid4())
    access_token = create_access_token(subject=user.id, role=user.role.value, data={'sid': session_id})
    refresh_token = create_refresh_token(subject=user.id, role=user.role.value, data={'sid': session_id})

    refresh_payload = decode_token(refresh_token)
    refresh_jti = refresh_payload.get('jti')
    if not isinstance(refresh_jti, str) or not refresh_jti:
        raise _auth_error('Could not create login session', status.HTTP_500_INTERNAL_SERVER_ERROR)

    db.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            refresh_jti=refresh_jti,
            refresh_token_hash=hash_token(refresh_token),
            last_activity_at=now,
            inactive_expires_at=now + inactivity_timeout_delta(),
            refresh_expires_at=_extract_expiry(refresh_payload),
            is_active=True,
        )
    )
    db.commit()

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token, user=UserPublic.model_validate(user))


def _load_active_session(
    db: Session,
    *,
    session_id: str,
    user_id: str,
) -> UserSession | None:
    return db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.is_active.is_(True),
        )
    )


def _revoke_session(db: Session, session: UserSession, *, when: datetime | None = None) -> None:
    session.revoke()
    session.revoked_at = when or utc_now()


@router.post('/create-account', response_model=TokenResponse)
def create_account(
    payload: CreateAccountRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = _create_local_account(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        db=db,
    )
    return _create_session_response(user, response, db)


@router.post('/register', response_model=TokenResponse)
def register(
    payload: UserCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = _create_local_account(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        db=db,
    )
    return _create_session_response(user, response, db)


@router.post('/login', response_model=TokenResponse)
def login(
    payload: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if not user or not user.hashed_password:
        raise _auth_error(
            'Invalid credentials',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )
    if not verify_password(payload.password, user.hashed_password):
        raise _auth_error(
            'Invalid credentials',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )
    if not user.is_active:
        raise _auth_error('User account is inactive', status.HTTP_401_UNAUTHORIZED)

    return _create_session_response(user, response, db)


@router.post('/admin/login', response_model=TokenResponse)
def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    configured_admin_id, configured_admin_email = default_admin_identity()
    provided_admin_id = _normalize_admin_id(payload.admin_id)
    if provided_admin_id != _normalize_admin_id(configured_admin_id):
        raise _auth_error(
            'Invalid credentials',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    admin_user = ensure_default_admin_user(db)
    if admin_user is None:
        admin_user = db.scalar(select(User).where(User.email == configured_admin_email))

    if (
        not admin_user
        or _normalize_email(admin_user.email) != _normalize_email(configured_admin_email)
        or admin_user.role != UserRole.ADMIN
        or not admin_user.hashed_password
        or not verify_password(payload.password, admin_user.hashed_password)
    ):
        raise _auth_error(
            'Invalid credentials',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    if not admin_user.is_active:
        raise _auth_error('User account is inactive', status.HTTP_401_UNAUTHORIZED)

    return _create_session_response(admin_user, response, db)


@router.post('/forgot-password', response_model=ForgotPasswordResponse)
def forgot_password(
    payload: UserForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> ForgotPasswordResponse:
    generic_message = 'If an account with that email exists, a password reset link has been generated.'
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if not user:
        return ForgotPasswordResponse(message=generic_message)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    raw_token = secrets.token_urlsafe(32)

    user.reset_token = hash_token(raw_token)
    user.reset_token_expiry = expires_at
    db.commit()

    # Keep backward compatibility via env flag while allowing secure production behavior.
    return ForgotPasswordResponse(
        message=generic_message,
        reset_token=raw_token if settings.expose_password_reset_token else None,
        expires_at=expires_at if settings.expose_password_reset_token else None,
    )


@router.post('/reset-password', response_model=MessageResponse)
def reset_password(payload: UserResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    now = datetime.now(timezone.utc)

    user = db.scalar(
        select(User).where(
            User.reset_token == hash_token(payload.token),
            User.reset_token_expiry.is_not(None),
            User.reset_token_expiry > now,
        )
    )
    if not user:
        raise _auth_error('Invalid or expired reset token', status.HTTP_400_BAD_REQUEST)

    user.hashed_password = get_password_hash(payload.new_password)
    user.reset_token = None
    user.reset_token_expiry = None

    db.commit()
    return MessageResponse(message='Password reset successful. You can now log in.')


@router.post('/google', response_model=TokenResponse)
def google_auth(
    payload: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    allowed_client_ids = settings.allowed_google_client_ids
    if not allowed_client_ids:
        raise _auth_error('Google OAuth is not configured', status.HTTP_400_BAD_REQUEST)

    try:
        token_info = id_token.verify_oauth2_token(
            payload.id_token,
            requests.Request(),
            audience=None,
            clock_skew_in_seconds=30,
        )
    except Exception as exc:
        raise _auth_error(
            'Invalid Google token',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc

    audiences: set[str] = set()
    aud = token_info.get('aud')
    if isinstance(aud, str):
        audiences.add(aud)
    elif isinstance(aud, list):
        audiences.update(str(item) for item in aud if item)

    azp = token_info.get('azp')
    if isinstance(azp, str) and azp:
        audiences.add(azp)

    if not audiences.intersection(allowed_client_ids):
        raise _auth_error('Invalid Google token audience', status.HTTP_401_UNAUTHORIZED)

    email = _normalize_email(token_info.get('email') or '')
    name = token_info.get('name') or email.split('@')[0]
    if not email:
        raise _auth_error('Google account email missing', status.HTTP_400_BAD_REQUEST)

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, full_name=name, hashed_password=None, role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active:
        raise _auth_error('User account is inactive', status.HTTP_401_UNAUTHORIZED)

    return _create_session_response(user, response, db)


@router.get('/me', response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post('/refresh', response_model=TokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    if not refresh_token:
        raise _auth_error(
            'Refresh token missing',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        )

    try:
        payload = decode_token(refresh_token)
    except ExpiredSignatureError as exc:
        _clear_refresh_cookie(response)
        raise _auth_error(
            'Refresh token has expired',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc
    except JWTError as exc:
        _clear_refresh_cookie(response)
        raise _auth_error(
            'Invalid refresh token',
            status.HTTP_401_UNAUTHORIZED,
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc

    if payload.get('type') != 'refresh':
        _clear_refresh_cookie(response)
        raise _auth_error('Invalid token type', status.HTTP_401_UNAUTHORIZED)

    user_id = payload.get('sub')
    session_id = payload.get('sid')
    jti = payload.get('jti') if isinstance(payload.get('jti'), str) else None
    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(session_id, str)
        or not session_id
        or not jti
    ):
        _clear_refresh_cookie(response)
        raise _auth_error('Invalid refresh token', status.HTTP_401_UNAUTHORIZED)

    refresh_token_hash = hash_token(refresh_token)
    now = utc_now()
    session = _load_active_session(db, session_id=session_id, user_id=user_id)
    if not session:
        _clear_refresh_cookie(response)
        raise _auth_error('Refresh token has been revoked', status.HTTP_401_UNAUTHORIZED)

    if (
        session.refresh_jti != jti
        or session.refresh_token_hash != refresh_token_hash
        or session.inactive_expires_at <= now
        or session.refresh_expires_at <= now
    ):
        _revoke_session(db, session, when=now)
        _blacklist_jti(db, jti)
        _blacklist_legacy_token(db, user_id=user_id, token=refresh_token, payload=payload)
        db.commit()
        _clear_refresh_cookie(response)

        if session.inactive_expires_at <= now:
            raise _auth_error('Session expired due to inactivity', status.HTTP_401_UNAUTHORIZED)
        raise _auth_error('Refresh token has expired', status.HTTP_401_UNAUTHORIZED)

    revoked = db.scalar(
        select(RevokedToken.id).where(
            or_(
                RevokedToken.token_hash == refresh_token_hash,
                RevokedToken.jti == jti,
            )
        )
    )
    if revoked or _is_jti_blacklisted(db, jti):
        _revoke_session(db, session, when=now)
        db.commit()
        _clear_refresh_cookie(response)
        raise _auth_error('Refresh token has been revoked', status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, user_id)
    if not user or not user.is_active:
        _revoke_session(db, session, when=now)
        db.commit()
        _clear_refresh_cookie(response)
        raise _auth_error('Invalid session user', status.HTTP_401_UNAUTHORIZED)

    access_token = create_access_token(subject=user.id, role=user.role.value, data={'sid': session_id})
    new_refresh_token = create_refresh_token(
        subject=user.id,
        role=user.role.value,
        data={'sid': session_id},
    )
    new_refresh_payload = decode_token(new_refresh_token)
    new_jti = new_refresh_payload.get('jti')
    if not isinstance(new_jti, str) or not new_jti:
        raise _auth_error('Could not refresh session', status.HTTP_500_INTERNAL_SERVER_ERROR)

    _blacklist_jti(db, jti)
    _blacklist_legacy_token(db, user_id=user_id, token=refresh_token, payload=payload)

    session.refresh_jti = new_jti
    session.refresh_token_hash = hash_token(new_refresh_token)
    session.last_activity_at = now
    session.inactive_expires_at = now + inactivity_timeout_delta()
    session.refresh_expires_at = _extract_expiry(new_refresh_payload)
    session.is_active = True
    session.revoked_at = None

    db.commit()

    _set_refresh_cookie(response, new_refresh_token)

    return TokenResponse(access_token=access_token, user=UserPublic.model_validate(user))


@router.post('/logout')
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> dict[str, bool | str]:
    did_blacklist = False
    session_ids_to_revoke: set[tuple[str, str]] = set()

    auth_header = request.headers.get('Authorization') or ''
    access_token = ''
    if auth_header.lower().startswith('bearer '):
        access_token = auth_header.split(' ', 1)[1].strip()

    if access_token:
        try:
            access_payload = decode_token(access_token, verify_exp=False)
            if access_payload.get('type') in (None, 'access'):
                jti = access_payload.get('jti')
                sub = access_payload.get('sub')
                sid = access_payload.get('sid')
                if isinstance(jti, str) and jti:
                    _blacklist_jti(db, jti)
                    did_blacklist = True
                if isinstance(sub, str) and sub:
                    _blacklist_legacy_token(
                        db,
                        user_id=sub,
                        token=access_token,
                        payload=access_payload,
                    )
                    did_blacklist = True
                    if isinstance(sid, str) and sid:
                        session_ids_to_revoke.add((sid, sub))
        except JWTError:
            pass

    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, verify_exp=False)
            if refresh_payload.get('type') == 'refresh':
                jti = refresh_payload.get('jti')
                sub = refresh_payload.get('sub')
                sid = refresh_payload.get('sid')
                if isinstance(jti, str) and jti:
                    _blacklist_jti(db, jti)
                    did_blacklist = True
                if isinstance(sub, str) and sub:
                    _blacklist_legacy_token(
                        db,
                        user_id=sub,
                        token=refresh_token,
                        payload=refresh_payload,
                    )
                    did_blacklist = True
                    if isinstance(sid, str) and sid:
                        session_ids_to_revoke.add((sid, sub))
        except JWTError:
            pass

    for session_id, user_id in session_ids_to_revoke:
        session = _load_active_session(db, session_id=session_id, user_id=user_id)
        if session:
            _revoke_session(db, session)
            did_blacklist = True

    if did_blacklist:
        db.commit()

    _clear_refresh_cookie(response)

    return {'success': True, 'message': 'Logged out successfully'}
