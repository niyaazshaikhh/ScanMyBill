from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import require_roles
from app.models.newsletter import NewsletterSubscriber
from app.models.user import User, UserRole
from app.schemas.newsletter import (
    NewsletterResponse,
    NewsletterSend,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
)
from app.services.email_service import EmailDeliveryError, validate_email_configuration
from app.services.newsletter_service import (
    get_all_active_subscribers,
    send_newsletter,
    subscribe_email,
    unsubscribe_email,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _admin_guard(current_user: User = Depends(require_roles([UserRole.ADMIN]))) -> User:
    return current_user


@router.post('/subscribe', response_model=NewsletterSubscribeResponse)
def subscribe(
    payload: NewsletterSubscribeRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> NewsletterSubscribeResponse:
    normalized_email = str(payload.email).strip().lower()
    existing_subscriber = db.scalar(
        select(NewsletterSubscriber).where(func.lower(NewsletterSubscriber.email) == normalized_email)
    )

    if existing_subscriber and existing_subscriber.is_active:
        response.status_code = status.HTTP_200_OK
        return NewsletterSubscribeResponse(success=False, message='Already subscribed')

    _ = subscribe_email(db, str(payload.email))

    if existing_subscriber and not existing_subscriber.is_active:
        response.status_code = status.HTTP_200_OK
        return NewsletterSubscribeResponse(success=True, message='Subscription reactivated')

    response.status_code = status.HTTP_201_CREATED
    return NewsletterSubscribeResponse(success=True, message='Subscribed successfully')


@router.post('/unsubscribe', response_model=NewsletterResponse)
def unsubscribe(payload: NewsletterSubscribeRequest, db: Session = Depends(get_db)) -> NewsletterResponse:
    subscriber = unsubscribe_email(db, str(payload.email))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber not found')
    return NewsletterResponse.model_validate(subscriber, from_attributes=True)


@router.get('/unsubscribe', response_model=NewsletterResponse)
def unsubscribe_via_link(email: EmailStr = Query(...), db: Session = Depends(get_db)) -> NewsletterResponse:
    subscriber = unsubscribe_email(db, str(email))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber not found')
    return NewsletterResponse.model_validate(subscriber, from_attributes=True)


@router.get('/subscribers', response_model=list[NewsletterResponse])
def list_subscribers(
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> list[NewsletterResponse]:
    _ = current_user
    subscribers = db.scalars(select(NewsletterSubscriber).order_by(NewsletterSubscriber.subscribed_at.desc())).all()
    return [NewsletterResponse.model_validate(subscriber, from_attributes=True) for subscriber in subscribers]


def _send_newsletter_background(*, subject: str, message: str) -> None:
    db = SessionLocal()
    try:
        sent_count, failed_recipients = send_newsletter(db, subject, message)
        logger.info(
            'Newsletter background task complete',
            extra={
                'sent_count': sent_count,
                'failed_count': len(failed_recipients),
            },
        )
    except Exception:
        logger.exception('Newsletter background task failed')
    finally:
        db.close()


@router.post('/send', status_code=status.HTTP_202_ACCEPTED)
def send_newsletter_to_active_subscribers(
    payload: NewsletterSend,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_guard),
) -> dict[str, int | str | bool]:
    try:
        validate_email_configuration()
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    active_subscribers = get_all_active_subscribers(db)
    recipient_count = len(active_subscribers)

    if recipient_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No active subscribers found')

    background_tasks.add_task(
        _send_newsletter_background,
        subject=payload.subject,
        message=payload.message,
    )

    logger.info(
        'Newsletter queued',
        extra={
            'admin_user_id': current_user.id,
            'recipient_count': recipient_count,
        },
    )

    return {
        'success': True,
        'message': f'Newsletter queued for {recipient_count} subscriber(s)',
        'queued': recipient_count,
    }
