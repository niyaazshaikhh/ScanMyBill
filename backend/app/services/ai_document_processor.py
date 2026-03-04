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
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
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


def _request_completion(
    client: Any,
    deployment: str,
    company_name: str | None,
    ocr_text: str | None,
    image_blocks: list[dict[str, Any]],
) -> Any:
    return client.chat.completions.create(
        model=deployment,
        messages=[
            {'role': 'system', 'content': _system_prompt()},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': _build_user_instruction(company_name, ocr_text)},
                    *image_blocks,
                ],
            },
        ],
        temperature=0,
        max_tokens=_MAX_TOKENS,
        response_format={'type': 'json_object'},
    )


def _sync_completion(
    image_blocks: list[dict[str, Any]],
    company_name: str | None,
    ocr_text: str | None,
) -> dict[str, Any]:
    try:
        from openai import AzureOpenAI
    except Exception:
        return {'error': 'OpenAI SDK is not installed on server'}

    endpoint = settings.azure_openai_endpoint
    deployment = settings.azure_openai_deployment
    api_key = settings.openai_api_key or settings.azure_openai_api_key

    if not endpoint or not deployment or not api_key:
        return {'error': 'Azure OpenAI configuration missing'}

    client = AzureOpenAI(
        api_version=settings.azure_openai_api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
    )

    try:
        completion = _request_completion(
            client=client,
            deployment=deployment,
            company_name=company_name,
            ocr_text=ocr_text,
            image_blocks=image_blocks,
        )
    except Exception as exc:
        logger.exception('AI completion with image payload failed')
        if ocr_text:
            try:
                completion = _request_completion(
                    client=client,
                    deployment=deployment,
                    company_name=company_name,
                    ocr_text=ocr_text,
                    image_blocks=[],
                )
            except Exception as fallback_exc:
                return {
                    'error': 'Failed to extract data from AI model',
                    'details': _format_model_error(fallback_exc),
                }
        else:
            return {
                'error': 'Failed to extract data from AI model',
                'details': _format_model_error(exc),
            }

    content = _extract_content_text(completion)
    if not content:
        return {'error': 'AI model returned empty response'}
    logger.info('AI raw response: %s', content)
    print(f'AI raw response: {content}')

    parsed = safe_json_parse(content)
    if parsed is None:
        return {'error': 'Model returned invalid JSON'}

    return _validate_document_type(parsed)


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
