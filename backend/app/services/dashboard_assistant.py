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


def _normalize_user_role(user_role: str | None) -> str:
    role = (user_role or '').strip().lower()
    return 'admin' if role == 'admin' else 'user'


def _build_navigation_guide(user_role: str) -> list[str]:
    lines = [
        '- Dashboard: Sidebar > Dashboard (/dashboard) for KPI cards, GST summary, and charts.',
        '- Upload bill: Dashboard > Bill Processing Flow card, or use the orange floating plus quick-upload button.',
        '- SMB AI Assistant: click the blue sparkles floating button on Dashboard.',
        '- GST invoices: Sidebar > Invoices (/invoices).',
        '- Delivery challans: Invoices page > Challan Type switch, or go to /invoices/delivery-challan.',
        '- Client analytics: Sidebar > Client Analytics (/client-analytics).',
        '- Client master list: Sidebar > Clients (/clients).',
        '- Create GST invoice: Sidebar > Create (/create).',
        '- Create delivery challan: Create page > Challan Type switch, or go to /create/delivery-challan.',
        '- Settings: Sidebar > Settings (/settings).',
        '- Personal/business details: Settings > Personal Details (/settings/personal_details).',
        '- HSN/SAC Master List: from Create Invoice page click "HSN Master List" (/hsn-sac-master-list).',
        '- About Us opens a popup modal from header/user menu and does not navigate to a separate route.',
        '- Header global search can jump to invoices, challans, clients, and settings routes instantly.',
    ]

    if user_role == 'admin':
        lines.extend(
            [
                '- Admin Console: Sidebar > Admin (/admin).',
                '- Newsletter and notifications: Sidebar > Newsletter and Notifications (/newsletter).',
            ]
        )
    else:
        lines.append('- Admin and Newsletter routes are not available for standard users.')

    return lines


def generate_dashboard_assistant_reply(
    *,
    db: Session,
    user_id: str,
    question: str,
    user_role: str | None = None,
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
    normalized_role = _normalize_user_role(user_role)
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
        f'User role: {normalized_role}',
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
    navigation_lines = _build_navigation_guide(normalized_role)
    trend_context = '\n'.join(trend_lines) if trend_lines else '- No trend buckets available'

    messages: list[dict[str, str]] = [
        {
            'role': 'system',
            'content': (
                'You are ScanMyBill AI Assistant for Indian MSMEs. '
                'Answer using only the supplied dashboard context, navigation guide, and user question. '
                'Keep answers concise (2-4 short sentences), actionable, and professional. '
                'Use "Rs" for currency values. '
                'For navigation questions, provide exact click steps in the format "Sidebar > Section" '
                'or "Header > Control", and include route paths in parentheses. '
                'If a page/action is role-restricted, say that clearly. '
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
        {
            'role': 'user',
            'content': 'ScanMyBill navigation guide:\n' + '\n'.join(navigation_lines),
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
    }

    request_variants: tuple[dict[str, Any], ...] = (
        {'temperature': 0.2, 'max_completion_tokens': 360},
        {'temperature': 0.2, 'max_tokens': 360},
        {'temperature': 0.2},
        {'max_completion_tokens': 360},
        {'max_tokens': 360},
        {},
    )

    last_error: Exception | None = None
    for optional_params in request_variants:
        request_payload = dict(request_payload_base)
        request_payload.update(optional_params)
        try:
            return client.chat.completions.create(**request_payload)
        except Exception as exc:
            last_error = exc
            if _has_incompatible_optional_params(exc, optional_params):
                continue
            raise

    if last_error is not None:
        raise last_error
    return client.chat.completions.create(**request_payload_base)


def _has_incompatible_optional_params(exc: Exception, optional_params: dict[str, Any]) -> bool:
    if not optional_params:
        return False
    return any(
        _is_incompatible_param_error(exc, param_name)
        for param_name in optional_params.keys()
    )


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
