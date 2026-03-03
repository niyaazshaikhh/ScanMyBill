from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import SubscriptionPlan, SubscriptionStatus


class _StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class UserCreate(_StrictRequestModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(_StrictRequestModel):
    email: EmailStr
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
    subscription_plan: SubscriptionPlan
    subscription_status: SubscriptionStatus

    model_config = {'from_attributes': True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class ForgotPasswordRequest(_StrictRequestModel):
    email: EmailStr


class ResetPasswordRequest(_StrictRequestModel):
    token: str = Field(min_length=16, max_length=255)
    new_password: str = Field(min_length=8, max_length=128)
