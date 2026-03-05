import logging
import re
from html import unescape

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import require_roles
from app.core.security import get_password_hash
from app.models.notification import NotificationCategory
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.models.user import User, UserRole
from app.schemas.newsletter import (
    NewsletterSendRequest,
    NewsletterSendResponse,
    NewsletterSubscriberListResponse,
    NewsletterSubscriberResponse,
    NewsletterUserListResponse,
    NewsletterUserTargetResponse,
)
from app.schemas.admin import (
    AdminActionResponse,
    AdminPasswordResetRequest,
    AdminUserSummary,
    AdminUserUpdateRequest,
    AdminUsersResponse,
)
from app.services.email_service import EmailDeliveryError, validate_email_configuration
from app.services.newsletter_service import send_newsletter
from app.services.notifications import create_notification

router = APIRouter()
logger = logging.getLogger(__name__)
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')


def _unique_emails(emails: list[str]) -> list[str]:
    deduped: dict[str, str] = {}
    for email in emails:
        normalized = email.strip().lower()
        if not normalized:
            continue
        if normalized not in deduped:
            deduped[normalized] = email.strip()
    return list(deduped.values())


def _notification_message(html_message: str) -> str:
    plain_text = HTML_TAG_PATTERN.sub(' ', html_message)
    plain_text = unescape(plain_text)
    collapsed = ' '.join(plain_text.split())
    return collapsed[:1000] if collapsed else 'You have a new newsletter update.'


def _admin_guard(current_user: User = Depends(require_roles([UserRole.ADMIN]))) -> User:
    return current_user


def _send_newsletter_background(
    *,
    recipient_emails: list[str],
    notification_user_ids: list[str],
    send_email: bool,
    send_notifications: bool,
    subject: str,
    message: str,
    admin_user_id: str,
) -> None:
    db = SessionLocal()
    try:
        sent_count = 0
        failed_recipients: list[str] = []
        notification_count = 0

        if send_email and recipient_emails:
            sent_count, failed_recipients = send_newsletter(
                db,
                subject,
                message,
                recipient_emails=recipient_emails,
            )

        if send_notifications and notification_user_ids:
            notification_body = _notification_message(message)
            for user_id in notification_user_ids:
                created = create_notification(
                    db,
                    user_id=user_id,
                    title=subject,
                    message=notification_body,
                    route='/newsletter',
                    category=NotificationCategory.SYSTEM,
                )
                if created is not None:
                    notification_count += 1
            db.commit()

        logger.info(
            'Admin newsletter dispatch complete',
            extra={
                'admin_user_id': admin_user_id,
                'attempted': len(recipient_emails),
                'sent': sent_count,
                'failed': len(failed_recipients),
                'notifications': notification_count,
            },
        )
    except Exception:
        db.rollback()
        logger.exception('Admin newsletter background dispatch failed', extra={'admin_user_id': admin_user_id})
    finally:
        db.close()


@router.get('/users', response_model=AdminUsersResponse)
def list_users(
    search: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> AdminUsersResponse:
    _ = current_user

    query = select(User).order_by(
        case((User.role == UserRole.ADMIN, 0), else_=1),
        User.created_at.desc(),
    )
    normalized_search = (search or '').strip()
    if normalized_search:
        search_term = f'%{normalized_search}%'
        query = query.where(
            or_(
                User.email.ilike(search_term),
                User.full_name.ilike(search_term),
            )
        )
    users = db.scalars(query).all()

    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    admin_users = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN)) or 0

    return AdminUsersResponse(
        total_users=int(total_users),
        active_users=int(active_users),
        admin_users=int(admin_users),
        users=[AdminUserSummary.model_validate(user, from_attributes=True) for user in users],
    )


@router.patch('/users/{user_id}', response_model=AdminUserSummary)
def update_user_account(
    user_id: str,
    payload: AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> AdminUserSummary:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    if payload.role is None and payload.is_active is None and payload.full_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No account updates were provided',
        )

    if payload.role is not None:
        if user.id == current_user.id and payload.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='You cannot remove your own admin role',
            )

        if user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
            remaining_admins = db.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.ADMIN,
                    User.id != user.id,
                    User.is_active.is_(True),
                )
            ) or 0
            if remaining_admins < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='At least one active admin account is required',
                )
        user.role = payload.role

    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='You cannot deactivate your own account',
            )
        user.is_active = payload.is_active

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()

    db.commit()
    db.refresh(user)

    logger.info(
        'Admin account update',
        extra={
            'admin_user_id': current_user.id,
            'target_user_id': user.id,
            'updated_role': user.role.value,
            'updated_is_active': user.is_active,
        },
    )

    return AdminUserSummary.model_validate(user, from_attributes=True)


@router.post('/users/{user_id}/reset-password', response_model=AdminActionResponse)
def admin_reset_user_password(
    user_id: str,
    payload: AdminPasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> AdminActionResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    logger.warning(
        'Admin forced password reset',
        extra={'admin_user_id': current_user.id, 'target_user_id': user.id},
    )

    return AdminActionResponse(message=f'Password reset for {user.email}')


@router.get('/newsletter/subscribers', response_model=NewsletterSubscriberListResponse)
def list_newsletter_subscribers(
    search: str | None = Query(default=None, min_length=1, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> NewsletterSubscriberListResponse:
    _ = current_user

    query = select(NewsletterSubscriber).order_by(NewsletterSubscriber.subscribed_at.desc())
    normalized_search = (search or '').strip()
    if normalized_search:
        search_term = f'%{normalized_search}%'
        query = query.where(NewsletterSubscriber.email.ilike(search_term))

    subscribers = db.scalars(query).all()
    total_subscribers = db.scalar(select(func.count(NewsletterSubscriber.id))) or 0
    active_subscribers = db.scalar(
        select(func.count(NewsletterSubscriber.id)).where(NewsletterSubscriber.is_active.is_(True))
    ) or 0

    return NewsletterSubscriberListResponse(
        total_subscribers=int(total_subscribers),
        active_subscribers=int(active_subscribers),
        subscribers=[
            NewsletterSubscriberResponse.model_validate(subscriber, from_attributes=True)
            for subscriber in subscribers
        ],
    )


@router.get('/newsletter/users', response_model=NewsletterUserListResponse)
def list_newsletter_users(
    search: str | None = Query(default=None, min_length=1, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> NewsletterUserListResponse:
    _ = current_user

    query = select(User).order_by(
        case((User.role == UserRole.ADMIN, 0), else_=1),
        User.created_at.desc(),
    )
    normalized_search = (search or '').strip()
    if normalized_search:
        search_term = f'%{normalized_search}%'
        query = query.where(
            or_(
                User.email.ilike(search_term),
                User.full_name.ilike(search_term),
            )
        )

    users = db.scalars(query).all()
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0

    return NewsletterUserListResponse(
        total_users=int(total_users),
        active_users=int(active_users),
        users=[
            NewsletterUserTargetResponse.model_validate(user, from_attributes=True)
            for user in users
        ],
    )


@router.delete('/newsletter/subscribers/{subscriber_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_newsletter_subscriber(
    subscriber_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> None:
    subscriber = db.get(NewsletterSubscriber, subscriber_id)
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber not found')

    subscriber_email = subscriber.email
    db.delete(subscriber)
    db.commit()

    logger.info(
        'Newsletter subscriber deleted',
        extra={
            'admin_user_id': current_user.id,
            'subscriber_id': subscriber_id,
            'subscriber_email': subscriber_email,
        },
    )


@router.post('/newsletter/send', response_model=NewsletterSendResponse)
def send_newsletter_message(
    payload: NewsletterSendRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> NewsletterSendResponse:
    selected_subscriber_ids = [
        subscriber_id.strip()
        for subscriber_id in payload.subscriber_ids
        if subscriber_id.strip()
    ]
    selected_user_ids = [user_id.strip() for user_id in payload.user_ids if user_id.strip()]

    subscribers: list[NewsletterSubscriber] = []
    if selected_subscriber_ids:
        subscribers = db.scalars(
            select(NewsletterSubscriber).where(
                NewsletterSubscriber.id.in_(selected_subscriber_ids),
                NewsletterSubscriber.is_active.is_(True),
            )
        ).all()
    elif payload.send_email and not selected_user_ids:
        # Backward compatibility: no explicit selection means "all active subscribers".
        subscribers = db.scalars(
            select(NewsletterSubscriber).where(NewsletterSubscriber.is_active.is_(True))
        ).all()

    users: list[User] = []
    if selected_user_ids:
        users = db.scalars(
            select(User).where(
                User.id.in_(selected_user_ids),
                User.is_active.is_(True),
            )
        ).all()

    if payload.send_notifications and not selected_user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Select at least one active user to send notifications',
        )

    recipient_emails: list[str] = []
    if payload.send_email:
        recipient_emails = _unique_emails(
            [subscriber.email for subscriber in subscribers] + [user.email for user in users]
        )
        if recipient_emails:
            try:
                validate_email_configuration()
            except EmailDeliveryError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc

    notification_user_ids: list[str] = []
    if payload.send_notifications:
        notification_user_ids = sorted({user.id for user in users if user.notifications_enabled})

    attempted_count = len(recipient_emails)
    queued_notification_count = len(notification_user_ids)

    if attempted_count < 1 and queued_notification_count < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No eligible recipients found',
        )

    background_tasks.add_task(
        _send_newsletter_background,
        recipient_emails=recipient_emails,
        notification_user_ids=notification_user_ids,
        send_email=payload.send_email,
        send_notifications=payload.send_notifications,
        subject=payload.subject,
        message=payload.message,
        admin_user_id=current_user.id,
    )

    logger.info(
        'Newsletter dispatch queued',
        extra={
            'admin_user_id': current_user.id,
            'attempted': attempted_count,
            'notifications': queued_notification_count,
        },
    )

    if attempted_count and queued_notification_count:
        message = (
            f'Newsletter queued for {attempted_count} email recipient(s) '
            f'and {queued_notification_count} notification target(s)'
        )
    elif attempted_count:
        message = f'Newsletter queued for {attempted_count} email recipient(s)'
    else:
        message = f'Newsletter notifications queued for {queued_notification_count} user(s)'

    return NewsletterSendResponse(
        success=True,
        message=message,
        attempted=attempted_count,
        sent=0,
        failed=0,
        queued_notifications=queued_notification_count,
        failed_recipients=[],
    )
