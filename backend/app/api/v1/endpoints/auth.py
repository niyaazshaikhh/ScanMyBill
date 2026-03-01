import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from google.auth.transport import requests
from google.oauth2 import id_token
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, oauth2_scheme
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
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

router = APIRouter(prefix='/auth')
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 15


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _create_local_account(email: str, password: str, full_name: str, db: Session) -> User:
    normalized_email = _normalize_email(email)
    normalized_name = full_name.strip()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        if existing.hashed_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already exists')

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


def _auth_response(user: User) -> TokenResponse:
    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post('/create-account', response_model=TokenResponse)
def create_account(payload: CreateAccountRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = _create_local_account(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        db=db,
    )
    return _auth_response(user)


@router.post('/register', response_model=TokenResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    user = _create_local_account(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        db=db,
    )
    return _auth_response(user)


@router.post('/login', response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')

    return _auth_response(user)


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

    # Email delivery is not configured yet, so token is returned for frontend use.
    return ForgotPasswordResponse(message=generic_message, reset_token=raw_token, expires_at=expires_at)


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid or expired reset token')

    user.hashed_password = get_password_hash(payload.new_password)
    user.reset_token = None
    user.reset_token_expiry = None

    db.commit()
    return MessageResponse(message='Password reset successful. You can now log in.')


@router.post('/google', response_model=TokenResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    allowed_client_ids = settings.allowed_google_client_ids
    if not allowed_client_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Google OAuth is not configured',
        )

    try:
        token_info = id_token.verify_oauth2_token(
            payload.id_token,
            requests.Request(),
            audience=None,
            clock_skew_in_seconds=30,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Google token') from exc

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Google token audience')

    email = _normalize_email(token_info.get('email') or '')
    name = token_info.get('name') or email.split('@')[0]
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Google account email missing')

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, full_name=name, hashed_password=None, role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.get('/me', response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc

    exp_raw = payload.get('exp')
    if isinstance(exp_raw, (int, float)):
        expires_at = datetime.fromtimestamp(exp_raw, tz=timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc)

    token_hash = hash_token(token)
    jti = payload.get('jti') if isinstance(payload.get('jti'), str) else None

    existing_conditions = [RevokedToken.token_hash == token_hash]
    if jti:
        existing_conditions.append(RevokedToken.jti == jti)

    existing = db.scalar(select(RevokedToken).where(or_(*existing_conditions)))

    if not existing:
        db.add(
            RevokedToken(
                user_id=current_user.id,
                token_hash=token_hash,
                jti=jti,
                expires_at=expires_at,
            )
        )
        db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
