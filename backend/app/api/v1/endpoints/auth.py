from datetime import datetime, timezone

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
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.schemas.auth import GoogleAuthRequest, LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter()


@router.post('/register', response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already exists')

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')

    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


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

    email = (token_info.get('email') or '').lower()
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
