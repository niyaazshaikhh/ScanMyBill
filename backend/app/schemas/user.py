from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import ensure_password_strength, ensure_safe_person_name
from app.models.user import SubscriptionPlan, SubscriptionStatus


class _StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class UserCreate(_StrictRequestModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        return ensure_password_strength(value)

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return ensure_safe_person_name(value, 'Full name')


class UserLogin(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr

    model_config = {'from_attributes': True}


class CurrentUserResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    notifications_enabled: bool = True
    subscription_plan: SubscriptionPlan
    subscription_status: SubscriptionStatus

    model_config = {'from_attributes': True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class ForgotPasswordRequest(_StrictRequestModel):
    email: EmailStr = Field(max_length=254)


class ResetPasswordRequest(_StrictRequestModel):
    token: str = Field(min_length=16, max_length=255, pattern=r'^[A-Za-z0-9_\-]+$')
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return ensure_password_strength(value)


class NotificationPreferenceUpdate(_StrictRequestModel):
    notifications_enabled: bool
