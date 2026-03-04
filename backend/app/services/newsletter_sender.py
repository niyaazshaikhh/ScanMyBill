from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings


class NewsletterDeliveryError(Exception):
    pass


def _smtp_sender_header() -> str:
    sender_email = (settings.smtp_sender_email or '').strip()
    if not sender_email:
        raise NewsletterDeliveryError('SMTP sender email is not configured')

    sender_name = (settings.smtp_sender_name or '').strip()
    if sender_name:
        return f'{sender_name} <{sender_email}>'
    return sender_email


def _validate_smtp_settings() -> None:
    smtp_host = (settings.smtp_host or '').strip()
    if not smtp_host:
        raise NewsletterDeliveryError('SMTP host is not configured')


def send_newsletter_email_batch(
    *,
    recipients: list[str],
    subject: str,
    message: str,
) -> tuple[int, list[str]]:
    _validate_smtp_settings()
    sender_header = _smtp_sender_header()

    smtp_host = (settings.smtp_host or '').strip()
    smtp_port = settings.smtp_port
    smtp_username = (settings.smtp_username or '').strip()
    smtp_password = (settings.smtp_password or '').strip()

    sent_count = 0
    failed_recipients: list[str] = []

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()

        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)

        for recipient in recipients:
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = sender_header
            msg['To'] = recipient
            msg.set_content(message)

            try:
                server.send_message(msg)
                sent_count += 1
            except Exception:
                failed_recipients.append(recipient)

    return sent_count, failed_recipients
