from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
from typing import Final

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.storage import remove_temp_file
from app.models.invoice import Invoice, InvoiceItem, InvoiceSource, InvoiceType
from app.models.personal_details import PersonalDetails
from app.models.user import User
from app.schemas.bill import BillUploadResponse
from app.services.ocr import extract_structured_data, extract_text_from_file

router = APIRouter()

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

    try:
        text = extract_text_from_file(processing_path, detected_mime)
        user_personal_details = db.scalar(
            select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id)
        )
        extracted = extract_structured_data(
            text,
            fallback_type=fallback_type,
            company_name=user_personal_details.company_name if user_personal_details else None,
            company_gstin=user_personal_details.gstin_number if user_personal_details else None,
        )

        bill_date = extracted['bill_date'] or date.today()
        total_amount = float(extracted['total_amount'] or 0.0)

        invoice = Invoice(
            owner_id=current_user.id,
            invoice_number=f"OCR-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}",
            invoice_date=bill_date,
            gst_number=extracted['gst_number'],
            type=extracted['inferred_type'],
            subtotal=total_amount,
            gst_amount=0.0,
            total_amount=total_amount,
            source=InvoiceSource.UPLOADED,
            original_file_path=None,
        )
        invoice.items.append(
            InvoiceItem(
                description='Uploaded Bill',
                hsn_sac='',
                quantity=1.0,
                price=total_amount,
                gst_percent=0.0,
                line_total=total_amount,
            )
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
    except Exception:
        db.rollback()
        raise
    finally:
        remove_temp_file(processing_path)

    preview = (text[:200] + '...') if text and len(text) > 200 else text

    return BillUploadResponse(
        upload_id=invoice.id,
        invoice_id=invoice.id,
        file_name=safe_original_name,
        file_path='',
        invoice_date=invoice.invoice_date,
        gst_number=invoice.gst_number,
        total_amount=invoice.total_amount,
        type=invoice.type,
        extracted_text_preview=preview,
        created_at=invoice.created_at or datetime.now(),
    )
