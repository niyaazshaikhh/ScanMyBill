from __future__ import annotations

from datetime import date


def financial_year_start(value: date) -> int:
    return value.year if value.month >= 4 else value.year - 1


def financial_quarter_number(value: date) -> int:
    financial_month_index = (value.month - 4) % 12
    return (financial_month_index // 3) + 1


def financial_quarter_label(value: date) -> str:
    return f'Q{financial_quarter_number(value)}'


def financial_half_label(value: date) -> str:
    financial_month_index = (value.month - 4) % 12
    return 'H1' if financial_month_index < 6 else 'H2'


def financial_quarter_bounds(value: date) -> tuple[date, date]:
    fy_start = financial_year_start(value)
    quarter_number = financial_quarter_number(value)
    quarter_start_month = 4 + ((quarter_number - 1) * 3)
    quarter_start_year = fy_start
    if quarter_start_month > 12:
        quarter_start_month -= 12
        quarter_start_year += 1
    period_start = date(quarter_start_year, quarter_start_month, 1)

    period_end_month = quarter_start_month + 3
    period_end_year = quarter_start_year
    if period_end_month > 12:
        period_end_month -= 12
        period_end_year += 1
    period_end = date(period_end_year, period_end_month, 1)
    return period_start, period_end


def to_folder_bucket(invoice_date: date, period: str) -> str:
    if period == 'monthly':
        return invoice_date.strftime('%b')
    if period == 'quarterly':
        return financial_quarter_label(invoice_date)
    if period == 'semi-annually':
        return financial_half_label(invoice_date)
    return str(invoice_date.year)


def matches_bucket(invoice_date: date, period: str, bucket: str) -> bool:
    return to_folder_bucket(invoice_date, period).lower() == bucket.lower()


def valid_period(period: str) -> str:
    allowed = {'monthly', 'quarterly', 'semi-annually', 'annually'}
    return period if period in allowed else 'monthly'
