from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.user import UserRole


class NewsletterSubscribeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: EmailStr


class NewsletterSend(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    subject: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=5, max_length=10000)


class NewsletterResponse(BaseModel):
    email: EmailStr
    subscribed_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def ensure_subscribed_at(cls, value: object) -> object:
        if isinstance(value, dict):
            if value.get('subscribed_at') is None:
                value['subscribed_at'] = datetime.now(timezone.utc)
            return value

        subscribed_at = getattr(value, 'subscribed_at', None)
        if subscribed_at is not None:
            return value

        return {
            'email': getattr(value, 'email', ''),
            'subscribed_at': datetime.now(timezone.utc),
            'is_active': bool(getattr(value, 'is_active', True)),
        }


# Backward-compatible aliases for existing frontend usage.
class NewsletterSubscribe(NewsletterSubscribeRequest):
    pass


class NewsletterCreate(NewsletterSubscribeRequest):
    pass


class NewsletterSubscribeResponse(BaseModel):
    success: bool
    message: str


class NewsletterSubscriberResponse(NewsletterResponse):
    id: str
    unsubscribed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='after')
    def ensure_created_at(self) -> 'NewsletterSubscriberResponse':
        if self.created_at is None:
            self.created_at = self.subscribed_at
        return self


class NewsletterSubscriberListResponse(BaseModel):
    total_subscribers: int
    active_subscribers: int
    subscribers: list[NewsletterSubscriberResponse]


class NewsletterUserTargetResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    notifications_enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NewsletterUserListResponse(BaseModel):
    total_users: int
    active_users: int
    users: list[NewsletterUserTargetResponse]


class NewsletterSendRequest(NewsletterSend):
    subscriber_ids: list[str] = Field(default_factory=list)
    user_ids: list[str] = Field(default_factory=list)
    send_email: bool = True
    send_notifications: bool = False

    @model_validator(mode='after')
    def validate_delivery_channels(self) -> 'NewsletterSendRequest':
        if not self.send_email and not self.send_notifications:
            raise ValueError('At least one delivery channel must be enabled')
        return self


class NewsletterSendResponse(BaseModel):
    success: bool
    message: str
    attempted: int
    sent: int
    failed: int
    queued_notifications: int = 0
    failed_recipients: list[EmailStr] = Field(default_factory=list)
