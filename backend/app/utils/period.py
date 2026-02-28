from __future__ import annotations

from datetime import date


def to_folder_bucket(invoice_date: date, period: str) -> str:
    if period == 'monthly':
        return invoice_date.strftime('%b')
    if period == 'quarterly':
        return f"Q{((invoice_date.month - 1) // 3) + 1}"
    if period == 'semi-annually':
        return 'H1' if invoice_date.month <= 6 else 'H2'
    return str(invoice_date.year)


def matches_bucket(invoice_date: date, period: str, bucket: str) -> bool:
    return to_folder_bucket(invoice_date, period).lower() == bucket.lower()


def valid_period(period: str) -> str:
    allowed = {'monthly', 'quarterly', 'semi-annually', 'annually'}
    return period if period in allowed else 'monthly'