from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from app.models.invoice import InvoiceType
from app.schemas.bill import (
    BillStructuredData,
    DeliveryChallanExtractedPayload,
    GSTInvoiceExtractedPayload,
)
from app.services.ai_document_processor import extract_document_data
from app.services.ocr import extract_text_from_file
from app.utils.gstin import normalize_gstin

GST_INVOICE_KEYWORDS = (
    'invoice',
    'tax invoice',
    'gst invoice',
    'invoice no',
    'bill no',
    'cgst',
    'sgst',
    'igst',
)
DELIVERY_CHALLAN_KEYWORDS = (
    'delivery challan',
    'delivery note',
    'challan',
    'challan no',
    'dc no',
)
LEGAL_ENTITY_SUFFIXES = {'pvt', 'private', 'ltd', 'limited', 'llp', 'inc', 'co', 'company'}
INVALID_DOCUMENT_MESSAGE = (
    'Uploaded file is not a valid invoice or delivery challan. '
    'Please upload a clear GST invoice or delivery challan document.'
)
COMPANY_MISMATCH_MESSAGE = (
    'This document does not match your company profile. '
    'Please upload a bill where your company is listed as buyer/seller/consignee.'
)


def normalize_party(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)

    seller_candidate = _first_non_empty_value(
        normalized.get('seller'),
        normalized.get('seller_name'),
        normalized.get('supplier'),
        normalized.get('vendor'),
        normalized.get('issuer'),
        normalized.get('from_party'),
    )
    buyer_candidate = _first_non_empty_value(
        normalized.get('buyer'),
        normalized.get('buyer_name'),
        normalized.get('bill_to'),
        normalized.get('consignee'),
        normalized.get('recipient'),
        normalized.get('to_party'),
    )

    if seller_candidate is not None:
        normalized['seller'] = seller_candidate
    if buyer_candidate is not None:
        normalized['buyer'] = buyer_candidate

    seller_name = _extract_party_name(seller_candidate)
    buyer_name = _extract_party_name(buyer_candidate)
    if seller_name and not _as_optional_str(normalized.get('seller_name')):
        normalized['seller_name'] = seller_name
    if buyer_name and not _as_optional_str(normalized.get('buyer_name')):
        normalized['buyer_name'] = buyer_name

    if not _as_optional_str(normalized.get('from_party')) and seller_name:
        normalized['from_party'] = seller_name
    if not _as_optional_str(normalized.get('to_party')) and buyer_name:
        normalized['to_party'] = buyer_name

    if not normalized.get('transaction_type'):
        normalized['transaction_type'] = normalized.get('bill_type') or normalized.get('type')

    return normalized


def compute_missing_amounts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        normalized_item = dict(item)
        quantity = _as_amount(_first_non_empty_value(normalized_item.get('quantity'), normalized_item.get('qty')))
        rate = _as_amount(
            _first_non_empty_value(
                normalized_item.get('rate'),
                normalized_item.get('unit_price'),
                normalized_item.get('price'),
            )
        )
        amount = _as_amount(
            _first_non_empty_value(
                normalized_item.get('amount'),
                normalized_item.get('line_total'),
                normalized_item.get('total'),
            )
        )

        if amount <= 0 and quantity > 0 and rate > 0:
            amount = round(quantity * rate, 2)

        normalized_item['quantity'] = quantity if quantity > 0 else 1.0
        normalized_item['rate'] = rate
        if amount > 0:
            normalized_item['amount'] = amount

        normalized_items.append(normalized_item)

    return normalized_items


def validate_invoice_math(data: dict[str, Any]) -> dict[str, Any]:
    validated = dict(data)
    subtotal = _as_amount(validated.get('subtotal'))
    gst_amount = _as_amount(validated.get('gst_amount'))
    total_amount = _as_amount(validated.get('total_amount'))

    if subtotal > 0 and gst_amount > 0:
        expected_total = round(subtotal + gst_amount, 2)
        if total_amount <= 0 or abs(expected_total - total_amount) > 5:
            validated['total_amount'] = expected_total
            total_amount = expected_total

    if subtotal <= 0 and total_amount > 0:
        derived_subtotal = round(max(total_amount - gst_amount, 0.0), 2)
        if derived_subtotal > 0:
            validated['subtotal'] = derived_subtotal
            subtotal = derived_subtotal

    if gst_amount <= 0 and total_amount > 0 and subtotal > 0:
        derived_gst = round(max(total_amount - subtotal, 0.0), 2)
        if derived_gst > 0:
            validated['gst_amount'] = derived_gst

    return validated


def normalize_items(items: Any) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized_items

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        item = dict(raw_item)
        item['description'] = (
            _as_optional_str(item.get('description'))
            or _as_optional_str(item.get('item_name'))
            or 'Item'
        )
        item['quantity'] = _as_positive_amount(
            _first_non_empty_value(item.get('quantity'), item.get('qty'))
        )
        item['rate'] = _as_amount(
            _first_non_empty_value(item.get('rate'), item.get('unit_price'), item.get('price'))
        )
        if item.get('amount') is not None:
            item['amount'] = _as_amount(item.get('amount'))
        normalized_items.append(item)

    return normalized_items


def normalize_ai_payload(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = _flatten_document_payload(raw)

    seller_value = _first_non_empty_value(normalized.get('seller'), normalized.get('seller_name'))
    buyer_value = _first_non_empty_value(normalized.get('buyer'), normalized.get('buyer_name'))
    if not _as_optional_str(normalized.get('seller_name')):
        seller_name = _extract_party_name(seller_value)
        if seller_name:
            normalized['seller_name'] = seller_name
    if not _as_optional_str(normalized.get('buyer_name')):
        buyer_name = _extract_party_name(buyer_value)
        if buyer_name:
            normalized['buyer_name'] = buyer_name

    normalized['subtotal'] = _as_amount(normalized.get('subtotal'))
    normalized['gst_amount'] = _as_amount(normalized.get('gst_amount'))
    normalized['total_amount'] = _as_amount(normalized.get('total_amount'))
    normalized['items'] = compute_missing_amounts(normalize_items(normalized.get('items')))
    return normalized


def _debug_print(label: str, payload: Any) -> None:
    payload = _to_jsonable(payload)
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=False)
    except Exception:
        serialized = str(payload)
    print(f'{label}: {serialized}')


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, 'model_dump'):
        try:
            return _to_jsonable(value.model_dump(mode='python'))
        except Exception:
            return str(value)
    return value


def _extract_party_name(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    if isinstance(value, dict):
        for key in ('name', 'business_name', 'party_name', 'company_name', 'seller_name', 'buyer_name'):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _extract_party_gstin(value: Any) -> str | None:
    if isinstance(value, str):
        return normalize_gstin(value)
    if isinstance(value, dict):
        for key in ('gstin', 'gst_number', 'gst', 'seller_gstin', 'buyer_gstin'):
            item = value.get(key)
            normalized = normalize_gstin(item)
            if normalized:
                return normalized
    return None


async def process_uploaded_document(
    *,
    file_path: str,
    mime_type: str,
    fallback_type: InvoiceType,
    company_name: str | None,
    company_gstin: str | None,
) -> dict[str, Any]:
    ocr_text = ''
    try:
        ocr_text = extract_text_from_file(file_path, mime_type)
    except Exception:
        ocr_text = ''

    raw = await extract_document_data(file_path, company_name=company_name, ocr_text=ocr_text)
    if not isinstance(raw, dict):
        raise ValueError('AI extraction failed')
    ai_debug = raw.get('__ai_debug') if isinstance(raw.get('__ai_debug'), dict) else None
    if '__ai_debug' in raw:
        raw = {key: value for key, value in raw.items() if key != '__ai_debug'}
    if raw.get('error'):
        raise ValueError(
            _map_extraction_error_to_user_message(
                error=raw.get('error'),
                details=raw.get('details'),
            )
        )

    raw = normalize_ai_payload(raw)
    raw = normalize_party(raw)

    document_type = _normalize_document_type(raw.get('document_type'))
    if document_type == 'unknown':
        raise ValueError(INVALID_DOCUMENT_MESSAGE)
    if document_type == 'gst_invoice':
        raw = validate_invoice_math(raw)

    try:
        gst_payload = _build_gst_payload(raw)
        challan_payload = _build_challan_payload(raw)
    except ValidationError as exc:
        _debug_print('Normalized AI payload before schema validation', raw)
        print(f'Pydantic payload validation error: {exc}')
        raise ValueError(f'Schema validation error: {exc}') from exc

    if not _has_required_document_signals(
        document_type=document_type,
        raw=raw,
        ocr_text=ocr_text,
        gst_payload=gst_payload,
        challan_payload=challan_payload,
    ):
        raise ValueError(INVALID_DOCUMENT_MESSAGE)
    if not _is_document_meant_for_company(
        document_type=document_type,
        raw=raw,
        ocr_text=ocr_text,
        company_name=company_name,
        company_gstin=company_gstin,
        challan_payload=challan_payload,
    ):
        raise ValueError(COMPANY_MISMATCH_MESSAGE)

    bill_type = _determine_bill_type(
        document_type=document_type,
        explicit_transaction_type=_first_non_empty_value(
            raw.get('transaction_type'),
            raw.get('bill_type'),
            raw.get('type'),
        ),
        fallback=fallback_type,
        company_name=company_name,
        seller_name=_extract_party_name(_first_non_empty_value(raw.get('seller'), raw.get('seller_name'))),
        buyer_name=_extract_party_name(_first_non_empty_value(raw.get('buyer'), raw.get('buyer_name'))),
        from_party=challan_payload.from_party,
        to_party=challan_payload.to_party,
    )
    if document_type == 'gst_invoice':
        gst_payload.gst_number = _select_gst_for_bill_type(raw, bill_type, gst_payload.gst_number)
    fallback_client_gstin = (
        gst_payload.gst_number
        if document_type == 'gst_invoice'
        else normalize_gstin(raw.get('gst_number'))
    )
    seller_name, buyer_name, seller_gstin, buyer_gstin = _extract_invoice_party_identity(raw)
    client_name, client_gstin = _resolve_client_identity(
        document_type=document_type,
        bill_type=bill_type,
        challan_payload=challan_payload,
        seller_name=seller_name,
        buyer_name=buyer_name,
        seller_gstin=seller_gstin,
        buyer_gstin=buyer_gstin,
        fallback_gstin=fallback_client_gstin,
    )

    warnings = [value for value in raw.get('warnings', []) if isinstance(value, str)]

    structured_payload = {
        'document_type': document_type,
        'bill_type': bill_type,
        'gst_invoice': gst_payload if document_type == 'gst_invoice' else None,
        'delivery_challan': challan_payload if document_type == 'delivery_challan' else None,
        'warnings': warnings,
    }
    _debug_print('Structured payload before BillStructuredData', structured_payload)
    try:
        structured = BillStructuredData(**structured_payload)
    except ValidationError as exc:
        print(f'BillStructuredData validation error: {exc}')
        raise ValueError(f'Schema validation error: {exc}') from exc

    bill_date = (
        gst_payload.invoice_date if document_type == 'gst_invoice' else challan_payload.challan_date
    ) or _as_optional_date(raw.get('invoice_date')) or _as_optional_date(raw.get('challan_date'))

    total_amount = gst_payload.total_amount if document_type == 'gst_invoice' else challan_payload.subtotal
    if total_amount <= 0:
        total_amount = _as_amount(raw.get('total_amount'))

    return {
        'text': ocr_text,
        'document_type': document_type,
        'bill_type': bill_type,
        'transaction_type': bill_type.value,
        'bill_date': bill_date,
        'gst_number': gst_payload.gst_number,
        'total_amount': total_amount,
        'gst_invoice': gst_payload,
        'delivery_challan': challan_payload,
        'seller_name': seller_name,
        'seller_gstin': seller_gstin,
        'buyer_name': buyer_name,
        'buyer_gstin': buyer_gstin,
        'client_name': client_name,
        'client_gstin': client_gstin,
        'from_party': challan_payload.from_party,
        'to_party': challan_payload.to_party,
        'ai_debug': ai_debug,
        'structured_data': structured,
    }


def _map_extraction_error_to_user_message(error: Any, details: Any) -> str:
    error_message = _as_optional_str(error) or 'Failed to process uploaded bill'
    details_message = _as_optional_str(details)
    normalized = error_message.lower()
    invalid_document_markers = (
        'unknown document type',
        'invalid json',
        'empty response',
        'file cannot be processed',
        'unsupported file type',
    )
    if any(marker in normalized for marker in invalid_document_markers):
        return INVALID_DOCUMENT_MESSAGE
    if details_message:
        return f'{error_message}: {details_message}'
    return error_message


def _has_required_document_signals(
    *,
    document_type: str,
    raw: dict[str, Any],
    ocr_text: str,
    gst_payload: GSTInvoiceExtractedPayload,
    challan_payload: DeliveryChallanExtractedPayload,
) -> bool:
    if document_type == 'gst_invoice':
        return _has_invoice_signals(raw=raw, ocr_text=ocr_text, payload=gst_payload)
    if document_type == 'delivery_challan':
        return _has_delivery_challan_signals(raw=raw, ocr_text=ocr_text, payload=challan_payload)
    return False


def _has_invoice_signals(
    *,
    raw: dict[str, Any],
    ocr_text: str,
    payload: GSTInvoiceExtractedPayload,
) -> bool:
    invoice_number = _as_optional_str(payload.invoice_number) or _as_optional_str(raw.get('invoice_number'))
    invoice_date = payload.invoice_date or _as_optional_date(raw.get('invoice_date'))
    seller_name = _extract_party_name(_first_non_empty_value(raw.get('seller'), raw.get('seller_name')))
    buyer_name = _extract_party_name(_first_non_empty_value(raw.get('buyer'), raw.get('buyer_name')))

    has_identity = bool(invoice_number or invoice_date)
    has_party = bool(seller_name or buyer_name)
    has_amount = payload.total_amount > 0 or payload.subtotal > 0 or _as_amount(raw.get('total_amount')) > 0
    has_items = len(payload.items) > 0
    has_keyword = _text_contains_keywords(ocr_text, GST_INVOICE_KEYWORDS)

    strong_structure = has_identity and has_party and (has_amount or has_items)
    keyword_structure = has_keyword and has_party and (has_identity or has_amount or has_items)
    return strong_structure or keyword_structure


def _has_delivery_challan_signals(
    *,
    raw: dict[str, Any],
    ocr_text: str,
    payload: DeliveryChallanExtractedPayload,
) -> bool:
    challan_number = payload.challan_number or _as_optional_int(raw.get('challan_number'))
    order_number = _as_optional_str(payload.order_number) or _as_optional_str(raw.get('order_number'))
    challan_date = payload.challan_date or _as_optional_date(raw.get('challan_date'))
    from_party = _as_optional_str(payload.from_party) or _extract_party_name(raw.get('from_party'))
    to_party = _as_optional_str(payload.to_party) or _extract_party_name(raw.get('to_party'))

    has_identity = bool(challan_number or order_number or challan_date)
    has_party = bool(from_party or to_party)
    has_amount = payload.subtotal > 0 or _as_amount(raw.get('subtotal')) > 0 or _as_amount(raw.get('total_amount')) > 0
    has_items = len(payload.items) > 0
    has_keyword = _text_contains_keywords(ocr_text, DELIVERY_CHALLAN_KEYWORDS)

    strong_structure = has_identity and has_party and (has_amount or has_items)
    keyword_structure = has_keyword and has_party and (has_identity or has_amount or has_items)
    return strong_structure or keyword_structure


def _is_document_meant_for_company(
    *,
    document_type: str,
    raw: dict[str, Any],
    ocr_text: str,
    company_name: str | None,
    company_gstin: str | None,
    challan_payload: DeliveryChallanExtractedPayload,
) -> bool:
    normalized_company = _normalize_name(company_name)
    normalized_company_gstin = normalize_gstin(company_gstin)
    if not normalized_company and not normalized_company_gstin:
        return True

    party_names = _collect_document_party_names(
        document_type=document_type,
        raw=raw,
        challan_payload=challan_payload,
    )
    if normalized_company and any(_name_matches_company(normalized_company, name) for name in party_names):
        return True
    if normalized_company and _ocr_mentions_company(normalized_company, ocr_text):
        return True

    if normalized_company_gstin:
        if _value_contains_gstin(raw, normalized_company_gstin):
            return True
        if normalized_company_gstin in str(ocr_text or '').upper():
            return True

    return False


def _collect_document_party_names(
    *,
    document_type: str,
    raw: dict[str, Any],
    challan_payload: DeliveryChallanExtractedPayload,
) -> list[str]:
    candidates: list[str] = []
    if document_type == 'delivery_challan':
        _append_party_name(candidates, challan_payload.from_party)
        _append_party_name(candidates, challan_payload.to_party)
        _append_party_name(candidates, raw.get('from_party'))
        _append_party_name(candidates, raw.get('to_party'))
    else:
        _append_party_name(candidates, raw.get('seller'))
        _append_party_name(candidates, raw.get('seller_name'))
        _append_party_name(candidates, raw.get('buyer'))
        _append_party_name(candidates, raw.get('buyer_name'))
        _append_party_name(candidates, raw.get('from_party'))
        _append_party_name(candidates, raw.get('to_party'))
    return candidates


def _append_party_name(target: list[str], value: Any) -> None:
    candidate = _extract_party_name(value) or _as_optional_str(value)
    if not candidate:
        return
    cleaned = candidate.strip()
    if cleaned and cleaned not in target:
        target.append(cleaned)


def _name_matches_company(normalized_company: str, candidate: str | None) -> bool:
    normalized_candidate = _normalize_name(candidate)
    if not normalized_candidate:
        return False

    if normalized_candidate == normalized_company:
        return True
    if len(normalized_company) >= 5 and normalized_company in normalized_candidate:
        return True
    if len(normalized_candidate) >= 5 and normalized_candidate in normalized_company:
        return True

    company_tokens = _name_tokens(normalized_company)
    candidate_tokens = _name_tokens(normalized_candidate)
    if not company_tokens or not candidate_tokens:
        return False

    overlap = company_tokens.intersection(candidate_tokens)
    if not overlap:
        return False
    return len(overlap) / len(company_tokens) >= 0.6


def _ocr_mentions_company(normalized_company: str, ocr_text: str) -> bool:
    normalized_text = _normalize_name(ocr_text)
    if not normalized_text:
        return False

    if len(normalized_company) >= 5 and normalized_company in normalized_text:
        return True

    company_tokens = _name_tokens(normalized_company)
    text_tokens = _name_tokens(normalized_text)
    if not company_tokens or not text_tokens:
        return False

    overlap = company_tokens.intersection(text_tokens)
    return bool(overlap) and len(overlap) / len(company_tokens) >= 0.6


def _name_tokens(normalized_name: str) -> set[str]:
    tokens = [
        token
        for token in normalized_name.split()
        if token and token not in LEGAL_ENTITY_SUFFIXES and len(token) >= 2
    ]
    if tokens:
        return set(tokens)
    return {token for token in normalized_name.split() if token}


def _text_contains_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    if not text:
        return False
    normalized_text = text.lower()
    return any(keyword in normalized_text for keyword in keywords)


def _value_contains_gstin(value: Any, target_gstin: str) -> bool:
    if isinstance(value, str):
        normalized = normalize_gstin(value)
        return normalized == target_gstin
    if isinstance(value, dict):
        return any(_value_contains_gstin(item, target_gstin) for item in value.values())
    if isinstance(value, list):
        return any(_value_contains_gstin(item, target_gstin) for item in value)
    return False


def _select_gst_for_bill_type(
    raw: dict[str, Any],
    bill_type: InvoiceType,
    existing_gst: str | None,
) -> str | None:
    seller_sources = [
        raw.get('seller'),
        raw.get('seller_name'),
        raw.get('seller_gstin'),
        raw.get('supplier'),
        raw.get('vendor'),
        raw.get('issuer'),
        raw.get('from_party'),
    ]
    buyer_sources = [
        raw.get('buyer'),
        raw.get('buyer_name'),
        raw.get('buyer_gstin'),
        raw.get('bill_to'),
        raw.get('consignee'),
        raw.get('recipient'),
        raw.get('to_party'),
    ]

    seller_gstin = _first_valid_gstin(seller_sources)
    buyer_gstin = _first_valid_gstin(buyer_sources)
    fallback_gstin = normalize_gstin(raw.get('gst_number')) or existing_gst

    if bill_type == InvoiceType.SALES:
        return buyer_gstin or fallback_gstin
    if bill_type == InvoiceType.PURCHASE:
        return seller_gstin or fallback_gstin
    return fallback_gstin


def _extract_invoice_party_identity(
    raw: dict[str, Any],
) -> tuple[str | None, str | None, str | None, str | None]:
    seller_sources = [
        raw.get('seller'),
        raw.get('seller_name'),
        raw.get('seller_gstin'),
        raw.get('supplier'),
        raw.get('vendor'),
        raw.get('issuer'),
        raw.get('from_party'),
    ]
    buyer_sources = [
        raw.get('buyer'),
        raw.get('buyer_name'),
        raw.get('buyer_gstin'),
        raw.get('bill_to'),
        raw.get('consignee'),
        raw.get('recipient'),
        raw.get('to_party'),
    ]
    seller_name = _extract_party_name(_first_non_empty_value(*seller_sources))
    buyer_name = _extract_party_name(_first_non_empty_value(*buyer_sources))
    seller_gstin = _first_valid_gstin(seller_sources)
    buyer_gstin = _first_valid_gstin(buyer_sources)
    return seller_name, buyer_name, seller_gstin, buyer_gstin


def _resolve_client_identity(
    *,
    document_type: str,
    bill_type: InvoiceType,
    challan_payload: DeliveryChallanExtractedPayload,
    seller_name: str | None,
    buyer_name: str | None,
    seller_gstin: str | None,
    buyer_gstin: str | None,
    fallback_gstin: str | None = None,
) -> tuple[str | None, str | None]:
    if document_type == 'delivery_challan':
        if bill_type == InvoiceType.SALES:
            return _as_optional_str(challan_payload.to_party) or buyer_name, buyer_gstin or fallback_gstin
        return _as_optional_str(challan_payload.from_party) or seller_name, seller_gstin or fallback_gstin

    if bill_type == InvoiceType.SALES:
        return buyer_name, buyer_gstin or fallback_gstin
    return seller_name, seller_gstin or fallback_gstin


def _flatten_document_payload(raw: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(raw)
    document_type = _normalize_document_type(flattened.get('document_type'))
    nested_key = 'gst_invoice' if document_type == 'gst_invoice' else 'delivery_challan'
    nested_payload = flattened.get(nested_key)
    if not isinstance(nested_payload, dict):
        return flattened

    for key, value in nested_payload.items():
        if key not in flattened or flattened.get(key) in (None, '', []):
            flattened[key] = value
    return flattened


def _first_valid_gstin(sources: list[Any]) -> str | None:
    for value in sources:
        normalized = _extract_party_gstin(value)
        if normalized:
            return normalized
    return None


def _build_gst_payload(raw: dict[str, Any]) -> GSTInvoiceExtractedPayload:
    seller = _first_non_empty_value(
        raw.get('seller'),
        raw.get('seller_name'),
        raw.get('supplier'),
        raw.get('vendor'),
        raw.get('issuer'),
    )
    items_raw = raw.get('items') if isinstance(raw.get('items'), list) else []

    return GSTInvoiceExtractedPayload(
        invoice_number=_as_optional_str(raw.get('invoice_number')),
        invoice_date=_as_optional_date(raw.get('invoice_date')),
        place_of_supply=_as_optional_str(raw.get('place_of_supply')),
        place_of_supply_code=_as_optional_str(raw.get('place_of_supply_code')),
        gst_number=(
            _extract_party_gstin(seller)
            or normalize_gstin(raw.get('seller_gstin'))
            or normalize_gstin(raw.get('gst_number'))
        ),
        subtotal=_as_amount(raw.get('subtotal')) or _as_amount(_dig(raw, 'invoice_totals', 'subtotal')),
        gst_amount=_as_amount(raw.get('gst_amount')) or _as_amount(_dig(raw, 'tax_summary', 'total_tax')),
        total_amount=_as_amount(raw.get('total_amount')) or _as_amount(_dig(raw, 'invoice_totals', 'grand_total')),
        notes=_as_optional_str(raw.get('notes')),
        items=[
            {
                'description': _as_optional_str(item.get('description')) or _as_optional_str(item.get('item_name')) or 'Item',
                'hsn_sac': (
                    _as_optional_str(item.get('hsn_sac'))
                    or _as_optional_str(item.get('hsn'))
                    or _as_optional_str(item.get('sac'))
                    or ''
                ),
                'quantity': _as_positive_amount(
                    _first_non_empty_value(item.get('quantity'), item.get('qty'))
                ),
                'rate': _as_amount(
                    _first_non_empty_value(item.get('rate'), item.get('unit_price'), item.get('price'))
                ),
                'tax_rate': _infer_tax_rate(item),
            }
            for item in items_raw
            if isinstance(item, dict)
        ],
    )


def _build_challan_payload(raw: dict[str, Any]) -> DeliveryChallanExtractedPayload:
    items_raw = raw.get('items') if isinstance(raw.get('items'), list) else []

    subtotal = _as_amount(raw.get('subtotal'))
    if subtotal <= 0 and items_raw:
        subtotal = round(
            sum(
                _as_positive_amount(_first_non_empty_value(item.get('quantity'), item.get('qty')))
                * _as_amount(_first_non_empty_value(item.get('rate'), item.get('unit_price'), item.get('price')))
                for item in items_raw
                if isinstance(item, dict)
            ),
            2,
        )

    from_party = _as_optional_str(raw.get('from_party')) or _extract_party_name(
        _first_non_empty_value(raw.get('seller'), raw.get('seller_name'))
    )
    to_party = _as_optional_str(raw.get('to_party')) or _extract_party_name(
        _first_non_empty_value(raw.get('buyer'), raw.get('buyer_name'))
    )

    return DeliveryChallanExtractedPayload(
        challan_number=_as_optional_int(raw.get('challan_number')),
        order_number=_as_optional_str(raw.get('order_number')),
        challan_date=_as_optional_date(raw.get('challan_date')),
        from_party=from_party,
        to_party=to_party,
        subtotal=subtotal,
        notes=_as_optional_str(raw.get('notes')),
        items=[
            {
                'description': _as_optional_str(item.get('description')) or _as_optional_str(item.get('item_name')) or 'Item',
                'quantity': _as_positive_amount(
                    _first_non_empty_value(item.get('quantity'), item.get('qty'))
                ),
                'rate': _as_amount(
                    _first_non_empty_value(item.get('rate'), item.get('unit_price'), item.get('price'))
                ),
            }
            for item in items_raw
            if isinstance(item, dict)
        ],
    )


def _infer_tax_rate(item: dict[str, Any]) -> float:
    direct = _as_amount(item.get('tax_rate'))
    if direct > 0:
        return direct
    cgst = _as_amount(item.get('cgst_rate'))
    sgst = _as_amount(item.get('sgst_rate'))
    igst = _as_amount(item.get('igst_rate'))
    total = cgst + sgst + igst
    return round(total, 2)


def _dig(raw: dict[str, Any], parent_key: str, child_key: str) -> Any:
    parent = raw.get(parent_key)
    if isinstance(parent, dict):
        return parent.get(child_key)
    return None


def _normalize_document_type(value: Any) -> str:
    normalized = str(value or '').strip().lower().replace(' ', '_')
    if normalized in {'gst_invoice', 'invoice', 'tax_invoice'}:
        return 'gst_invoice'
    if normalized in {'delivery_challan', 'challan', 'delivery_note'}:
        return 'delivery_challan'
    return 'unknown'


def _determine_bill_type(
    *,
    document_type: str,
    explicit_transaction_type: Any,
    fallback: InvoiceType,
    company_name: str | None,
    seller_name: str | None,
    buyer_name: str | None,
    from_party: str | None,
    to_party: str | None,
) -> InvoiceType:
    normalized_company = _normalize_name(company_name)
    if normalized_company:
        if document_type == 'delivery_challan':
            normalized_from = _normalize_name(from_party)
            normalized_to = _normalize_name(to_party)
            if normalized_from and normalized_from == normalized_company:
                return InvoiceType.SALES
            if normalized_to and normalized_to == normalized_company:
                return InvoiceType.PURCHASE
        else:
            normalized_seller = _normalize_name(seller_name)
            normalized_buyer = _normalize_name(buyer_name)
            if normalized_seller and normalized_seller == normalized_company:
                return InvoiceType.SALES
            if normalized_buyer and normalized_buyer == normalized_company:
                return InvoiceType.PURCHASE

    explicit = _coerce_invoice_type(explicit_transaction_type)
    if explicit is not None:
        return explicit

    return fallback


def _coerce_invoice_type(value: Any) -> InvoiceType | None:
    normalized = str(value or '').strip().lower()
    if normalized in {'sales', 'purchase'}:
        return InvoiceType(normalized)
    return None


def _normalize_name(value: str | None) -> str:
    if not value:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()
    return re.sub(r'\s+', ' ', normalized)


def _as_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r'\s+', ' ', value.replace(',', ' ')).strip()
    return cleaned if cleaned else None


def _as_optional_date(value: Any) -> date | None:
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

    patterns = (
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
    )
    for pattern in patterns:
        try:
            parsed = datetime.strptime(cleaned, pattern)
            if parsed.year < 2000:
                parsed = parsed.replace(year=parsed.year + 2000)
            return parsed.date()
        except ValueError:
            continue

    return None


def _as_optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _as_amount(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, str):
            normalized = re.sub(r'[^0-9.-]', '', value.replace(',', ''))
            if normalized in {'', '.', '-', '-.'}:
                return 0.0
            return round(max(float(normalized), 0.0), 2)
        return round(max(float(value), 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _as_positive_amount(value: Any) -> float:
    amount = _as_amount(value)
    return amount if amount > 0 else 1.0


def _first_non_empty_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        if isinstance(value, dict):
            if value:
                return value
            continue
        return value
    return None
