from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_MIME = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/webp',
}
_MAX_PDF_PAGES = 3
_MAX_TOKENS = 3000
_DEBUG_RESPONSE_TEXT_LIMIT = 12_000
_RESPONSE_SCHEMA_NAME = 'bill_extraction'
_MAX_IMAGE_SIDE = 1800
_QUALITY_ACCEPT_THRESHOLD = 45
_GSTIN_PATTERN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')


def _get_resample_filter() -> Any:
    try:
        return Image.Resampling.LANCZOS  # Pillow>=9
    except AttributeError:
        return Image.LANCZOS


def _detect_mime(payload: bytes, file_path: Path) -> str | None:
    if payload.startswith(b'%PDF-'):
        return 'application/pdf'
    if payload.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if payload.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if len(payload) >= 12 and payload[:4] == b'RIFF' and payload[8:12] == b'WEBP':
        return 'image/webp'

    suffix = file_path.suffix.lower()
    if suffix == '.pdf':
        return 'application/pdf'
    if suffix == '.png':
        return 'image/png'
    if suffix in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if suffix == '.webp':
        return 'image/webp'
    return None


def _encode_pil_to_jpeg_data_url(image: Image.Image) -> str | None:
    try:
        resized = image.convert('RGB')
        resized.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), _get_resample_filter())
        buffer = io.BytesIO()
        resized.save(buffer, format='JPEG', quality=85, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/jpeg;base64,{encoded}'
    except Exception:
        return None


def _build_image_blocks(file_path: Path, mime_type: str, payload: bytes) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    if mime_type == 'application/pdf':
        try:
            pages = convert_from_path(str(file_path), first_page=1, last_page=_MAX_PDF_PAGES)
        except Exception:
            return blocks

        for page in pages:
            data_url = _encode_pil_to_jpeg_data_url(page)
            if data_url:
                blocks.append({'type': 'image_url', 'image_url': {'url': data_url}})
        return blocks

    if mime_type.startswith('image/'):
        try:
            with Image.open(file_path) as image:
                data_url = _encode_pil_to_jpeg_data_url(image)
        except Exception:
            data_url = None

        if not data_url:
            normalized_mime = 'image/jpeg' if mime_type in {'image/jpg', 'image/jpeg'} else mime_type
            encoded = base64.b64encode(payload).decode('ascii')
            data_url = f'data:{normalized_mime};base64,{encoded}'

        blocks.append({'type': 'image_url', 'image_url': {'url': data_url}})

    return blocks


def _system_prompt() -> str:
    return (
        'You are a financial document extraction engine for Indian invoices and delivery challans. '
        'Return only valid JSON with no markdown or commentary. '
        'Detect document_type strictly as gst_invoice or delivery_challan. '
        'Detect bill type as sales or purchase using the provided company name with highest priority. '
        'Classification priority rule: '
        'if buyer/bill to/consignee matches company name, classify purchase; '
        'if seller/supplier/issuer matches company name, classify sales. '
        'Extract fields by semantic meaning, not position or layout. '
        'Possible labels: invoice_number (Invoice No, Bill No, Estimate No, Invoice #), '
        'invoice_date (Date, Invoice Date, Estimate Date), '
        'gst_number (GSTIN, GSTIN/UIN, GST No), '
        'total_amount (Total, Net Amount, Grand Total, Amount Chargeable), '
        'subtotal (Taxable Value, Sub Total), '
        'gst_amount (IGST, CGST+SGST, Total Tax). '
        'GSTIN must match this exact pattern: '
        '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$. '
        'Never output company names or addresses as GST numbers. If GSTIN is missing or invalid, return null. '
        'For sales invoices, choose buyer GSTIN. For purchase invoices, choose seller/vendor GSTIN. '
        'For totals: never use item rate/qty/unit price as totals; prioritize summary section totals. '
        'If CGST and SGST are available, set gst_amount=CGST+SGST and total_amount=subtotal+gst_amount when needed. '
        'Validate that total_amount is greater than individual item rates. '
        'If unsure for any field, return null. Keep all expected keys present.'
    )


def _build_user_instruction(company_name: str | None, ocr_text: str | None) -> str:
    normalized_company = (company_name or '').strip() or 'UNKNOWN'
    compact_ocr = ' '.join((ocr_text or '').split()).strip()
    clipped_ocr = compact_ocr[:6000] if compact_ocr else ''
    return (
        'Extract structured bill information from this document. '
        f'Settings company name from /settings/personal_details: {normalized_company}. '
        'Use this company name first when deciding transaction_type and bill_type. '
        'Always include transaction_type and bill_type keys with value sales or purchase. '
        'For gst_invoice include invoice_number, invoice_date, seller/seller_name, buyer/buyer_name, amounts, and items. '
        'For delivery_challan include challan_number, order_number, challan_date, from_party, to_party, subtotal, and items. '
        'Output JSON only with fields needed for gst_invoice or delivery_challan. '
        'Use null for missing scalar fields and [] for missing item lists. '
        f'OCR_TEXT_FALLBACK: {clipped_ocr or "N/A"}'
    )


def _bill_extraction_json_schema() -> dict[str, Any]:
    return {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'document_type': {'type': 'string', 'enum': ['gst_invoice', 'delivery_challan']},
            'bill_type': {'type': 'string', 'enum': ['sales', 'purchase']},
            'gst_invoice': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'invoice_number': {'type': ['string', 'null']},
                    'invoice_date': {'type': ['string', 'null']},
                    'seller_name': {'type': ['string', 'null']},
                    'buyer_name': {'type': ['string', 'null']},
                    'place_of_supply': {'type': ['string', 'null']},
                    'place_of_supply_code': {'type': ['string', 'null']},
                    'gst_number': {'type': ['string', 'null']},
                    'subtotal': {'type': ['number', 'null']},
                    'gst_amount': {'type': ['number', 'null']},
                    'total_amount': {'type': ['number', 'null']},
                    'notes': {'type': ['string', 'null']},
                    'items': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'description': {'type': ['string', 'null']},
                                'hsn_sac': {'type': ['string', 'null']},
                                'quantity': {'type': ['number', 'null']},
                                'rate': {'type': ['number', 'null']},
                                'tax_rate': {'type': ['number', 'null']},
                            },
                            'required': ['description', 'hsn_sac', 'quantity', 'rate', 'tax_rate'],
                        },
                    },
                },
                'required': [
                    'invoice_number',
                    'invoice_date',
                    'seller_name',
                    'buyer_name',
                    'place_of_supply',
                    'place_of_supply_code',
                    'gst_number',
                    'subtotal',
                    'gst_amount',
                    'total_amount',
                    'notes',
                    'items',
                ],
            },
            'delivery_challan': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'challan_number': {'type': ['number', 'null']},
                    'order_number': {'type': ['string', 'null']},
                    'challan_date': {'type': ['string', 'null']},
                    'from_party': {'type': ['string', 'null']},
                    'to_party': {'type': ['string', 'null']},
                    'subtotal': {'type': ['number', 'null']},
                    'notes': {'type': ['string', 'null']},
                    'items': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'description': {'type': ['string', 'null']},
                                'quantity': {'type': ['number', 'null']},
                                'rate': {'type': ['number', 'null']},
                            },
                            'required': ['description', 'quantity', 'rate'],
                        },
                    },
                },
                'required': [
                    'challan_number',
                    'order_number',
                    'challan_date',
                    'from_party',
                    'to_party',
                    'subtotal',
                    'notes',
                    'items',
                ],
            },
            'warnings': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['document_type', 'bill_type', 'gst_invoice', 'delivery_challan', 'warnings'],
    }


def _strict_json_response_format() -> dict[str, Any]:
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': _RESPONSE_SCHEMA_NAME,
            'strict': True,
            'schema': _bill_extraction_json_schema(),
        },
    }


def _validate_document_type(data: dict[str, Any]) -> dict[str, Any]:
    normalized_document_type = _normalize_document_type_value(data)
    if normalized_document_type is None:
        return {'error': 'Model returned unknown document type'}
    data['document_type'] = normalized_document_type
    return data


def _extract_content_text(completion: Any) -> str:
    try:
        choice = completion.choices[0]
        message = choice.message
        content = message.content
    except Exception:
        return ''

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get('text'), str):
                chunks.append(part['text'])
        return ''.join(chunks)
    return ''


def safe_json_parse(raw_content: str) -> dict[str, Any] | None:
    candidate = (raw_content or '').strip()
    if not candidate:
        return None

    cleaned = re.sub(r'^```(?:json)?\s*', '', candidate, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    if cleaned.lower().startswith('json'):
        cleaned = cleaned[4:].lstrip(' \t\r\n:')

    attempts = [cleaned]
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start >= 0 and end > start:
        attempts.append(cleaned[start : end + 1])

    for attempt in attempts:
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'[^0-9.\-]', '', value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _score_extraction_payload(parsed: dict[str, Any] | None) -> int:
    if not isinstance(parsed, dict):
        return -1

    score = 0
    document_type = _normalize_document_type_value(parsed)
    if document_type:
        score += 12

    bill_type = str(parsed.get('bill_type') or '').strip().lower()
    if bill_type in {'sales', 'purchase'}:
        score += 8

    gst_invoice = parsed.get('gst_invoice') if isinstance(parsed.get('gst_invoice'), dict) else {}
    delivery_challan = (
        parsed.get('delivery_challan') if isinstance(parsed.get('delivery_challan'), dict) else {}
    )

    if document_type == 'gst_invoice':
        fields = [
            'invoice_number',
            'invoice_date',
            'seller_name',
            'buyer_name',
            'place_of_supply',
            'place_of_supply_code',
            'notes',
        ]
        score += sum(4 for field in fields if _has_text(gst_invoice.get(field)))
        gst_number = str(gst_invoice.get('gst_number') or '').strip().upper()
        if _GSTIN_PATTERN.match(gst_number):
            score += 8
        for amount_field in ('subtotal', 'gst_amount', 'total_amount'):
            value = _to_float(gst_invoice.get(amount_field))
            if value is not None and value > 0:
                score += 6
        items = gst_invoice.get('items') if isinstance(gst_invoice.get('items'), list) else []
        if items:
            score += min(len(items), 5) * 2

    if document_type == 'delivery_challan':
        fields = [
            'challan_number',
            'order_number',
            'challan_date',
            'from_party',
            'to_party',
            'notes',
        ]
        score += sum(4 for field in fields if _has_text(delivery_challan.get(field)) or delivery_challan.get(field) is not None)
        subtotal = _to_float(delivery_challan.get('subtotal'))
        if subtotal is not None and subtotal > 0:
            score += 6
        items = delivery_challan.get('items') if isinstance(delivery_challan.get('items'), list) else []
        if items:
            score += min(len(items), 5) * 2

    return score


def _normalize_document_type_value(data: dict[str, Any]) -> str | None:
    candidates = [
        data.get('document_type'),
        data.get('type'),
        data.get('doc_type'),
        data.get('bill_type'),
    ]
    for candidate in candidates:
        normalized = str(candidate or '').strip().lower().replace(' ', '_')
        if normalized in {'gst_invoice', 'invoice', 'tax_invoice', 'purchase_bill', 'estimate'}:
            return 'gst_invoice'
        if normalized in {'delivery_challan', 'challan', 'delivery_note'}:
            return 'delivery_challan'

    challan_markers = {'challan_number', 'order_number', 'challan_date', 'from_party', 'to_party'}
    invoice_markers = {'invoice_number', 'invoice_date', 'seller', 'buyer', 'gst_number'}
    if any(key in data and data.get(key) not in (None, '', []) for key in challan_markers):
        return 'delivery_challan'
    if any(key in data and data.get(key) not in (None, '', []) for key in invoice_markers):
        return 'gst_invoice'
    return None


def _format_model_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    message = re.sub(r'\s+', ' ', message)
    return message[:300]


def _clip_debug_text(value: str, limit: int = _DEBUG_RESPONSE_TEXT_LIMIT) -> str:
    cleaned = (value or '').strip()
    if len(cleaned) <= limit:
        return cleaned
    omitted = len(cleaned) - limit
    return f'{cleaned[:limit]}... [truncated {omitted} chars]'


def _new_debug_trace() -> dict[str, Any]:
    return {
        'provider': None,
        'model': None,
        'configured_model': settings.openai_model,
        'openai_base_url': settings.openai_base_url,
        'azure_endpoint': settings.azure_openai_endpoint,
        'azure_deployment': settings.azure_openai_deployment,
        'api_version': settings.azure_openai_api_version,
        'providers_configured': _build_provider_sequence(),
        'attempts': [],
    }


def _append_debug_attempt(
    trace: dict[str, Any],
    *,
    provider: str,
    model: str,
    mode: str,
    status: str,
    response_text: str | None = None,
    error: str | None = None,
    image_blocks_count: int | None = None,
) -> None:
    attempts = trace.setdefault('attempts', [])
    if not isinstance(attempts, list):
        attempts = []
        trace['attempts'] = attempts

    payload: dict[str, Any] = {
        'provider': provider,
        'model': model,
        'mode': mode,
        'status': status,
    }
    if image_blocks_count is not None:
        payload['image_blocks_count'] = image_blocks_count
    if response_text:
        payload['response_text'] = _clip_debug_text(response_text)
    if error:
        payload['error'] = error
    attempts.append(payload)


def _with_debug(payload: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result['__ai_debug'] = trace
    return result


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


def _request_completion(
    client: Any,
    model_name: str,
    company_name: str | None,
    ocr_text: str | None,
    image_blocks: list[dict[str, Any]],
) -> Any:
    request_payload_base = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': _system_prompt()},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': _build_user_instruction(company_name, ocr_text)},
                    *image_blocks,
                ],
            },
        ],
        'response_format': _strict_json_response_format(),
    }

    attempts: list[tuple[str, bool]] = [
        ('max_completion_tokens', True),
        ('max_completion_tokens', False),
        ('max_tokens', True),
        ('max_tokens', False),
    ]
    last_compat_error: Exception | None = None

    for token_param, include_temperature in attempts:
        request_payload = dict(request_payload_base)
        request_payload[token_param] = _MAX_TOKENS
        if include_temperature:
            request_payload['temperature'] = 0

        try:
            return client.chat.completions.create(**request_payload)
        except Exception as exc:
            token_unsupported = _is_incompatible_param_error(exc, token_param)
            temperature_unsupported = include_temperature and _is_incompatible_param_error(exc, 'temperature')
            if token_unsupported or temperature_unsupported:
                last_compat_error = exc
                continue
            raise

    if last_compat_error:
        raise last_compat_error
    raise RuntimeError('Failed to request completion')


def _build_provider_sequence() -> list[str]:
    providers: list[str] = []
    if settings.azure_openai_endpoint and settings.azure_openai_deployment and (
        settings.azure_openai_api_key or settings.openai_api_key
    ):
        providers.append('azure_openai')
    if settings.openai_api_key:
        providers.append('openai')
    return providers


def _build_provider_client(provider: str) -> tuple[Any, str]:
    if provider == 'azure_openai':
        from openai import AzureOpenAI

        endpoint = settings.azure_openai_endpoint
        deployment = settings.azure_openai_deployment
        api_key = settings.azure_openai_api_key or settings.openai_api_key
        if not endpoint or not deployment or not api_key:
            raise ValueError('Azure OpenAI configuration missing')
        client = AzureOpenAI(
            api_version=settings.azure_openai_api_version,
            azure_endpoint=endpoint,
            api_key=api_key,
        )
        return client, deployment

    if provider == 'openai':
        from openai import OpenAI

        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError('OpenAI configuration missing')
        base_url = (settings.openai_base_url or '').strip()
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
        return client, settings.openai_model

    raise ValueError(f'Unsupported AI provider: {provider}')


def _request_with_provider(
    *,
    provider: str,
    model_name: str,
    client: Any,
    image_blocks: list[dict[str, Any]],
    company_name: str | None,
    ocr_text: str | None,
    debug_trace: dict[str, Any],
) -> tuple[Any, str]:
    try:
        completion = _request_completion(
            client=client,
            model_name=model_name,
            company_name=company_name,
            ocr_text=ocr_text,
            image_blocks=image_blocks,
        )
        content = _extract_content_text(completion)
        _append_debug_attempt(
            debug_trace,
            provider=provider,
            model=model_name,
            mode='vision+ocr',
            status='ok',
            response_text=content,
            image_blocks_count=len(image_blocks),
        )
        return completion, 'vision+ocr'
    except Exception as exc:
        logger.exception('AI completion with image payload failed for provider=%s', provider)
        _append_debug_attempt(
            debug_trace,
            provider=provider,
            model=model_name,
            mode='vision+ocr',
            status='error',
            error=_format_model_error(exc),
            image_blocks_count=len(image_blocks),
        )
        if not ocr_text:
            raise

    try:
        completion = _request_completion(
            client=client,
            model_name=model_name,
            company_name=company_name,
            ocr_text=ocr_text,
            image_blocks=[],
        )
    except Exception as exc:
        _append_debug_attempt(
            debug_trace,
            provider=provider,
            model=model_name,
            mode='ocr-only',
            status='error',
            error=_format_model_error(exc),
            image_blocks_count=0,
        )
        raise

    content = _extract_content_text(completion)
    _append_debug_attempt(
        debug_trace,
        provider=provider,
        model=model_name,
        mode='ocr-only',
        status='ok',
        response_text=content,
        image_blocks_count=0,
    )
    return completion, 'ocr-only'


def _sync_completion(
    image_blocks: list[dict[str, Any]],
    company_name: str | None,
    ocr_text: str | None,
) -> dict[str, Any]:
    debug_trace = _new_debug_trace()

    try:
        from openai import AzureOpenAI, OpenAI  # noqa: F401
    except Exception:
        debug_trace['result'] = 'error'
        debug_trace['error'] = 'OpenAI SDK is not installed on server'
        return _with_debug({'error': 'OpenAI SDK is not installed on server'}, debug_trace)

    providers = _build_provider_sequence()
    if not providers:
        debug_trace['result'] = 'error'
        debug_trace['error'] = 'AI provider configuration missing'
        return _with_debug({'error': 'AI provider configuration missing'}, debug_trace)

    completion: Any | None = None
    content = ''
    provider_errors: list[str] = []
    completion_mode: str | None = None
    parsed_payload: dict[str, Any] | None = None
    best_candidate: dict[str, Any] | None = None

    for provider in providers:
        try:
            client, model_name = _build_provider_client(provider)
        except Exception as exc:
            message = _format_model_error(exc)
            provider_errors.append(f'{provider}: {message}')
            _append_debug_attempt(
                debug_trace,
                provider=provider,
                model='',
                mode='provider-setup',
                status='error',
                error=message,
            )
            continue

        try:
            completion_candidate, mode = _request_with_provider(
                provider=provider,
                model_name=model_name,
                client=client,
                image_blocks=image_blocks,
                company_name=company_name,
                ocr_text=ocr_text,
                debug_trace=debug_trace,
            )
        except Exception as exc:
            provider_errors.append(f'{provider}: {_format_model_error(exc)}')
            continue

        content_candidate = _extract_content_text(completion_candidate)
        parsed_candidate = safe_json_parse(content_candidate) if content_candidate else None
        payload_score = _score_extraction_payload(parsed_candidate)
        mode_bonus = 100 if mode == 'vision+ocr' else 0
        total_score = mode_bonus + max(payload_score, 0)

        candidate = {
            'completion': completion_candidate,
            'provider': provider,
            'model': model_name,
            'mode': mode,
            'content': content_candidate,
            'parsed': parsed_candidate,
            'payload_score': payload_score,
            'total_score': total_score,
        }

        if best_candidate is None or int(candidate['total_score']) > int(best_candidate['total_score']):
            best_candidate = candidate

        # If we already got a strong vision extraction, avoid extra latency/cost.
        if mode == 'vision+ocr' and payload_score >= _QUALITY_ACCEPT_THRESHOLD:
            break

    if best_candidate is not None:
        completion = best_candidate['completion']
        completion_mode = str(best_candidate['mode'])
        content = str(best_candidate['content'] or '')
        parsed_payload = best_candidate['parsed'] if isinstance(best_candidate['parsed'], dict) else None
        debug_trace['provider'] = best_candidate['provider']
        debug_trace['model'] = best_candidate['model']
        debug_trace['selected_mode'] = completion_mode
        debug_trace['selected_payload_score'] = int(best_candidate['payload_score'])
        debug_trace['selected_total_score'] = int(best_candidate['total_score'])

    if completion is None:
        details = '; '.join(provider_errors) if provider_errors else 'No provider attempts available'
        debug_trace['result'] = 'error'
        debug_trace['error'] = 'Failed to extract data from AI model'
        debug_trace['details'] = details[:1000]
        return _with_debug({
            'error': 'Failed to extract data from AI model',
            'details': details[:1000],
        }, debug_trace)

    if not content:
        debug_trace['result'] = 'error'
        debug_trace['error'] = 'AI model returned empty response'
        return _with_debug({'error': 'AI model returned empty response'}, debug_trace)
    logger.info('AI raw response: %s', content)
    print(f'AI raw response: {content}')

    parsed = parsed_payload if isinstance(parsed_payload, dict) else safe_json_parse(content)
    if parsed is None:
        debug_trace['result'] = 'error'
        debug_trace['error'] = 'Model returned invalid JSON'
        return _with_debug({'error': 'Model returned invalid JSON'}, debug_trace)

    validated = _validate_document_type(parsed)
    debug_trace['parsed_response'] = parsed
    if validated.get('error'):
        debug_trace['result'] = 'error'
        debug_trace['error'] = validated.get('error')
    else:
        debug_trace['result'] = 'success'
        debug_trace['document_type'] = validated.get('document_type')
        if completion_mode:
            debug_trace['selected_mode'] = completion_mode
    return _with_debug(validated, debug_trace)


async def extract_document_data(
    file_path: str,
    company_name: str | None = None,
    ocr_text: str | None = None,
) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return {'error': 'File cannot be processed'}

    try:
        payload = path.read_bytes()
    except Exception:
        return {'error': 'File cannot be processed'}

    mime_type = _detect_mime(payload, path)
    if mime_type not in _SUPPORTED_MIME:
        return {'error': 'Unsupported file type for AI processing'}

    image_blocks = _build_image_blocks(path, mime_type, payload)
    if not image_blocks:
        return {'error': 'File cannot be processed'}

    return await asyncio.to_thread(_sync_completion, image_blocks, company_name, ocr_text)
