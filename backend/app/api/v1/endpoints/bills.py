from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.storage import get_storage_backend, remove_temp_file
from app.models.bill_upload import BillUpload
from app.models.invoice import Invoice, InvoiceSource, InvoiceType
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
}


@router.post('/upload', response_model=BillUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_bill(
    file: UploadFile = File(...),
    invoice_type: str = Form('purchase'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillUploadResponse:
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported file type')

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Empty file upload')

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f'File exceeds {settings.max_upload_mb}MB limit',
        )

    fallback_type = InvoiceType.SALES if invoice_type.lower() == InvoiceType.SALES.value else InvoiceType.PURCHASE

    storage = get_storage_backend()
    stored_path = storage.save_bytes(payload, file.filename or 'bill', subdir='bills')
    processing_path = storage.local_processing_path(stored_path)

    text = extract_text_from_file(processing_path, file.content_type)
    extracted = extract_structured_data(text, fallback_type=fallback_type)

    bill_date = extracted['bill_date'] or date.today()
    total_amount = float(extracted['total_amount'] or 0.0)

    invoice = Invoice(
        owner_id=current_user.id,
        invoice_number=f"OCR-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        invoice_date=bill_date,
        gst_number=extracted['gst_number'],
        type=extracted['inferred_type'],
        subtotal=total_amount,
        gst_amount=0.0,
        total_amount=total_amount,
        source=InvoiceSource.UPLOADED,
        original_file_path=stored_path,
    )
    db.add(invoice)
    db.flush()

    upload = BillUpload(
        owner_id=current_user.id,
        invoice_id=invoice.id,
        file_name=file.filename or 'bill',
        file_path=stored_path,
        mime_type=file.content_type,
        file_size=len(payload),
        ocr_text=text,
        processed=True,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    if processing_path != stored_path:
        remove_temp_file(processing_path)

    preview = (text[:200] + '...') if text and len(text) > 200 else text

    return BillUploadResponse(
        upload_id=upload.id,
        invoice_id=invoice.id,
        file_name=upload.file_name,
        file_path=upload.file_path,
        invoice_date=invoice.invoice_date,
        gst_number=invoice.gst_number,
        total_amount=invoice.total_amount,
        type=invoice.type,
        extracted_text_preview=preview,
        created_at=upload.created_at,
    )