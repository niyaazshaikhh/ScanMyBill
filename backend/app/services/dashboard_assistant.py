from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.invoice import Invoice
from app.services.analytics import build_dashboard_summary
from app.utils.period import valid_period


class DashboardAssistantError(RuntimeError):
    pass


def generate_dashboard_assistant_reply(
    *,
    db: Session,
    user_id: str,
    question: str,
    period: str | None = None,
    financial_year_start: int | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    api_key = (settings.azure_openai_api_key or '').strip()
    if not api_key:
        raise DashboardAssistantError('AZURE_OPENAI_API_KEY is not configured.')

    azure_endpoint = (settings.azure_openai_endpoint or '').strip()
    if not azure_endpoint:
        raise DashboardAssistantError('AZURE_OPENAI_ENDPOINT is not configured.')

    model_name = (settings.azure_openai_deployment or settings.openai_model or '').strip()
    if not model_name:
        raise DashboardAssistantError('AZURE_OPENAI_DEPLOYMENT (or OPENAI_MODEL fallback) is not configured.')

    cleaned_question = question.strip()
    if not cleaned_question:
        raise DashboardAssistantError('Question cannot be empty.')

    normalized_period = valid_period(period or 'monthly')
    selected_financial_year = financial_year_start or _current_financial_year_start()
    dashboard_summary = build_dashboard_summary(
        db=db,
        user_id=user_id,
        period=normalized_period,
        financial_year_start=selected_financial_year,
    )

    current_month_invoice_count = _current_month_invoice_count(db=db, user_id=user_id)
    current_month_label = date.today().strftime('%B %Y')

    context_lines = [
        f'Selected period: {normalized_period}',
        f'Selected financial year start: {selected_financial_year}',
        f'Current month: {current_month_label}',
        f'Current month invoice count: {current_month_invoice_count}',
        f'Total sales: Rs {dashboard_summary.total_sales:.2f}',
        f'Total purchases: Rs {dashboard_summary.total_purchases:.2f}',
        f'GST collected: Rs {dashboard_summary.gst_collected:.2f}',
        f'GST paid: Rs {dashboard_summary.gst_paid:.2f}',
        f'GST payable: Rs {dashboard_summary.gst_payable:.2f}',
    ]
    trend_lines = [
        f'- {point.label}: Sales Rs {point.sales:.2f}, Purchases Rs {point.purchases:.2f}'
        for point in dashboard_summary.trend
    ]
    trend_context = '\n'.join(trend_lines) if trend_lines else '- No trend buckets available'

    messages: list[dict[str, str]] = [
        {
            'role': 'system',
            'content': (
                'You are ScanMyBill AI Assistant for Indian MSMEs. '
                'Answer using only the supplied dashboard context and user question. '
                'Keep answers concise (2-4 short sentences), actionable, and professional. '
                'Use "Rs" for currency values. '
                'If data is unavailable, state that clearly and avoid guessing.'
            ),
        },
        {
            'role': 'user',
            'content': 'Dashboard context:\n'
            + '\n'.join(context_lines)
            + '\nTrend buckets:\n'
            + trend_context,
        },
    ]

    for item in (history or [])[-8:]:
        role = (item.get('role') or '').strip().lower()
        content = (item.get('content') or '').strip()
        if role not in {'assistant', 'user'} or not content:
            continue
        messages.append({'role': role, 'content': content[:2000]})

    messages.append({'role': 'user', 'content': cleaned_question})

    completion = _request_chat_completion(
        messages=messages,
        model_name=model_name,
        api_key=api_key,
        azure_endpoint=azure_endpoint,
    )
    answer = _extract_message_text(completion).strip()
    if not answer:
        raise DashboardAssistantError('AI assistant returned an empty response.')

    return answer, model_name


def _current_financial_year_start() -> int:
    today = date.today()
    return today.year if today.month >= 4 else today.year - 1


def _current_month_invoice_count(*, db: Session, user_id: str) -> int:
    today = date.today()
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1)
    else:
        month_end = date(today.year, today.month + 1, 1)

    count = db.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.owner_id == user_id,
            Invoice.invoice_date >= month_start,
            Invoice.invoice_date < month_end,
        )
    )
    return int(count or 0)


def _request_chat_completion(
    *,
    messages: list[dict[str, str]],
    model_name: str,
    api_key: str,
    azure_endpoint: str,
) -> Any:
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=azure_endpoint,
        api_version=settings.azure_openai_api_version,
    )

    request_payload_base: dict[str, Any] = {
        'model': model_name,
        'messages': messages,
        'temperature': 0.2,
    }

    for token_param in ('max_completion_tokens', 'max_tokens'):
        request_payload = dict(request_payload_base)
        request_payload[token_param] = 360
        try:
            return client.chat.completions.create(**request_payload)
        except Exception as exc:
            if _is_incompatible_param_error(exc, token_param):
                continue
            raise

    return client.chat.completions.create(**request_payload_base)


def _is_incompatible_param_error(exc: Exception, param_name: str) -> bool:
    message = str(exc).lower()
    normalized_param = param_name.lower()
    unsupported_markers = ('unsupported parameter', 'unsupported value', 'does not support')
    mentions_param = (
        f"'{normalized_param}'" in message
        or f'"{normalized_param}"' in message
        or normalized_param in message
    )
    return mentions_param and any(marker in message for marker in unsupported_markers)


def _extract_message_text(completion: Any) -> str:
    choices = getattr(completion, 'choices', None) or []
    if not choices:
        return ''

    first_choice = choices[0]
    message = getattr(first_choice, 'message', None)
    if message is None:
        return ''

    content = getattr(message, 'content', '')
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        extracted: list[str] = []
        for item in content:
            text: str | None = None
            if isinstance(item, dict):
                raw_text = item.get('text')
                if isinstance(raw_text, str):
                    text = raw_text
            else:
                raw_text = getattr(item, 'text', None)
                if isinstance(raw_text, str):
                    text = raw_text
            if text:
                extracted.append(text)
        return '\n'.join(extracted)

    return str(content)
