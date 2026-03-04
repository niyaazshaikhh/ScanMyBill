from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.models.invoice import InvoiceType
from app.schemas.bill import (
    BillStructuredData,
    DeliveryChallanExtractedPayload,
    GSTInvoiceExtractedPayload,
)
from app.services.ai_document_processor import extract_document_data


def _extract_party_name(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    if isinstance(value, dict):
        for key in ('name', 'business_name', 'party_name', 'company_name'):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _extract_party_gstin(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip().upper()
        return cleaned if cleaned else None
    if isinstance(value, dict):
        for key in ('gstin', 'gst_number', 'gst'):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip().upper()
    return None


async def process_uploaded_document(
    *,
    file_path: str,
    mime_type: str,
    fallback_type: InvoiceType,
    company_name: str | None,
    company_gstin: str | None,
) -> dict[str, Any]:
    del mime_type, company_gstin

    raw = await extract_document_data(file_path)
    if not isinstance(raw, dict):
        raise ValueError('AI extraction failed')
    if raw.get('error'):
        raise ValueError(str(raw['error']))

    document_type = _normalize_document_type(raw.get('document_type'))
    if document_type == 'unknown':
        raise ValueError('Model returned unknown document type')

    gst_payload = _build_gst_payload(raw)
    challan_payload = _build_challan_payload(raw)

    bill_type = _determine_bill_type(
        document_type=document_type,
        explicit_transaction_type=raw.get('transaction_type'),
        fallback=fallback_type,
        company_name=company_name,
        seller_name=_extract_party_name(raw.get('seller')),
        buyer_name=_extract_party_name(raw.get('buyer')),
        from_party=challan_payload.from_party,
        to_party=challan_payload.to_party,
    )

    warnings = [value for value in raw.get('warnings', []) if isinstance(value, str)]

    structured = BillStructuredData(
        document_type=document_type,
        bill_type=bill_type,
        gst_invoice=gst_payload if document_type == 'gst_invoice' else None,
        delivery_challan=challan_payload if document_type == 'delivery_challan' else None,
        warnings=warnings,
    )

    bill_date = (
        gst_payload.invoice_date if document_type == 'gst_invoice' else challan_payload.challan_date
    ) or _as_optional_date(raw.get('invoice_date')) or _as_optional_date(raw.get('challan_date'))

    total_amount = (
        gst_payload.total_amount if document_type == 'gst_invoice' else challan_payload.subtotal
    )
    if total_amount <= 0:
        total_amount = _as_amount(raw.get('total_amount'))

    gst_number = gst_payload.gst_number

    return {
        'text': '',
        'document_type': document_type,
        'bill_type': bill_type,
        'transaction_type': bill_type.value,
        'bill_date': bill_date,
        'gst_number': gst_number,
        'total_amount': total_amount,
        'gst_invoice': gst_payload,
        'delivery_challan': challan_payload,
        'from_party': challan_payload.from_party,
        'to_party': challan_payload.to_party,
        'structured_data': structured,
    }


def _build_gst_payload(raw: dict[str, Any]) -> GSTInvoiceExtractedPayload:
    seller = raw.get('seller')
    buyer = raw.get('buyer')

    items_raw = raw.get('items') if isinstance(raw.get('items'), list) else []

    return GSTInvoiceExtractedPayload(
        invoice_number=_as_optional_str(raw.get('invoice_number')),
        invoice_date=_as_optional_date(raw.get('invoice_date')),
        place_of_supply=_as_optional_str(raw.get('place_of_supply')),
        place_of_supply_code=_as_optional_str(raw.get('place_of_supply_code')),
        gst_number=_extract_party_gstin(seller) or _as_optional_str(raw.get('gst_number')),
        subtotal=_as_amount(raw.get('subtotal')) or _as_amount(_dig(raw, 'invoice_totals', 'subtotal')),
        gst_amount=_as_amount(raw.get('gst_amount')) or _as_amount(_dig(raw, 'tax_summary', 'total_tax')),
        total_amount=_as_amount(raw.get('total_amount')) or _as_amount(_dig(raw, 'invoice_totals', 'grand_total')),
        notes=_as_optional_str(raw.get('notes')),
        items=[
            {
                'description': _as_optional_str(item.get('description')) or 'Item',
                'hsn_sac': _as_optional_str(item.get('hsn_sac')) or _as_optional_str(item.get('hsn')) or '',
                'quantity': _as_positive_amount(item.get('quantity')),
                'rate': _as_amount(item.get('rate')) or _as_amount(item.get('unit_price')),
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
                _as_positive_amount(item.get('quantity')) * _as_amount(item.get('rate'))
                for item in items_raw
                if isinstance(item, dict)
            ),
            2,
        )

    return DeliveryChallanExtractedPayload(
        challan_number=_as_optional_int(raw.get('challan_number')),
        order_number=_as_optional_str(raw.get('order_number')),
        challan_date=_as_optional_date(raw.get('challan_date')),
        from_party=_as_optional_str(raw.get('from_party')),
        to_party=_as_optional_str(raw.get('to_party')),
        subtotal=subtotal,
        notes=_as_optional_str(raw.get('notes')),
        items=[
            {
                'description': _as_optional_str(item.get('description')) or 'Item',
                'quantity': _as_positive_amount(item.get('quantity')),
                'rate': _as_amount(item.get('rate')),
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
    normalized = str(value or '').strip().lower()
    if normalized in {'gst_invoice', 'delivery_challan'}:
        return normalized
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
    explicit = _coerce_invoice_type(explicit_transaction_type)
    if explicit is not None:
        return explicit

    normalized_company = _normalize_name(company_name)
    if not normalized_company:
        return fallback

    if document_type == 'delivery_challan':
        normalized_from = _normalize_name(from_party)
        normalized_to = _normalize_name(to_party)
        if normalized_from and normalized_from == normalized_company:
            return InvoiceType.SALES
        if normalized_to and normalized_to == normalized_company:
            return InvoiceType.PURCHASE
        return fallback

    normalized_seller = _normalize_name(seller_name)
    normalized_buyer = _normalize_name(buyer_name)
    if normalized_seller and normalized_seller == normalized_company:
        return InvoiceType.SALES
    if normalized_buyer and normalized_buyer == normalized_company:
        return InvoiceType.PURCHASE
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
    cleaned = value.strip()
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
            normalized = value.replace(',', '').strip()
            return round(max(float(normalized), 0.0), 2)
        return round(max(float(value), 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _as_positive_amount(value: Any) -> float:
    amount = _as_amount(value)
    return amount if amount > 0 else 1.0
