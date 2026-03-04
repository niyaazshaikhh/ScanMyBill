from __future__ import annotations

from datetime import date, datetime
import logging
from pathlib import Path
import re
import tempfile
from typing import Any, Final

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.storage import remove_temp_file
from app.models.invoice import Invoice, InvoiceItem, InvoiceSource, InvoiceType
from app.models.non_gst_challan import NonGSTChallan, NonGSTChallanItem
from app.models.personal_details import PersonalDetails
from app.models.user import User
from app.schemas.bill import (
    BillStructuredData,
    BillUploadResponse,
    DeliveryChallanExtractedItem,
    DeliveryChallanExtractedPayload,
    GSTInvoiceExtractedItem,
    GSTInvoiceExtractedPayload,
)
from app.services.client_resolver import resolve_client
from app.services.document_processor import process_uploaded_document

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/webp',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.xls', '.xlsx'}
MIME_BY_EXTENSION: Final[dict[str, str]] = {
    '.pdf': 'application/pdf',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
ALLOWED_INVOICE_TYPES: Final[set[str]] = {InvoiceType.SALES.value, InvoiceType.PURCHASE.value}


def _detect_mime(payload: bytes) -> str | None:
    if payload.startswith(b'%PDF-'):
        return 'application/pdf'
    if payload.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if payload.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if len(payload) >= 12 and payload[:4] == b'RIFF' and payload[8:12] == b'WEBP':
        return 'image/webp'
    if payload.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'application/vnd.ms-excel'
    if payload.startswith(b'PK') and b'[Content_Types].xml' in payload and b'xl/' in payload:
        return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return None


def _sanitize_display_filename(original_name: str | None, extension: str) -> str:
    stem = Path(original_name or 'bill').stem
    cleaned = ''.join(char for char in stem if char.isalnum() or char in {'-', '_', ' '}).strip()
    if not cleaned:
        cleaned = 'bill'
    return f'{cleaned[:120]}{extension}'


def _coerce_amount(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return round(max(float(value), 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _safe_invoice_number(candidate: Any) -> str:
    if isinstance(candidate, str):
        cleaned = re.sub(r'[^A-Za-z0-9./#_-]', '', candidate.strip().upper())
        if cleaned:
            return cleaned[:20]
    return f"OCR-{datetime.now().strftime('%y%m%d%H%M%S%f')}"[:20]


def _safe_order_number(candidate: Any, *, fallback_sequence: int) -> str:
    if isinstance(candidate, str):
        cleaned = re.sub(r'[^A-Za-z0-9]', '', candidate.strip())
        if cleaned:
            return cleaned[:5]
    return str(fallback_sequence).zfill(5)[-5:]


def _next_challan_sequence_number(db: Session, owner_id: str) -> int:
    latest = db.scalar(
        select(func.max(NonGSTChallan.sequence_number)).where(NonGSTChallan.owner_id == owner_id)
    )
    return int(latest or 0) + 1


def _challan_sequence_exists(db: Session, owner_id: str, sequence_number: int) -> bool:
    if sequence_number <= 0:
        return False
    existing_id = db.scalar(
        select(NonGSTChallan.id).where(
            NonGSTChallan.owner_id == owner_id,
            NonGSTChallan.sequence_number == sequence_number,
        )
    )
    return existing_id is not None


def _build_invoice_from_extraction(owner_id: str, extracted: dict[str, Any]) -> Invoice:
    gst_payload = extracted.get('gst_invoice') if isinstance(extracted.get('gst_invoice'), dict) else {}

    bill_date = gst_payload.get('invoice_date') or extracted.get('bill_date') or date.today()
    if not isinstance(bill_date, date):
        bill_date = date.today()
    subtotal = _coerce_amount(gst_payload.get('subtotal'))
    gst_amount = _coerce_amount(gst_payload.get('gst_amount'))
    total_amount = _coerce_amount(gst_payload.get('total_amount'))
    if total_amount <= 0:
        total_amount = _coerce_amount(extracted.get('total_amount'))
    inferred_type = extracted.get('inferred_type')
    invoice_type = inferred_type if isinstance(inferred_type, InvoiceType) else InvoiceType.PURCHASE

    invoice = Invoice(
        owner_id=owner_id,
        invoice_number=_safe_invoice_number(gst_payload.get('invoice_number')),
        invoice_date=bill_date,
        place_of_supply=gst_payload.get('place_of_supply'),
        place_of_supply_code=gst_payload.get('place_of_supply_code'),
        gst_number=gst_payload.get('gst_number') or extracted.get('gst_number'),
        type=invoice_type,
        subtotal=0.0,
        gst_amount=0.0,
        total_amount=0.0,
        source=InvoiceSource.UPLOADED,
        notes=gst_payload.get('notes'),
        original_file_path=None,
    )

    items_payload = gst_payload.get('items') if isinstance(gst_payload.get('items'), list) else []
    item_subtotal = 0.0
    item_gst = 0.0
    for raw_item in items_payload:
        if not isinstance(raw_item, dict):
            continue

        description_raw = raw_item.get('description')
        description = str(description_raw).strip() if description_raw else 'Uploaded Bill Item'
        hsn_sac_raw = raw_item.get('hsn_sac')
        hsn_sac = str(hsn_sac_raw).strip() if hsn_sac_raw else ''
        quantity = _coerce_amount(raw_item.get('quantity'))
        rate = _coerce_amount(raw_item.get('rate'))
        tax_rate = _coerce_amount(raw_item.get('tax_rate'))

        if quantity <= 0:
            quantity = 1.0

        base = round(quantity * rate, 2)
        tax_value = round(base * (tax_rate / 100.0), 2)
        line_total = round(base + tax_value, 2)

        item_subtotal += base
        item_gst += tax_value

        invoice.items.append(
            InvoiceItem(
                description=description[:255],
                hsn_sac=hsn_sac[:8],
                quantity=quantity,
                price=rate,
                gst_percent=tax_rate,
                line_total=line_total,
            )
        )

    if not invoice.items:
        fallback_line_total = total_amount if total_amount > 0 else subtotal
        invoice.items.append(
            InvoiceItem(
                description='Uploaded Bill',
                hsn_sac='',
                quantity=1.0,
                price=fallback_line_total,
                gst_percent=0.0,
                line_total=fallback_line_total,
            )
        )
        item_subtotal = fallback_line_total
        item_gst = 0.0

    if subtotal <= 0:
        subtotal = item_subtotal
    if gst_amount <= 0:
        gst_amount = item_gst
    if total_amount <= 0:
        total_amount = subtotal + gst_amount

    invoice.subtotal = round(subtotal, 2)
    invoice.gst_amount = round(gst_amount, 2)
    invoice.total_amount = round(total_amount, 2)
    return invoice


def _build_delivery_challan_from_extraction(
    db: Session,
    *,
    owner_id: str,
    client_id: str,
    extracted: dict[str, Any],
) -> NonGSTChallan:
    challan_payload = (
        extracted.get('delivery_challan') if isinstance(extracted.get('delivery_challan'), dict) else {}
    )

    try:
        requested_challan_number = int(challan_payload.get('challan_number') or 0)
    except (TypeError, ValueError):
        requested_challan_number = 0
    if requested_challan_number > 0 and not _challan_sequence_exists(db, owner_id, requested_challan_number):
        sequence_number = requested_challan_number
    else:
        sequence_number = _next_challan_sequence_number(db, owner_id)
    challan_date = challan_payload.get('challan_date') or extracted.get('bill_date') or date.today()
    if not isinstance(challan_date, date):
        challan_date = date.today()
    subtotal = _coerce_amount(challan_payload.get('subtotal'))
    if subtotal <= 0:
        subtotal = _coerce_amount(extracted.get('total_amount'))

    challan = NonGSTChallan(
        owner_id=owner_id,
        client_id=client_id,
        challan_number=_safe_order_number(
            challan_payload.get('order_number'),
            fallback_sequence=sequence_number,
        ),
        sequence_number=sequence_number,
        challan_date=challan_date,
        subtotal=0.0,
        notes=challan_payload.get('notes'),
        original_file_path=None,
    )

    items_payload = challan_payload.get('items') if isinstance(challan_payload.get('items'), list) else []
    computed_subtotal = 0.0
    for raw_item in items_payload:
        if not isinstance(raw_item, dict):
            continue

        description_raw = raw_item.get('description')
        description = str(description_raw).strip() if description_raw else 'Uploaded Challan Item'
        quantity = _coerce_amount(raw_item.get('quantity'))
        rate = _coerce_amount(raw_item.get('rate'))

        if quantity <= 0:
            quantity = 1.0

        line_total = round(quantity * rate, 2)
        computed_subtotal += line_total

        challan.items.append(
            NonGSTChallanItem(
                description=description[:255],
                quantity=quantity,
                rate=rate,
                line_total=line_total,
            )
        )

    if not challan.items:
        fallback_line_total = subtotal
        challan.items.append(
            NonGSTChallanItem(
                description='Uploaded Challan',
                quantity=1.0,
                rate=fallback_line_total,
                line_total=fallback_line_total,
            )
        )
        computed_subtotal = fallback_line_total

    if subtotal <= 0:
        subtotal = computed_subtotal

    challan.subtotal = round(subtotal, 2)
    return challan


def _build_invoice_structured_data(invoice: Invoice, warnings: list[str]) -> BillStructuredData:
    gst_invoice_items = [
        GSTInvoiceExtractedItem(
            description=item.description,
            hsn_sac=item.hsn_sac or '',
            quantity=round(item.quantity, 2),
            rate=round(item.price, 2),
            tax_rate=round(item.gst_percent, 2),
        )
        for item in invoice.items
    ]

    return BillStructuredData(
        document_type='gst_invoice',
        bill_type=invoice.type,
        gst_invoice=GSTInvoiceExtractedPayload(
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            place_of_supply=invoice.place_of_supply,
            place_of_supply_code=invoice.place_of_supply_code,
            gst_number=invoice.gst_number,
            subtotal=round(invoice.subtotal, 2),
            gst_amount=round(invoice.gst_amount, 2),
            total_amount=round(invoice.total_amount, 2),
            notes=invoice.notes,
            items=gst_invoice_items,
        ),
        delivery_challan=None,
        warnings=warnings,
    )


def _build_challan_structured_data(
    challan: NonGSTChallan,
    *,
    bill_type: InvoiceType,
    warnings: list[str],
    from_party: str | None = None,
    to_party: str | None = None,
) -> BillStructuredData:
    challan_items = [
        DeliveryChallanExtractedItem(
            description=item.description,
            quantity=round(item.quantity, 2),
            rate=round(item.rate, 2),
        )
        for item in challan.items
    ]

    return BillStructuredData(
        document_type='delivery_challan',
        bill_type=bill_type,
        gst_invoice=None,
        delivery_challan=DeliveryChallanExtractedPayload(
            challan_number=challan.sequence_number,
            order_number=challan.challan_number,
            challan_date=challan.challan_date,
            from_party=from_party,
            to_party=to_party,
            subtotal=round(challan.subtotal, 2),
            notes=challan.notes,
            items=challan_items,
        ),
        warnings=warnings,
    )


@router.post('/upload', response_model=BillUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_bill(
    file: UploadFile = File(...),
    invoice_type: str = Form('purchase'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillUploadResponse:
    mime_type = (file.content_type or '').lower()
    extension = Path(file.filename or '').suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported file type')
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported file type')

    normalized_invoice_type = invoice_type.strip().lower()
    if normalized_invoice_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid invoice type')

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Empty file upload')

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f'File exceeds {settings.max_upload_mb}MB limit',
        )

    detected_mime = _detect_mime(payload)
    expected_mime = MIME_BY_EXTENSION.get(extension)
    if not detected_mime or (expected_mime and detected_mime != expected_mime):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Uploaded file content is invalid')

    if mime_type and mime_type == 'image/jpg':
        mime_type = 'image/jpeg'
    if mime_type and mime_type != detected_mime:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='File MIME type does not match file content')

    safe_original_name = _sanitize_display_filename(file.filename, extension)
    fallback_type = InvoiceType(normalized_invoice_type)

    processing_path = ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
        temp_file.write(payload)
        processing_path = temp_file.name

    created_invoice: Invoice | None = None
    created_challan: NonGSTChallan | None = None
    extracted: dict[str, Any] = {}
    processed: dict[str, Any] = {}

    try:
        user_personal_details = db.scalar(
            select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id)
        )
        try:
            processed = await process_uploaded_document(
                file_path=processing_path,
                mime_type=detected_mime,
                fallback_type=fallback_type,
                company_name=user_personal_details.company_name if user_personal_details else None,
                company_gstin=user_personal_details.gstin_number if user_personal_details else None,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        gst_payload_model = processed.get('gst_invoice')
        challan_payload_model = processed.get('delivery_challan')
        extracted = {
            'document_type': processed.get('document_type'),
            'bill_date': processed.get('bill_date'),
            'gst_number': processed.get('gst_number'),
            'total_amount': processed.get('total_amount'),
            'inferred_type': processed.get('bill_type'),
            'gst_invoice': (
                gst_payload_model.model_dump(mode='python')
                if isinstance(gst_payload_model, GSTInvoiceExtractedPayload)
                else {}
            ),
            'delivery_challan': (
                challan_payload_model.model_dump(mode='python')
                if isinstance(challan_payload_model, DeliveryChallanExtractedPayload)
                else {}
            ),
        }

        document_type = str(extracted.get('document_type') or 'gst_invoice')
        if document_type == 'delivery_challan':
            challan_payload = (
                extracted.get('delivery_challan')
                if isinstance(extracted.get('delivery_challan'), dict)
                else {}
            )
            transaction_type = extracted.get('inferred_type')
            client_name_source = (
                challan_payload.get('to_party')
                if transaction_type == InvoiceType.SALES
                else challan_payload.get('from_party')
            )
            client_name = (
                client_name_source.strip()
                if isinstance(client_name_source, str)
                else ''
            )
            if not client_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Unable to determine client from document',
                )
            try:
                client_id = resolve_client(
                    db,
                    client_name=client_name,
                    owner_id=current_user.id,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Unable to determine client from document',
                ) from exc

            created_challan = _build_delivery_challan_from_extraction(
                db,
                owner_id=current_user.id,
                client_id=client_id,
                extracted=extracted,
            )
            db.add(created_challan)
        else:
            created_invoice = _build_invoice_from_extraction(
                owner_id=current_user.id,
                extracted=extracted,
            )
            invoice_number = created_invoice.invoice_number.strip()
            created_invoice.invoice_number = invoice_number
            existing_invoice = (
                db.query(Invoice)
                .filter(
                    Invoice.owner_id == current_user.id,
                    Invoice.invoice_number == invoice_number,
                )
                .first()
            )
            if existing_invoice is not None:
                logger.warning(
                    'Duplicate invoice upload attempt',
                    extra={
                        'owner_id': str(current_user.id),
                        'invoice_number': invoice_number,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'Invoice {invoice_number} already exists',
                )
            db.add(created_invoice)

        db.commit()

        if created_invoice is not None:
            db.refresh(created_invoice)
        if created_challan is not None:
            db.refresh(created_challan)
    except Exception:
        db.rollback()
        raise
    finally:
        remove_temp_file(processing_path)

    text = str(processed.get('text') or '')
    preview = (text[:200] + '...') if text and len(text) > 200 else text
    warnings = [
        value
        for value in (
            processed.get('structured_data').warnings
            if isinstance(processed.get('structured_data'), BillStructuredData)
            else []
        )
        if isinstance(value, str)
    ]

    if created_invoice is not None:
        structured_data = _build_invoice_structured_data(created_invoice, warnings)
        return BillUploadResponse(
            upload_id=created_invoice.id,
            invoice_id=created_invoice.id,
            delivery_challan_id=None,
            document_type='gst_invoice',
            target_route='/invoices',
            file_name=safe_original_name,
            file_path='',
            invoice_date=created_invoice.invoice_date,
            gst_number=created_invoice.gst_number,
            total_amount=round(created_invoice.total_amount, 2),
            type=created_invoice.type,
            structured_data=structured_data,
            extracted_text_preview=preview,
            created_at=created_invoice.created_at or datetime.now(),
        )

    if created_challan is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Bill upload failed.')

    inferred_type = extracted.get('inferred_type')
    bill_type = inferred_type if isinstance(inferred_type, InvoiceType) else fallback_type
    structured_data = _build_challan_structured_data(
        created_challan,
        bill_type=bill_type,
        warnings=warnings,
        from_party=(
            extracted.get('delivery_challan', {}).get('from_party')
            if isinstance(extracted.get('delivery_challan'), dict)
            else None
        ),
        to_party=(
            extracted.get('delivery_challan', {}).get('to_party')
            if isinstance(extracted.get('delivery_challan'), dict)
            else None
        ),
    )

    return BillUploadResponse(
        upload_id=created_challan.id,
        invoice_id=None,
        delivery_challan_id=created_challan.id,
        document_type='delivery_challan',
        target_route='/invoices/delivery-challan',
        file_name=safe_original_name,
        file_path='',
        invoice_date=created_challan.challan_date,
        gst_number=extracted.get('gst_number') if isinstance(extracted.get('gst_number'), str) else None,
        total_amount=round(created_challan.subtotal, 2),
        type=bill_type,
        structured_data=structured_data,
        extracted_text_preview=preview,
        created_at=created_challan.created_at or datetime.now(),
    )
