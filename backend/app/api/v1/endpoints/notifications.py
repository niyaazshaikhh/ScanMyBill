from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.schemas.notification import NotificationListResponse, NotificationResponse, NotificationStatusResponse
from app.services.notifications import (
    ensure_monthly_gst_payable_notification,
    ensure_quarterly_gst_payable_notification,
)

router = APIRouter()


@router.get('', response_model=NotificationListResponse)
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    is_admin = current_user.role == UserRole.ADMIN
    if not is_admin:
        monthly_inserted_or_updated = ensure_monthly_gst_payable_notification(db, user_id=current_user.id)
        quarterly_inserted_or_updated = ensure_quarterly_gst_payable_notification(db, user_id=current_user.id)
        if monthly_inserted_or_updated or quarterly_inserted_or_updated:
            db.commit()

    notification_filters = [Notification.owner_id == current_user.id]
    if is_admin:
        notification_filters.append(
            or_(
                Notification.dedupe_key.is_(None),
                ~Notification.dedupe_key.like('gst-payable-%'),
            )
        )

    notifications = list(
        db.scalars(
            select(Notification)
            .where(*notification_filters)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        ).all()
    )

    unread_filters = [*notification_filters, Notification.is_read.is_(False)]
    unread_count = int(
        db.scalar(
            select(func.count(Notification.id)).where(*unread_filters)
        )
        or 0
    )
    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(item) for item in notifications],
        unread_count=unread_count,
        count=len(notifications),
    )


@router.post('/read-all', response_model=NotificationStatusResponse)
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationStatusResponse:
    db.execute(
        update(Notification)
        .where(
            Notification.owner_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    db.commit()
    return NotificationStatusResponse(success=True)


@router.delete('/clear-all', response_model=NotificationStatusResponse)
def clear_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationStatusResponse:
    db.execute(
        delete(Notification).where(
            Notification.owner_id == current_user.id,
        )
    )
    db.commit()
    return NotificationStatusResponse(success=True)


@router.post('/{notification_id}/read', response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.owner_id == current_user.id,
        )
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Notification not found')

    if not notification.is_read:
        notification.is_read = True
        db.commit()
        db.refresh(notification)

    return NotificationResponse.model_validate(notification)
