from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import ensure_password_strength, ensure_safe_person_name
from app.models.user import SubscriptionPlan, SubscriptionStatus, UserRole


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    notifications_enabled: bool = True
    subscription_plan: SubscriptionPlan
    subscription_status: SubscriptionStatus
    razorpay_subscription_id: str | None = None
    subscription_started_at: datetime | None = None
    subscription_expires_at: datetime | None = None
    created_at: datetime

    model_config = {'from_attributes': True}


class _StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class RegisterRequest(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        return ensure_password_strength(value)

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return ensure_safe_person_name(value, 'Full name')


class CreateAccountRequest(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        return ensure_password_strength(value)

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return ensure_safe_person_name(value, 'Full name')


class LoginRequest(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class GoogleAuthRequest(_StrictRequestModel):
    id_token: str


class ForgotPasswordRequest(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    expires_at: datetime | None = None


class ResetPasswordRequest(_StrictRequestModel):
    token: str = Field(min_length=16, max_length=255, pattern=r'^[A-Za-z0-9_\-]+$')
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return ensure_password_strength(value)


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserPublic
