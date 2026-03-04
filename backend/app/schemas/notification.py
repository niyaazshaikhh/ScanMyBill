from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationCategory


class NotificationResponse(BaseModel):
    id: str
    category: NotificationCategory
    title: str
    message: str
    route: str | None
    is_read: bool
    created_at: datetime

    model_config = {'from_attributes': True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    count: int


class NotificationStatusResponse(BaseModel):
    success: bool = True
