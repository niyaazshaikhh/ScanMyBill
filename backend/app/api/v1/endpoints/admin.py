import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.newsletter import (
    NewsletterSendRequest,
    NewsletterSendResponse,
    NewsletterSubscriberListResponse,
    NewsletterSubscriberResponse,
)
from app.schemas.admin import (
    AdminActionResponse,
    AdminPasswordResetRequest,
    AdminUserSummary,
    AdminUserUpdateRequest,
    AdminUsersResponse,
)
from app.services.newsletter_sender import NewsletterDeliveryError, send_newsletter_email_batch

router = APIRouter()
logger = logging.getLogger(__name__)


def _admin_guard(current_user: User = Depends(require_roles([UserRole.ADMIN]))) -> User:
    return current_user


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

    query = select(NewsletterSubscriber).order_by(NewsletterSubscriber.created_at.desc())
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


@router.post('/newsletter/send', response_model=NewsletterSendResponse)
def send_newsletter_message(
    payload: NewsletterSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> NewsletterSendResponse:
    selected_ids = [subscriber_id.strip() for subscriber_id in payload.subscriber_ids if subscriber_id.strip()]
    if not selected_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No recipients selected')

    subscribers = db.scalars(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.id.in_(selected_ids),
            NewsletterSubscriber.is_active.is_(True),
        )
    ).all()
    if not subscribers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No active subscribers found')

    recipient_emails = [subscriber.email for subscriber in subscribers]
    try:
        sent_count, failed_recipients = send_newsletter_email_batch(
            recipients=recipient_emails,
            subject=payload.subject,
            message=payload.message,
        )
    except NewsletterDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception('Newsletter send failed', extra={'admin_user_id': current_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Unable to send newsletter message',
        ) from exc

    attempted_count = len(recipient_emails)
    failed_count = len(failed_recipients)
    success = sent_count > 0 and failed_count == 0
    status_message = (
        f'Newsletter sent to {sent_count} recipient(s)'
        if failed_count == 0
        else f'Newsletter sent to {sent_count} recipient(s), {failed_count} failed'
    )

    logger.info(
        'Newsletter dispatch complete',
        extra={
            'admin_user_id': current_user.id,
            'attempted': attempted_count,
            'sent': sent_count,
            'failed': failed_count,
        },
    )

    return NewsletterSendResponse(
        success=success,
        message=status_message,
        attempted=attempted_count,
        sent=sent_count,
        failed=failed_count,
        failed_recipients=failed_recipients,
    )
