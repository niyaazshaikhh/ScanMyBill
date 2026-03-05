from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import ensure_password_strength, ensure_safe_person_name
from app.models.user import SubscriptionPlan, SubscriptionStatus, UserRole


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    admin_id: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AdminUserSummary(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    subscription_plan: SubscriptionPlan
    subscription_status: SubscriptionStatus
    created_at: datetime

    model_config = {'from_attributes': True}


class AdminUsersResponse(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    users: list[AdminUserSummary]


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    role: UserRole | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_safe_person_name(value, 'Full name')


class AdminPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    new_password: str = Field(min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return ensure_password_strength(value)


class AdminActionResponse(BaseModel):
    message: str
