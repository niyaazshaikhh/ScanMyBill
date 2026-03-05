from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from app.core.config import settings


def _smtp_settings() -> tuple[str, int, str, str]:
    smtp_host = (os.getenv('SMTP_HOST') or settings.smtp_host or '').strip()
    smtp_port_raw = (os.getenv('SMTP_PORT') or str(settings.smtp_port)).strip()
    smtp_email = (
        os.getenv('SMTP_EMAIL')
        or settings.smtp_sender_email
        or settings.smtp_username
        or ''
    ).strip()
    smtp_password = (os.getenv('SMTP_PASSWORD') or settings.smtp_password or '').strip()

    if not smtp_host:
        raise ValueError('SMTP_HOST is not configured')
    if not smtp_email:
        raise ValueError('SMTP_EMAIL is not configured')
    if not smtp_password:
        raise ValueError('SMTP_PASSWORD is not configured')

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise ValueError('SMTP_PORT must be a valid integer') from exc

    return smtp_host, smtp_port, smtp_email, smtp_password


def send_email(to_email: str, subject: str, html_body: str) -> None:
    smtp_host, smtp_port, smtp_email, smtp_password = _smtp_settings()

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = smtp_email
    msg['To'] = to_email
    msg.set_content('This email contains HTML content. Please use an HTML compatible email client.')
    msg.add_alternative(html_body, subtype='html')

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.send_message(msg)
