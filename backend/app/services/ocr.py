from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytesseract
import requests
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance
from pypdf import PdfReader

from app.core.config import settings
from app.models.invoice import InvoiceType
from app.schemas.validation_rules import STATE_CODE_BY_NAME, STATE_NAME_BY_LOWERCASE

logger = logging.getLogger(__name__)

GST_REGEX = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b')
DATE_PATTERNS = [
    '%d/%m/%Y',
    '%d-%m-%Y',
    '%d.%m.%Y',
    '%Y-%m-%d',
    '%d/%m/%y',
    '%d-%m-%y',
    '%d/%b/%Y',
    '%d-%b-%Y',
    '%d.%b.%Y',
    '%d %b %Y',
    '%d/%B/%Y',
    '%d-%B-%Y',
    '%d.%B.%Y',
    '%d %B %Y',
    '%d/%b/%y',
    '%d-%b-%y',
    '%d/%B/%y',
    '%d-%B-%y',
]
CHALLAN_KEYWORDS = ('delivery challan', 'delivery note', 'challan no', 'dc no')
GST_INVOICE_KEYWORDS = (
    'tax invoice',
    'gst invoice',
    'invoice',
    'cgst',
    'sgst',
    'igst',
    'hsn',
)
SALE_KEYWORDS = ('sales invoice', 'tax invoice', 'outward', 'billed to', 'bill to')
PURCHASE_KEYWORDS = ('purchase', 'supplier', 'vendor bill', 'inward')

MAX_VISUAL_PAGES = 3
LLM_TIMEOUT_SECONDS = 45

def preprocess_image(image: Image.Image):

    image = image.convert("L")  # grayscale

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    image = image.point(lambda x: 0 if x < 140 else 255)

    return image

def extract_text_from_file(file_path: str, mime_type: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return ''

    try:
        if mime_type.startswith('image/'):
            with Image.open(path) as image:
                return pytesseract.image_to_string(preprocess_image(image))

        if mime_type == 'application/pdf':
            return _extract_text_from_pdf(path)

        return ''
    except Exception:
        return ''


def extract_bill_insights(
    *,
    file_path: str,
    mime_type: str,
    fallback_type: InvoiceType,
    company_name: str | None = None,
    company_gstin: str | None = None,
) -> dict[str, Any]:
    text = extract_text_from_file(file_path, mime_type)
    llm_payload = _extract_with_gpt_4o_mini(
        file_path=file_path,
        mime_type=mime_type,
        text=text,
        company_name=company_name,
        company_gstin=company_gstin,
    )
    if llm_payload:
        return _normalize_llm_payload(
            llm_payload=llm_payload,
            text=text,
            fallback_type=fallback_type,
            company_name=company_name,
            company_gstin=company_gstin,
        )

    heuristic = extract_structured_data(
        text,
        fallback_type=fallback_type,
        company_name=company_name,
        company_gstin=company_gstin,
    )
    document_type = _infer_document_type(text)
    gst_invoice_payload = _build_fallback_gst_invoice_payload(text, heuristic)
    delivery_challan_payload = _build_fallback_delivery_challan_payload(text, heuristic)

    return {
        'text': text,
        'document_type': document_type,
        'bill_date': heuristic['bill_date'],
        'gst_number': heuristic['gst_number'],
        'total_amount': heuristic['total_amount'],
        'inferred_type': heuristic['inferred_type'],
        'gst_invoice': gst_invoice_payload,
        'delivery_challan': delivery_challan_payload,
        'warnings': ['LLM extraction unavailable. Used OCR/regex fallback extraction.'],
    }


def _extract_text_from_pdf(path: Path) -> str:
    # OCR first pages for scanned PDFs, then fallback to embedded text extraction.
    text_parts: list[str] = []
    try:
        images = convert_from_path(str(path), first_page=1, last_page=MAX_VISUAL_PAGES)
        for image in images:
            text_parts.append(pytesseract.image_to_string(preprocess_image(image)))
    except Exception:
        pass

    if ''.join(text_parts).strip():
        return '\n'.join(text_parts)

    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:MAX_VISUAL_PAGES]:
            text_parts.append(page.extract_text() or '')
    except Exception:
        return ''

    return '\n'.join(text_parts)


def _extract_with_gpt_4o_mini(
    *,
    file_path: str,
    mime_type: str,
    text: str,
    company_name: str | None,
    company_gstin: str | None,
) -> dict[str, Any] | None:
    if not _llm_is_configured():
        return None

    message_content: list[dict[str, Any]] = [{'type': 'text', 'text': _build_prompt_text(text, company_name, company_gstin)}]
    message_content.extend(_build_visual_content(file_path, mime_type))
    if len(message_content) == 1 and not text.strip():
        return None

    request_body = {
        'model': settings.openai_model,
        'messages': [
            {'role': 'system', 'content': _system_prompt()},
            {'role': 'user', 'content': message_content},
        ],
        'temperature': 0,
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'bill_extraction',
                'strict': True,
                'schema': _bill_extraction_json_schema(),
            },
        },
    }

    if _azure_openai_is_configured():
        azure_payload = dict(request_body)
        azure_payload['model'] = settings.azure_openai_deployment
        try:
            response_json = _call_azure_openai_chat_completion(azure_payload)
            parsed = _parse_completion_json(response_json)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning('Azure OpenAI bill extraction failed. Falling back to next provider: %s', exc)

    if _openai_is_configured():
        try:
            response_json = _call_openai_chat_completion(request_body)
            parsed = _parse_completion_json(response_json)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning('OpenAI bill extraction failed. Using fallback extraction: %s', exc)

    return None


def _system_prompt() -> str:
    return (
        'You extract structured data from Indian business bills. '
        'Classify each document as either gst_invoice or delivery_challan. '
        'Classify bill_type as sales or purchase based on the provided company details. '
        'Return strictly valid JSON matching the required schema. '
        'If data is missing, use null for scalar fields and [] for items. '
        'Do not include markdown, explanations, or extra keys.'
    )


def _build_prompt_text(text: str, company_name: str | None, company_gstin: str | None) -> str:
    compact_text = re.sub(r'\s+', ' ', text or '').strip()
    # Keep payload bounded for model context while still retaining representative OCR text.
    clipped_text = compact_text[:6_000]
    return (
        'Extract the bill fields from the attached document/image and OCR text.\n'
        f'Company Name from settings/personal_details: {company_name or "UNKNOWN"}\n'
        f'Company GSTIN from settings/personal_details: {company_gstin or "UNKNOWN"}\n'
        'For gst_invoice, always extract seller_name and buyer_name.\n'
        'For delivery_challan, always extract challan_number, from_party, and to_party.\n'
        'bill_type classification rule:\n'
        '- sales: if settings company appears as seller/issuer/consignor.\n'
        '- purchase: if settings company appears as buyer/recipient/consignee.\n'
        '- If unclear, choose purchase.\n'
        'Use OCR reference text below only as fallback when image is unclear.\n'
        f'OCR_TEXT: {clipped_text or "N/A"}'
    )


def _build_visual_content(file_path: str, mime_type: str) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        return []

    if mime_type.startswith('image/'):
        payload = _encode_image_to_data_url(path, mime_type)
        if not payload:
            return []
        return [{'type': 'image_url', 'image_url': {'url': payload}}]

    if mime_type == 'application/pdf':
        blocks: list[dict[str, Any]] = []
        try:
            pages = convert_from_path(str(path), first_page=1, last_page=MAX_VISUAL_PAGES)
        except Exception:
            return []

        for page in pages:
            encoded = _encode_pil_image(page)
            if encoded:
                blocks.append({'type': 'image_url', 'image_url': {'url': encoded}})
        return blocks

    return []


def _encode_image_to_data_url(path: Path, mime_type: str) -> str | None:
    # Re-encode to JPEG to control payload size for vision requests.
    try:
        with Image.open(path) as image:
            encoded = _encode_pil_image(image)
            if encoded:
                return encoded
    except Exception:
        pass

    try:
        data = path.read_bytes()
    except Exception:
        return None

    normalized_mime = 'image/jpeg' if mime_type in {'image/jpg', 'image/jpeg'} else mime_type
    encoded = base64.b64encode(data).decode('ascii')
    return f'data:{normalized_mime};base64,{encoded}'


def _encode_pil_image(image: Image.Image) -> str | None:
    try:
        buffer = io.BytesIO()
        rgb = image.convert('RGB')
        rgb.save(buffer, format='JPEG', quality=80, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/jpeg;base64,{encoded}'
    except Exception:
        return None


def _call_openai_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = (settings.openai_base_url or 'https://api.openai.com/v1').rstrip('/')
    url = f'{base_url}/chat/completions'
    headers = {
        'Authorization': f'Bearer {settings.openai_api_key}',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _call_azure_openai_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    endpoint = (settings.azure_openai_endpoint or '').rstrip('/')
    deployment = settings.azure_openai_deployment
    if not endpoint or not deployment:
        raise ValueError('Azure OpenAI endpoint/deployment is not configured.')

    url = (
        f'{endpoint}/openai/deployments/{deployment}/chat/completions'
        f'?api-version={settings.azure_openai_api_version}'
    )
    headers = {
        'api-key': settings.azure_openai_api_key or '',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _parse_completion_json(response_json: dict[str, Any]) -> dict[str, Any] | None:
    choices = response_json.get('choices')
    if not isinstance(choices, list) or not choices:
        return None

    message = choices[0].get('message') if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None

    content = message.get('content')
    if isinstance(content, str):
        return _try_parse_json(content)

    if isinstance(content, list):
        text_fragments: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get('text'), str):
                text_fragments.append(part['text'])
                continue
            if part.get('type') == 'text' and isinstance(part.get('text'), str):
                text_fragments.append(part['text'])
        if text_fragments:
            return _try_parse_json(''.join(text_fragments))
    return None


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
                'required': ['challan_number', 'order_number', 'challan_date', 'from_party', 'to_party', 'subtotal', 'notes', 'items'],
            },
            'warnings': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['document_type', 'bill_type', 'gst_invoice', 'delivery_challan', 'warnings'],
    }


def _normalize_llm_payload(
    *,
    llm_payload: dict[str, Any],
    text: str,
    fallback_type: InvoiceType,
    company_name: str | None,
    company_gstin: str | None,
) -> dict[str, Any]:
    warnings = [item for item in llm_payload.get('warnings', []) if isinstance(item, str)]

    gst_invoice_raw = llm_payload.get('gst_invoice') if isinstance(llm_payload.get('gst_invoice'), dict) else {}
    delivery_challan_raw = (
        llm_payload.get('delivery_challan') if isinstance(llm_payload.get('delivery_challan'), dict) else {}
    )
    llm_document_type = str(llm_payload.get('document_type') or '').strip().lower()
    document_type = llm_document_type if llm_document_type in {'gst_invoice', 'delivery_challan'} else _infer_document_type(text)

    gst_number = _normalize_gstin_or_none(gst_invoice_raw.get('gst_number')) or _extract_gst_number(text)
    llm_bill_type_raw = str(llm_payload.get('bill_type') or '').strip().lower()
    llm_bill_type = InvoiceType(llm_bill_type_raw) if llm_bill_type_raw in {'sales', 'purchase'} else fallback_type

    gst_invoice = _normalize_gst_invoice_payload(
        raw=gst_invoice_raw,
        text=text,
        fallback_total=_extract_total_amount(text),
    )
    delivery_challan = _normalize_delivery_challan_payload(
        raw=delivery_challan_raw,
        text=text,
        fallback_total=_extract_total_amount(text),
    )
    party_matched_type = _infer_type_by_party_match(
        company_name=company_name,
        seller_name=gst_invoice.get('seller_name'),
        buyer_name=gst_invoice.get('buyer_name'),
    )
    inferred_type = party_matched_type or _infer_invoice_type(
        text=text,
        fallback_type=llm_bill_type,
        company_name=company_name,
        company_gstin=company_gstin,
        gst_number=gst_number,
    )

    if document_type == 'gst_invoice':
        bill_date = gst_invoice['invoice_date'] or _extract_date(text)
        total_amount = gst_invoice['total_amount']
    else:
        bill_date = delivery_challan['challan_date'] or _extract_date(text)
        total_amount = delivery_challan['subtotal']

    return {
        'text': text,
        'document_type': document_type,
        'bill_date': bill_date,
        'gst_number': gst_number,
        'total_amount': total_amount,
        'inferred_type': inferred_type,
        'gst_invoice': gst_invoice,
        'delivery_challan': delivery_challan,
        'warnings': warnings,
    }


def _normalize_gst_invoice_payload(
    *,
    raw: dict[str, Any],
    text: str,
    fallback_total: float,
) -> dict[str, Any]:
    place_of_supply = _normalize_state_name(raw.get('place_of_supply'))
    place_code = _normalize_state_code(raw.get('place_of_supply_code'))
    if place_of_supply and not place_code:
        place_code = STATE_CODE_BY_NAME.get(place_of_supply.lower())
    if place_code and not place_of_supply:
        place_of_supply = _state_name_by_code(place_code)

    subtotal = _coerce_non_negative_number(raw.get('subtotal'))
    gst_amount = _coerce_non_negative_number(raw.get('gst_amount'))
    total_amount = _coerce_non_negative_number(raw.get('total_amount'))

    if total_amount <= 0:
        total_amount = fallback_total
    if subtotal <= 0 and total_amount > 0:
        computed_subtotal = total_amount - gst_amount
        subtotal = computed_subtotal if computed_subtotal > 0 else total_amount
    if gst_amount <= 0:
        extracted_gst = _extract_gst_amount(text)
        if extracted_gst > 0:
            gst_amount = extracted_gst
            if subtotal <= 0 and total_amount > 0:
                subtotal = max(total_amount - gst_amount, 0.0)

    items_raw = raw.get('items')
    items: list[dict[str, Any]] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_gst_invoice_item(item)
            if normalized:
                items.append(normalized)

    return {
        'invoice_number': _normalize_document_number(raw.get('invoice_number')),
        'invoice_date': _parse_date(raw.get('invoice_date')) or _extract_date(text),
        'seller_name': _normalize_party_name(raw.get('seller_name')) or _extract_party_name(text, 'seller'),
        'buyer_name': _normalize_party_name(raw.get('buyer_name')) or _extract_party_name(text, 'buyer'),
        'place_of_supply': place_of_supply,
        'place_of_supply_code': place_code,
        'gst_number': _normalize_gstin_or_none(raw.get('gst_number')) or _extract_gst_number(text),
        'subtotal': round(subtotal, 2),
        'gst_amount': round(gst_amount, 2),
        'total_amount': round(total_amount, 2),
        'notes': _normalize_notes(raw.get('notes')),
        'items': items,
    }


def _normalize_delivery_challan_payload(
    *,
    raw: dict[str, Any],
    text: str,
    fallback_total: float,
) -> dict[str, Any]:
    subtotal = _coerce_non_negative_number(raw.get('subtotal'))
    if subtotal <= 0:
        subtotal = fallback_total

    items_raw = raw.get('items')
    items: list[dict[str, Any]] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_delivery_challan_item(item)
            if normalized:
                items.append(normalized)

    return {
        'challan_number': _coerce_positive_int(raw.get('challan_number')) or _extract_challan_number(text),
        'order_number': _normalize_order_number(raw.get('order_number')) or _extract_order_number(text),
        'challan_date': _parse_date(raw.get('challan_date')) or _extract_date(text),
        'from_party': _normalize_party_name(raw.get('from_party')) or _extract_party_name(text, 'seller'),
        'to_party': _normalize_party_name(raw.get('to_party')) or _extract_party_name(text, 'buyer'),
        'subtotal': round(subtotal, 2),
        'notes': _normalize_notes(raw.get('notes')),
        'items': items,
    }


def _normalize_gst_invoice_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    description = _normalize_description(raw.get('description'))
    quantity = _coerce_positive_number(raw.get('quantity'))
    rate = _coerce_non_negative_number(raw.get('rate'))
    tax_rate = _coerce_non_negative_number(raw.get('tax_rate'))
    hsn_sac = _normalize_hsn_sac(raw.get('hsn_sac'))
    if description is None and rate <= 0 and quantity <= 0:
        return None
    return {
        'description': description or 'Item',
        'hsn_sac': hsn_sac,
        'quantity': quantity if quantity > 0 else 1.0,
        'rate': rate,
        'tax_rate': tax_rate,
    }


def _normalize_delivery_challan_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    description = _normalize_description(raw.get('description'))
    quantity = _coerce_positive_number(raw.get('quantity'))
    rate = _coerce_non_negative_number(raw.get('rate'))
    if description is None and rate <= 0 and quantity <= 0:
        return None
    return {
        'description': description or 'Item',
        'quantity': quantity if quantity > 0 else 1.0,
        'rate': rate,
    }


def _build_fallback_gst_invoice_payload(text: str, heuristic: dict[str, Any]) -> dict[str, Any]:
    total = float(heuristic['total_amount'] or 0.0)
    gst_amount = _extract_gst_amount(text)
    subtotal = max(total - gst_amount, 0.0) if total > 0 else 0.0

    return {
        'invoice_number': _extract_invoice_number(text),
        'invoice_date': heuristic['bill_date'],
        'seller_name': _extract_party_name(text, 'seller'),
        'buyer_name': _extract_party_name(text, 'buyer'),
        'place_of_supply': _extract_state_name(text),
        'place_of_supply_code': _extract_state_code(text),
        'gst_number': heuristic['gst_number'],
        'subtotal': round(subtotal, 2),
        'gst_amount': round(gst_amount, 2),
        'total_amount': round(total, 2),
        'notes': None,
        'items': [],
    }


def _build_fallback_delivery_challan_payload(text: str, heuristic: dict[str, Any]) -> dict[str, Any]:
    return {
        'challan_number': _extract_challan_number(text),
        'order_number': _extract_order_number(text),
        'challan_date': heuristic['bill_date'],
        'from_party': _extract_party_name(text, 'seller'),
        'to_party': _extract_party_name(text, 'buyer'),
        'subtotal': round(float(heuristic['total_amount'] or 0.0), 2),
        'notes': None,
        'items': [],
    }


def extract_structured_data(
    text: str,
    fallback_type: InvoiceType,
    company_name: str | None = None,
    company_gstin: str | None = None,
) -> dict[str, Any]:
    normalized_text = text or ''
    date_value = _extract_date(normalized_text)
    gst_number = _extract_gst_number(normalized_text)
    total_amount = _extract_total_amount(normalized_text)
    inferred_type = _infer_invoice_type(
        text=normalized_text,
        fallback_type=fallback_type,
        company_name=company_name,
        company_gstin=company_gstin,
        gst_number=gst_number,
    )
    return {
        'bill_date': date_value,
        'gst_number': gst_number,
        'total_amount': total_amount,
        'inferred_type': inferred_type,
    }


def _infer_invoice_type(
    *,
    text: str,
    fallback_type: InvoiceType,
    company_name: str | None,
    company_gstin: str | None,
    gst_number: str | None,
) -> InvoiceType:
    lowered = text.lower()
    normalized_company_gstin = _normalize_gstin(company_gstin)
    normalized_detected_gstin = _normalize_gstin(gst_number)
    normalized_company_name = (company_name or '').strip().lower()

    if normalized_company_gstin and normalized_detected_gstin:
        return (
            InvoiceType.SALES
            if normalized_company_gstin == normalized_detected_gstin
            else InvoiceType.PURCHASE
        )
    if normalized_company_name and len(normalized_company_name) >= 3 and normalized_company_name in lowered:
        return InvoiceType.SALES
    if any(keyword in lowered for keyword in SALE_KEYWORDS):
        return InvoiceType.SALES
    if any(keyword in lowered for keyword in PURCHASE_KEYWORDS):
        return InvoiceType.PURCHASE
    return fallback_type


def _infer_type_by_party_match(
    *,
    company_name: str | None,
    seller_name: str | None,
    buyer_name: str | None,
) -> InvoiceType | None:
    normalized_company = _normalize_party_label(company_name)
    if not normalized_company:
        return None

    normalized_seller = _normalize_party_label(seller_name)
    normalized_buyer = _normalize_party_label(buyer_name)
    if normalized_seller and normalized_seller == normalized_company:
        return InvoiceType.SALES
    if normalized_buyer and normalized_buyer == normalized_company:
        return InvoiceType.PURCHASE
    return None


def _normalize_party_label(value: str | None) -> str:
    if not value:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()
    return re.sub(r'\s+', ' ', normalized)


def _infer_document_type(text: str) -> str:
    lowered = (text or '').lower()
    if any(keyword in lowered for keyword in CHALLAN_KEYWORDS):
        return 'delivery_challan'
    if any(keyword in lowered for keyword in GST_INVOICE_KEYWORDS):
        return 'gst_invoice'
    return 'gst_invoice'


def _extract_date(text: str) -> date | None:
    numeric_matches = re.findall(r'\b(\d{1,4}[./-]\d{1,2}[./-]\d{2,4})\b', text)
    named_month_matches = re.findall(
        r'\b(\d{1,2}(?:[./-]|\s)[A-Za-z]{3,9}(?:[./-]|\s)\d{2,4})\b',
        text,
    )
    for match in [*numeric_matches, *named_month_matches]:
        candidate = match.strip()
        for pattern in DATE_PATTERNS:
            try:
                parsed = datetime.strptime(candidate, pattern)
                if parsed.year < 2000:
                    parsed = parsed.replace(year=parsed.year + 2000)
                return parsed.date()
            except ValueError:
                continue
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith('Z'):
        cleaned = cleaned[:-1]
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        pass
    for pattern in DATE_PATTERNS:
        try:
            parsed = datetime.strptime(cleaned, pattern)
            if parsed.year < 2000:
                parsed = parsed.replace(year=parsed.year + 2000)
            return parsed.date()
        except ValueError:
            continue
    return None


def _extract_gst_number(text: str) -> str | None:
    match = GST_REGEX.search(text.upper())
    return match.group(0) if match else None


def _normalize_gstin(value: str | None) -> str:
    if not value:
        return ''
    return re.sub(r'[^A-Z0-9]', '', value.upper())


def _normalize_gstin_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_gstin(value)
    return normalized if len(normalized) == 15 else None


def _extract_total_amount(text: str) -> float:
    patterns = [
        r'(?:grand\s*total|amount\s*due|total\s*amount|invoice\s*total)\s*[:\-]?\s*[₹Rs.\s]*([0-9,]+(?:\.\d{1,2})?)',
        r'(?:payable|net\s*amount|net\s*payable)\s*[:\-]?\s*[₹Rs.\s]*([0-9,]+(?:\.\d{1,2})?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _to_float(match.group(1))

    numeric_candidates = re.findall(r'\b([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.\d{1,2})?)\b', text)
    if numeric_candidates:
        values = [_to_float(value) for value in numeric_candidates]
        values = [value for value in values if value > 0]
        if values:
            return max(values)

    return 0.0


def _extract_gst_amount(text: str) -> float:
    patterns = [
        r'(?:total\s*gst|gst\s*amount|tax\s*amount|total\s*tax)\s*[:\-]?\s*[₹Rs.\s]*([0-9,]+(?:\.\d{1,2})?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _to_float(match.group(1))
    return 0.0


def _extract_invoice_number(text: str) -> str | None:
    patterns = (
        r'(?:invoice\s*(?:no|number)?|bill\s*no)\s*[:#-]?\s*([A-Za-z0-9/-]{3,30})',
        r'\b(\d{4}-\d{2}/\d{3})\b',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _normalize_document_number(match.group(1))
    return None


def _extract_order_number(text: str) -> str | None:
    patterns = (
        r'(?:order\s*(?:no|number)|challan\s*(?:no|number)|dc\s*no)\s*[:#-]?\s*([A-Za-z0-9/-]{1,20})',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = _normalize_order_number(match.group(1))
            if candidate:
                return candidate
    return None


def _extract_challan_number(text: str) -> int | None:
    patterns = (
        r'(?:challan\s*(?:no|number)|dc\s*no)\s*[:#-]?\s*(\d{1,9})',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = _coerce_positive_int(match.group(1))
        if value:
            return value
    return None


def _normalize_document_number(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'[^A-Za-z0-9/-]', '', value.strip())
    if not cleaned:
        return None
    return cleaned[:60]


def _normalize_order_number(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'[^A-Za-z0-9]', '', value.strip())
    if not cleaned:
        return None
    return cleaned[:5]


def _normalize_hsn_sac(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    digits = re.sub(r'\D', '', value)
    return digits[:8]


def _normalize_notes(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:1_000]


def _normalize_description(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'\s+', ' ', value).strip()
    if not cleaned:
        return None
    return cleaned[:255]


def _normalize_party_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'\s+', ' ', value).strip()
    if not cleaned:
        return None
    return cleaned[:255]


def _extract_party_name(text: str, role: str) -> str | None:
    if not text:
        return None
    lowered_role = role.lower().strip()
    patterns: tuple[str, ...]
    if lowered_role == 'seller':
        patterns = (
            r'(?:seller|supplier|from|consignor)\s*[:\-]?\s*([A-Za-z0-9&.,()\- ]{3,100})',
            r'(?:issued\s*by)\s*[:\-]?\s*([A-Za-z0-9&.,()\- ]{3,100})',
        )
    else:
        patterns = (
            r'(?:buyer|bill\s*to|ship\s*to|to|consignee)\s*[:\-]?\s*([A-Za-z0-9&.,()\- ]{3,100})',
            r'(?:received\s*by)\s*[:\-]?\s*([A-Za-z0-9&.,()\- ]{3,100})',
        )

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        candidate = _normalize_party_name(match.group(1))
        if candidate:
            return candidate
    return None


def _normalize_state_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'\s+', ' ', value).strip()
    if not cleaned:
        return None
    normalized = STATE_NAME_BY_LOWERCASE.get(cleaned.lower())
    return normalized if normalized else cleaned[:64]


def _normalize_state_code(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    digits = re.sub(r'\D', '', raw)
    if len(digits) >= 2:
        return digits[:2]
    return None


def _extract_state_name(text: str) -> str | None:
    lowered = text.lower()
    for state_lower, proper_name in STATE_NAME_BY_LOWERCASE.items():
        if state_lower in lowered:
            return proper_name
    return None


def _extract_state_code(text: str) -> str | None:
    match = re.search(r'(?:state\s*code|pos)\s*[:#-]?\s*(\d{2})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    state_name = _extract_state_name(text)
    if not state_name:
        return None
    return STATE_CODE_BY_NAME.get(state_name.lower())


def _state_name_by_code(code: str) -> str | None:
    for state_name, state_code in STATE_CODE_BY_NAME.items():
        if state_code == code:
            return STATE_NAME_BY_LOWERCASE.get(state_name)
    return None


def _coerce_non_negative_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return round(max(float(value), 0.0), 2)
    if isinstance(value, str):
        return round(max(_to_float(value), 0.0), 2)
    return 0.0


def _coerce_positive_number(value: Any) -> float:
    numeric = _coerce_non_negative_number(value)
    return numeric if numeric > 0 else 0.0


def _coerce_positive_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_float(value: str) -> float:
    try:
        return float(value.replace(',', '').strip())
    except ValueError:
        return 0.0


def _llm_is_configured() -> bool:
    return _openai_is_configured() or _azure_openai_is_configured()


def _openai_is_configured() -> bool:
    return bool(settings.openai_api_key)


def _azure_openai_is_configured() -> bool:
    return bool(settings.azure_openai_api_key and settings.azure_openai_endpoint and settings.azure_openai_deployment)
