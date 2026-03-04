from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class NewsletterCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: EmailStr


class NewsletterSubscribeResponse(BaseModel):
    success: bool
    message: str


class NewsletterSubscriberResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    created_at: datetime

    model_config = {'from_attributes': True}


class NewsletterSubscriberListResponse(BaseModel):
    total_subscribers: int
    active_subscribers: int
    subscribers: list[NewsletterSubscriberResponse]


class NewsletterSendRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    subscriber_ids: list[str] = Field(default_factory=list, min_length=1)
    subject: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=5, max_length=10000)


class NewsletterSendResponse(BaseModel):
    success: bool
    message: str
    attempted: int
    sent: int
    failed: int
    failed_recipients: list[EmailStr] = Field(default_factory=list)
