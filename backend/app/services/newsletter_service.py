from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from urllib.parse import quote_plus

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.newsletter import NewsletterSubscriber
from app.services.email_service import EmailMessagePayload, send_email_batch

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_NAME = 'newsletter.html'
UNSUBSCRIBE_BASE_URL = 'https://app.scanmybill.xyz/unsubscribe'


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _dedupe_recipients(recipient_emails: list[str]) -> dict[str, str]:
    deduped: dict[str, str] = {}
    for email in recipient_emails:
        cleaned = email.strip()
        if not cleaned:
            continue
        normalized = _normalize_email(cleaned)
        if normalized not in deduped:
            deduped[normalized] = cleaned
    return deduped


def _ensure_subscribed_at(db: Session, subscriber: NewsletterSubscriber) -> NewsletterSubscriber:
    if subscriber.subscribed_at is None:
        subscriber.subscribed_at = utc_now()
        db.commit()
        db.refresh(subscriber)
    return subscriber


def _template_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(APP_ROOT / 'templates')),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _unsubscribe_link(email: str) -> str:
    return f'{UNSUBSCRIBE_BASE_URL}?email={quote_plus(email)}'


def _render_newsletter_html(subject: str, message: str, unsubscribe_link: str) -> str:
    try:
        template = _template_environment().get_template(TEMPLATE_NAME)
        return template.render(
            subject=subject,
            message=message,
            unsubscribe_link=unsubscribe_link,
        )
    except TemplateNotFound:
        logger.error('Newsletter template missing at app/templates/%s. Using fallback template.', TEMPLATE_NAME)
    except Exception:
        logger.exception('Failed to render newsletter template. Using fallback template.')

    safe_subject = escape(subject)
    safe_message = escape(message).replace('\n', '<br/>')
    safe_unsubscribe = escape(unsubscribe_link)
    return (
        f'<html><body>'
        f'<h2>{safe_subject}</h2>'
        f'<p>{safe_message}</p>'
        f'<hr/>'
        f'<p>You received this email because you subscribed to ScanMyBill.</p>'
        f'<p>Unsubscribe: <a href="{safe_unsubscribe}">{safe_unsubscribe}</a></p>'
        f'</body></html>'
    )


def subscribe_email(db: Session, email: str) -> NewsletterSubscriber:
    normalized_email = _normalize_email(email)
    subscriber = db.scalar(
        select(NewsletterSubscriber).where(func.lower(NewsletterSubscriber.email) == normalized_email)
    )

    if subscriber:
        if not subscriber.is_active:
            subscriber.is_active = True
            subscriber.subscribed_at = utc_now()
            subscriber.unsubscribed_at = None
            db.commit()
            db.refresh(subscriber)
        return _ensure_subscribed_at(db, subscriber)

    subscriber = NewsletterSubscriber(
        email=normalized_email,
        is_active=True,
        subscribed_at=utc_now(),
    )
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return _ensure_subscribed_at(db, subscriber)


def unsubscribe_email(db: Session, email: str) -> NewsletterSubscriber | None:
    normalized_email = _normalize_email(email)
    subscriber = db.scalar(
        select(NewsletterSubscriber).where(func.lower(NewsletterSubscriber.email) == normalized_email)
    )
    if not subscriber:
        return None

    if subscriber.is_active:
        subscriber.is_active = False
        subscriber.unsubscribed_at = utc_now()
        db.commit()
        db.refresh(subscriber)

    return _ensure_subscribed_at(db, subscriber)


def get_all_active_subscribers(db: Session) -> list[NewsletterSubscriber]:
    subscribers = db.scalars(
        select(NewsletterSubscriber)
        .where(NewsletterSubscriber.is_active.is_(True))
        .order_by(NewsletterSubscriber.subscribed_at.desc())
    ).all()
    changed = False
    for subscriber in subscribers:
        if subscriber.subscribed_at is None:
            subscriber.subscribed_at = utc_now()
            changed = True
    if changed:
        db.commit()
        for subscriber in subscribers:
            db.refresh(subscriber)
    return subscribers


def send_newsletter(
    db: Session,
    subject: str,
    message: str,
    recipient_emails: list[str] | None = None,
) -> tuple[int, list[str]]:
    if recipient_emails:
        recipient_map = _dedupe_recipients(recipient_emails)
        if not recipient_map:
            logger.info('Newsletter send skipped: no valid recipient emails')
            return 0, []

        subscribers = db.scalars(
            select(NewsletterSubscriber)
            .where(
                NewsletterSubscriber.is_active.is_(True),
                func.lower(NewsletterSubscriber.email).in_(set(recipient_map.keys())),
            )
            .order_by(NewsletterSubscriber.subscribed_at.desc())
        ).all()
        active_subscribers: dict[str, NewsletterSubscriber] = {
            _normalize_email(subscriber.email): subscriber for subscriber in subscribers
        }
        for subscriber in subscribers:
            _ensure_subscribed_at(db, subscriber)
        target_emails = [recipient_map[email] for email in recipient_map]
    else:
        subscribers = get_all_active_subscribers(db)
        active_subscribers = {_normalize_email(subscriber.email): subscriber for subscriber in subscribers}
        target_emails = [subscriber.email for subscriber in subscribers]

    attempted = len(target_emails)

    if attempted == 0:
        logger.info('Newsletter send skipped: no active subscribers')
        return 0, []

    messages: list[EmailMessagePayload] = []
    for recipient_email in target_emails:
        normalized_email = _normalize_email(recipient_email)
        subscriber = active_subscribers.get(normalized_email)
        delivery_email = subscriber.email if subscriber else recipient_email
        unsubscribe_link = _unsubscribe_link(delivery_email)
        html_body = _render_newsletter_html(subject, message, unsubscribe_link)
        text_body = (
            f'{subject}\n\n'
            f'{message}\n\n'
            'You received this email because you subscribed to ScanMyBill.\n\n'
            f'Unsubscribe: {unsubscribe_link}'
        )
        messages.append(
            EmailMessagePayload(
                to_email=delivery_email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
        )

    sent_count, failed_recipients = send_email_batch(messages=messages, batch_size=50)

    logger.info(
        'Newsletter sent',
        extra={
            'attempted': attempted,
            'sent': sent_count,
            'failed': len(failed_recipients),
        },
    )
    if failed_recipients:
        logger.warning(
            'Newsletter failed recipients',
            extra={'failed_recipients': failed_recipients},
        )

    return sent_count, failed_recipients

