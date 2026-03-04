from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class AdminPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    new_password: str = Field(min_length=8, max_length=128)


class AdminActionResponse(BaseModel):
    message: str
