from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceType
from app.models.notification import Notification, NotificationCategory
from app.utils.period import financial_quarter_bounds, financial_quarter_number, financial_year_start


def create_notification(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None = None,
    category: NotificationCategory = NotificationCategory.ACTIVITY,
    dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key:
        existing_id = db.scalar(
            select(Notification.id).where(
                Notification.owner_id == user_id,
                Notification.dedupe_key == dedupe_key,
            )
        )
        if existing_id:
            return None

    notification = Notification(
        owner_id=user_id,
        category=category,
        title=title.strip()[:120] or 'Notification',
        message=message.strip() or title.strip() or 'Notification',
        route=route.strip()[:255] if route else None,
        dedupe_key=dedupe_key.strip()[:120] if dedupe_key else None,
        is_read=False,
    )
    db.add(notification)
    return notification


def _gst_payable_for_period(
    db: Session,
    *,
    user_id: str,
    period_start: date,
    period_end: date,
) -> float:
    sums = dict(
        db.execute(
            select(Invoice.type, func.coalesce(func.sum(Invoice.gst_amount), 0.0))
            .where(
                Invoice.owner_id == user_id,
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date < period_end,
            )
            .group_by(Invoice.type)
        ).all()
    )
    gst_collected = float(sums.get(InvoiceType.SALES, 0.0) or 0.0)
    gst_paid = float(sums.get(InvoiceType.PURCHASE, 0.0) or 0.0)
    return round(gst_collected - gst_paid, 2)


def _upsert_reminder_notification(
    db: Session,
    *,
    user_id: str,
    dedupe_key: str,
    title: str,
    message: str,
    route: str = '/dashboard',
) -> Notification | None:
    existing_notification = db.scalar(
        select(Notification).where(
            Notification.owner_id == user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )

    if existing_notification:
        has_change = False
        if existing_notification.category != NotificationCategory.ALERT:
            existing_notification.category = NotificationCategory.ALERT
            has_change = True
        if existing_notification.title != title:
            existing_notification.title = title
            has_change = True
        if existing_notification.message != message:
            existing_notification.message = message
            has_change = True
        if existing_notification.route != route:
            existing_notification.route = route
            has_change = True
        return existing_notification if has_change else None

    return create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.ALERT,
        title=title,
        message=message,
        route=route,
        dedupe_key=dedupe_key,
    )


def ensure_monthly_gst_payable_notification(db: Session, *, user_id: str) -> Notification | None:
    today = date.today()
    period_start = date(today.year, today.month, 1)
    if today.month == 12:
        period_end = date(today.year + 1, 1, 1)
    else:
        period_end = date(today.year, today.month + 1, 1)

    gst_payable = _gst_payable_for_period(
        db,
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
    )
    month_label = period_start.strftime('%b %Y')
    dedupe_key = f'gst-payable-monthly-reminder-{today:%Y-%m-%d}'
    title = 'Monthly GST Payable'
    message = f'GST payable for {month_label} is Rs {gst_payable:.2f}.'

    return _upsert_reminder_notification(
        db,
        user_id=user_id,
        dedupe_key=dedupe_key,
        title=title,
        message=message,
    )


def ensure_quarterly_gst_payable_notification(db: Session, *, user_id: str) -> Notification | None:
    today = date.today()
    quarter_number = financial_quarter_number(today)
    period_start, period_end = financial_quarter_bounds(today)
    fy_start = financial_year_start(today)

    gst_payable = _gst_payable_for_period(
        db,
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
    )
    dedupe_key = f'gst-payable-quarterly-reminder-{today:%Y-%m-%d}'
    title = 'Quarterly GST Payable'
    message = f'GST payable for Q{quarter_number} FY {fy_start}-{fy_start + 1} is Rs {gst_payable:.2f}.'

    return _upsert_reminder_notification(
        db,
        user_id=user_id,
        dedupe_key=dedupe_key,
        title=title,
        message=message,
    )
