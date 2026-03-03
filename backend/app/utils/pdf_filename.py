from __future__ import annotations

from datetime import date


def _financial_year_label(bill_date: date) -> str:
    start_year = bill_date.year if bill_date.month >= 4 else bill_date.year - 1
    return f'{start_year}-{(start_year + 1) % 100:02d}'


def _extract_document_number(document_number: str) -> str:
    candidate = (document_number or '').strip()
    if '/' in candidate:
        candidate = candidate.rsplit('/', 1)[-1].strip()

    sanitized = ''.join(char for char in candidate if char.isalnum() or char in {'-', '_'})
    return sanitized or '0'


def _sanitize_client_name(client_name: str | None) -> str:
    source = (client_name or '').strip()
    sanitized = ''.join(char for char in source if char.isalnum() or char in {'-', '_'})
    return sanitized or 'Client'


def build_bill_pdf_filename(*, bill_date: date, document_number: str, client_name: str | None) -> str:
    year_label = _financial_year_label(bill_date)
    number_label = _extract_document_number(document_number)
    client_label = _sanitize_client_name(client_name)
    return f'{year_label}_{number_label}-{client_label}.pdf'

