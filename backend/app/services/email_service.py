from __future__ import annotations

import os
import smtplib
import logging
from dataclasses import dataclass
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class EmailMessagePayload:
    to_email: str
    subject: str
    html_body: str
    text_body: str


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    sender_email: str
    sender_name: str
    use_tls: bool


def _normalize(value: str | None) -> str:
    return (value or '').strip()


def _smtp_settings() -> SMTPSettings:
    host = _normalize(os.getenv('SMTP_HOST') or settings.smtp_host)
    port_raw = _normalize(os.getenv('SMTP_PORT') or str(settings.smtp_port))
    username = _normalize(os.getenv('SMTP_USERNAME') or settings.smtp_username)
    password = _normalize(os.getenv('SMTP_PASSWORD') or settings.smtp_password)
    sender_email = _normalize(
        os.getenv('SMTP_SENDER_EMAIL')
        or os.getenv('SMTP_EMAIL')
        or settings.smtp_sender_email
        or username
    )
    sender_name = _normalize(os.getenv('SMTP_SENDER_NAME') or settings.smtp_sender_name)

    tls_raw = _normalize(os.getenv('SMTP_USE_TLS'))
    use_tls = settings.smtp_use_tls if not tls_raw else tls_raw.lower() in {'1', 'true', 'yes', 'on'}

    if not host:
        raise EmailDeliveryError('SMTP host is not configured')
    if not sender_email:
        raise EmailDeliveryError('SMTP sender email is not configured')
    if not password:
        raise EmailDeliveryError('SMTP password is not configured')

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise EmailDeliveryError('SMTP port must be a valid integer') from exc

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        sender_email=sender_email,
        sender_name=sender_name or 'ScanMyBill',
        use_tls=use_tls,
    )


def _build_message(payload: EmailMessagePayload, smtp: SMTPSettings) -> MIMEMultipart:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = payload.subject
    if smtp.sender_name:
        msg['From'] = f'{smtp.sender_name} <{smtp.sender_email}>'
    else:
        msg['From'] = smtp.sender_email
    msg['To'] = payload.to_email
    msg.attach(MIMEText(payload.text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(payload.html_body, 'html', 'utf-8'))
    return msg


def send_email_batch(
    *,
    messages: list[EmailMessagePayload],
    batch_size: int = 50,
) -> tuple[int, list[str]]:
    smtp = _smtp_settings()
    if not messages:
        return 0, []

    sent_count = 0
    failed_recipients: list[str] = []
    chunk_size = max(1, batch_size)

    for offset in range(0, len(messages), chunk_size):
        chunk = messages[offset : offset + chunk_size]
        try:
            with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
                if smtp.use_tls:
                    server.starttls()

                login_user = smtp.username or smtp.sender_email
                server.login(login_user, smtp.password)

                for payload in chunk:
                    try:
                        server.sendmail(
                            from_addr=smtp.sender_email,
                            to_addrs=[payload.to_email],
                            msg=_build_message(payload, smtp).as_string(),
                        )
                        sent_count += 1
                    except Exception:
                        failed_recipients.append(payload.to_email)
        except Exception:
            failed_recipients.extend([payload.to_email for payload in chunk])
            logger.exception(
                'SMTP batch delivery failed',
                extra={'batch_start': offset, 'batch_size': len(chunk)},
            )

    return sent_count, failed_recipients


def send_password_reset_email(email: str, reset_link: str) -> None:
    subject = 'Reset your ScanMyBill password'
    text_body = (
        'Hello,\n\n'
        'You requested to reset your ScanMyBill password.\n\n'
        'Click the link below to reset your password:\n\n'
        f'{reset_link}\n\n'
        'This link will expire in 30 minutes.\n\n'
        'If you did not request this, you can ignore this email.'
    )
    safe_link = escape(reset_link, quote=True)
    html_body = (
        '<html><body>'
        '<p>Hello,</p>'
        '<p>You requested to reset your ScanMyBill password.</p>'
        '<p>Click the link below to reset your password:</p>'
        f'<p><a href="{safe_link}">{safe_link}</a></p>'
        '<p>This link will expire in 30 minutes.</p>'
        '<p>If you did not request this, you can ignore this email.</p>'
        '</body></html>'
    )

    sent_count, failed_recipients = send_email_batch(
        messages=[
            EmailMessagePayload(
                to_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
        ],
        batch_size=1,
    )
    if sent_count != 1 or failed_recipients:
        raise EmailDeliveryError('Password reset email delivery failed')


def validate_email_configuration() -> None:
    _smtp_settings()

