from __future__ import annotations

from datetime import date
from io import BytesIO
import logging
import mimetypes
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageSequence, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.storage import get_storage_backend
from app.models.bill_upload import BillUpload
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceItem, InvoiceSource, InvoiceType
from app.models.personal_details import PersonalDetails
from app.models.user import User
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    LatestCreatedInvoiceResponse,
)
from app.services.pdf_invoice_service import (
    PDFInvoiceDataError,
    PDFInvoiceGenerationError,
    PDFInvoiceTemplateError,
    generate_invoice_pdf,
    remove_generated_pdf,
    resolve_generated_pdf_path,
)
from app.services.pdf_service import build_invoice_pdf
from app.services.notifications import create_notification
from app.utils.pdf_filename import build_bill_pdf_filename
from app.utils.period import matches_bucket, valid_period

router = APIRouter()
logger = logging.getLogger(__name__)


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    serialized_items = []
    for item in invoice.items:
        amount_before_tax = item.quantity * item.price
        total_tax_amount = amount_before_tax * (item.gst_percent / 100.0)
        cgst = total_tax_amount / 2.0
        sgst_utgst = total_tax_amount / 2.0
        grand_total = amount_before_tax + total_tax_amount
        serialized_items.append(
            {
                'id': item.id,
                'description': item.description,
                'hsn_sac': item.hsn_sac,
                'quantity': item.quantity,
                'rate': round(item.price, 2),
                'tax_rate': round(item.gst_percent, 2),
                'amount_before_tax': round(amount_before_tax, 2),
                'cgst': round(cgst, 2),
                'sgst_utgst': round(sgst_utgst, 2),
                'total_tax_amount': round(total_tax_amount, 2),
                'grand_total': round(grand_total, 2),
            }
        )

    return InvoiceResponse(
        id=invoice.id,
        client_id=invoice.client_id,
        client_name=invoice.client.name if invoice.client else None,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        place_of_supply=invoice.place_of_supply,
        place_of_supply_code=invoice.place_of_supply_code,
        gst_number=invoice.gst_number,
        type=invoice.type,
        subtotal=round(invoice.subtotal, 2),
        gst_amount=round(invoice.gst_amount, 2),
        total_amount=round(invoice.total_amount, 2),
        source=invoice.source,
        notes=invoice.notes,
        original_file_path=invoice.original_file_path,
        created_at=invoice.created_at,
        items=serialized_items,
    )


def _parse_invoice_type(invoice_type: str | None) -> InvoiceType | None:
    if not invoice_type:
        return None
    value = invoice_type.lower()
    if value not in {InvoiceType.SALES.value, InvoiceType.PURCHASE.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid invoice type')
    return InvoiceType(value)


def _financial_year_bounds(target_date: date) -> tuple[date, date]:
    start_year = target_date.year if target_date.month >= 4 else target_date.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 4, 1)


def _financial_year_prefix(target_date: date) -> str:
    start_year = target_date.year if target_date.month >= 4 else target_date.year - 1
    return f'{start_year}-{(start_year + 1) % 100:02d}'


def _format_bank_details(personal_details: PersonalDetails | None) -> str:
    if not personal_details:
        return 'N/A'

    parts: list[str] = []
    if personal_details.bank_name:
        parts.append(f'Bank: {personal_details.bank_name}')
    if personal_details.account_number:
        parts.append(f'Account No: {personal_details.account_number}')
    if personal_details.branch:
        parts.append(f'Branch: {personal_details.branch}')
    if personal_details.ifsc_code:
        parts.append(f'IFSC: {personal_details.ifsc_code}')
    return ' | '.join(parts) if parts else 'N/A'


def _build_invoice_pdf_data(
    invoice: Invoice,
    *,
    owner_id: str,
    company_details: PersonalDetails | None,
    client: Client | None,
) -> dict[str, Any]:
    company_state_code = (company_details.state_code if company_details else '') or ''
    invoice_state_code = invoice.place_of_supply_code or ''

    is_intra_state = bool(company_state_code and invoice_state_code and company_state_code == invoice_state_code)
    if is_intra_state:
        cgst = round(invoice.gst_amount / 2.0, 2)
        sgst = round(invoice.gst_amount / 2.0, 2)
        igst = 0.0
    else:
        cgst = 0.0
        sgst = 0.0
        igst = round(invoice.gst_amount, 2)

    item_rows: list[dict[str, Any]] = []
    for item in invoice.items:
        taxable_amount = round(item.quantity * item.price, 2)
        item_rows.append(
            {
                'description': item.description,
                'hsn': item.hsn_sac or '',
                'quantity': round(item.quantity, 2),
                'rate': round(item.price, 2),
                'tax_percent': round(item.gst_percent, 2),
                'amount': taxable_amount,
            }
        )
    if not item_rows:
        # Legacy OCR uploads may not contain itemized rows; provide a synthetic row for template rendering.
        item_rows.append(
            {
                'description': invoice.notes or 'Uploaded Bill',
                'hsn': '',
                'quantity': 1.0,
                'rate': round(invoice.subtotal, 2),
                'tax_percent': 0.0,
                'amount': round(invoice.subtotal, 2),
            }
        )

    return {
        'user_id': owner_id,
        'company_name': company_details.company_name if company_details and company_details.company_name else 'ScanMyBill',
        'company_address': company_details.address if company_details and company_details.address else 'N/A',
        'gstin': company_details.gstin_number if company_details and company_details.gstin_number else 'N/A',
        'invoice_number': invoice.invoice_number,
        'invoice_date': invoice.invoice_date.isoformat(),
        'place_of_supply': invoice.place_of_supply or 'N/A',
        'state_code': invoice.place_of_supply_code or 'N/A',
        'client_name': client.name if client else 'N/A',
        'client_address': client.address if client and client.address else 'N/A',
        'client_gstin': client.gst_number if client and client.gst_number else 'N/A',
        'items': item_rows,
        'subtotal': round(invoice.subtotal, 2),
        'cgst': cgst,
        'sgst': sgst,
        'igst': igst,
        'total': round(invoice.total_amount, 2),
        'bank_details': _format_bank_details(company_details),
    }


def _build_sales_invoice_from_payload(payload: InvoiceCreate, *, owner_id: str) -> Invoice:
    subtotal = 0.0
    gst_amount = 0.0

    invoice = Invoice(
        owner_id=owner_id,
        client_id=payload.client_id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        place_of_supply=payload.place_of_supply,
        place_of_supply_code=payload.place_of_supply_code,
        gst_number=None,
        type=InvoiceType.SALES,
        source=InvoiceSource.CREATED,
        notes=payload.notes,
    )

    for item_data in payload.items:
        base = item_data.quantity * item_data.rate
        item_gst = base * (item_data.tax_rate / 100.0)
        line_total = base + item_gst

        subtotal += base
        gst_amount += item_gst

        item = InvoiceItem(
            description=item_data.description,
            hsn_sac=item_data.hsn_sac,
            quantity=item_data.quantity,
            price=item_data.rate,
            gst_percent=item_data.tax_rate,
            line_total=line_total,
        )
        invoice.items.append(item)

    invoice.subtotal = round(subtotal, 2)
    invoice.gst_amount = round(gst_amount, 2)
    invoice.total_amount = round(subtotal + gst_amount, 2)
    return invoice


def _raise_pdf_generation_http_error(exc: Exception) -> None:
    if isinstance(exc, PDFInvoiceDataError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if isinstance(exc, PDFInvoiceTemplateError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    if isinstance(exc, PDFInvoiceGenerationError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to generate invoice PDF') from exc


def _create_notification_best_effort(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None,
) -> None:
    try:
        notification = create_notification(
            db,
            user_id=user_id,
            title=title,
            message=message,
            route=route,
        )
        if notification:
            db.commit()
    except Exception:
        db.rollback()


def _resolve_invoice_pdf_for_response(
    invoice: Invoice,
    *,
    db: Session,
    owner_id: str,
    company_details: PersonalDetails | None,
) -> tuple[Path, str | None]:
    invoice_pdf_data = _build_invoice_pdf_data(
        invoice,
        owner_id=owner_id,
        company_details=company_details,
        client=invoice.client,
    )
    try:
        generated_pdf_path = generate_invoice_pdf(invoice_pdf_data)
    except Exception as exc:
        _raise_pdf_generation_http_error(exc)

    try:
        absolute_pdf_path = resolve_generated_pdf_path(generated_pdf_path)
    except PDFInvoiceGenerationError as exc:
        _raise_pdf_generation_http_error(exc)

    if not absolute_pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Generated invoice PDF missing')

    return absolute_pdf_path, generated_pdf_path


def _generated_invoice_pdf_file_response(
    invoice: Invoice,
    *,
    db: Session,
    owner_id: str,
    company_details: PersonalDetails | None,
    inline: bool,
) -> FileResponse:
    absolute_pdf_path, cleanup_path = _resolve_invoice_pdf_for_response(
        invoice,
        db=db,
        owner_id=owner_id,
        company_details=company_details,
    )
    filename = build_bill_pdf_filename(
        bill_date=invoice.invoice_date,
        document_number=invoice.invoice_number,
        client_name=invoice.client.name if invoice.client else None,
    )
    disposition = 'inline' if inline else 'attachment'
    background = BackgroundTask(remove_generated_pdf, cleanup_path) if cleanup_path else None
    return FileResponse(
        path=str(absolute_pdf_path),
        media_type='application/pdf',
        filename=filename,
        headers={'Content-Disposition': f'{disposition}; filename="{filename}"'},
        background=background,
    )


def _is_uploaded_invoice(invoice: Invoice) -> bool:
    return invoice.source == InvoiceSource.UPLOADED and bool(invoice.original_file_path)


def _build_uploaded_invoice_filename(invoice: Invoice) -> str:
    suffix = Path(invoice.original_file_path or '').suffix.lower() or '.bin'
    base = re.sub(r'[^A-Za-z0-9._-]+', '-', invoice.invoice_number or 'uploaded-invoice').strip('-_.')
    if not base:
        base = 'uploaded-invoice'
    return f'{base[:80]}{suffix}'


def _as_uploaded_invoice_file_response(
    invoice: Invoice,
    *,
    inline: bool,
) -> Response:
    stored_path = invoice.original_file_path
    if not stored_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded invoice file not found')

    storage = get_storage_backend()
    try:
        file_bytes = storage.read_bytes(stored_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded invoice file not found') from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to read uploaded invoice file',
        ) from exc

    media_type = mimetypes.guess_type(stored_path)[0] or 'application/octet-stream'
    filename = _build_uploaded_invoice_filename(invoice)
    disposition = 'inline' if inline else 'attachment'
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={'Content-Disposition': f'{disposition}; filename="{filename}"'},
    )


def _image_bytes_to_pdf_bytes(image_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            frames: list[Image.Image]
            if getattr(image, 'is_animated', False):
                frames = [frame.convert('RGB') for frame in ImageSequence.Iterator(image)]
            else:
                frames = [image.convert('RGB')]
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Uploaded invoice file is not a supported image or PDF for folder export.',
        ) from exc

    if not frames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Uploaded invoice image has no renderable pages for folder export.',
        )

    output = BytesIO()
    first_frame, *remaining_frames = frames
    first_frame.save(output, format='PDF', save_all=bool(remaining_frames), append_images=remaining_frames)
    return output.getvalue()


def _uploaded_invoice_pdf_bytes(invoice: Invoice) -> bytes:
    stored_path = invoice.original_file_path
    if not stored_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded invoice file not found')

    storage = get_storage_backend()
    try:
        file_bytes = storage.read_bytes(stored_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded invoice file not found') from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to read uploaded invoice file',
        ) from exc

    media_type = mimetypes.guess_type(stored_path)[0] or ''
    suffix = Path(stored_path).suffix.lower()
    if media_type == 'application/pdf' or suffix == '.pdf':
        return file_bytes
    return _image_bytes_to_pdf_bytes(file_bytes)


def _append_pdf_bytes(writer: PdfWriter, pdf_bytes: bytes, *, invoice_number: str) -> None:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if len(reader.pages) == 0:
            raise ValueError('No pages found in source PDF.')
        writer.append(reader)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to append invoice {invoice_number} to folder export.',
        ) from exc


def _build_basic_invoice_pdf_bytes(invoice: Invoice) -> bytes:
    try:
        return build_invoice_pdf(invoice)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to generate fallback invoice PDF for invoice {invoice.invoice_number}.',
        ) from exc


@router.get('', response_model=InvoiceListResponse)
def list_invoices(
    period: str = Query('monthly'),
    invoice_type: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    financial_year_start: int | None = Query(None, ge=2000, le=2100),
    bucket: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceListResponse:
    normalized_period = valid_period(period)
    typed = _parse_invoice_type(invoice_type)

    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.owner_id == current_user.id)
        .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
    )
    if typed:
        stmt = stmt.where(Invoice.type == typed)
    if financial_year_start is not None:
        start = date(financial_year_start, 4, 1)
        end = date(financial_year_start + 1, 4, 1)
        stmt = stmt.where(Invoice.invoice_date >= start, Invoice.invoice_date < end)
    elif year is not None:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        stmt = stmt.where(Invoice.invoice_date >= start, Invoice.invoice_date < end)

    invoices = list(db.scalars(stmt).all())
    if bucket:
        invoices = [inv for inv in invoices if matches_bucket(inv.invoice_date, normalized_period, bucket)]

    serialized = [_invoice_to_response(invoice) for invoice in invoices]
    return InvoiceListResponse(invoices=serialized, count=len(serialized))


@router.get('/latest-created', response_model=LatestCreatedInvoiceResponse)
def latest_created_invoice(
    invoice_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LatestCreatedInvoiceResponse:
    if invoice_date:
        financial_year_start, financial_year_end = _financial_year_bounds(invoice_date)
        prefix = _financial_year_prefix(invoice_date)
        serial_pattern = re.compile(rf'^{re.escape(prefix)}/(\d{{1,3}})$')

        invoices = list(
            db.scalars(
                select(Invoice).where(
                    Invoice.owner_id == current_user.id,
                    Invoice.type == InvoiceType.SALES,
                    Invoice.invoice_date >= financial_year_start,
                    Invoice.invoice_date < financial_year_end,
                )
                .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
            ).all()
        )

        # Follow the same "most recent bill first" ordering as /invoices and
        # increment from the newest valid FY-style invoice number.
        for invoice in invoices:
            match = serial_pattern.match((invoice.invoice_number or '').strip().upper())
            if not match:
                continue
            serial_value = int(match.group(1))
            if serial_value <= 0 or serial_value > 999:
                continue
            return LatestCreatedInvoiceResponse(invoice_number=f'{prefix}/{serial_value:03d}')

        return LatestCreatedInvoiceResponse(invoice_number=None)

    latest = db.scalar(
        select(Invoice)
        .where(Invoice.owner_id == current_user.id, Invoice.source == InvoiceSource.CREATED)
        .order_by(Invoice.created_at.desc(), Invoice.invoice_date.desc())
        .limit(1)
    )
    if not latest:
        return LatestCreatedInvoiceResponse(invoice_number=None)
    return LatestCreatedInvoiceResponse(invoice_number=latest.invoice_number)


@router.post('/create', response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceResponse:
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one item is required')

    client = db.scalar(
        select(Client).where(Client.id == payload.client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected client is invalid')

    duplicate_invoice_id = db.scalar(
        select(Invoice.id).where(
            Invoice.owner_id == current_user.id,
            Invoice.invoice_number == payload.invoice_number,
        )
    )
    if duplicate_invoice_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invoice Number already exists.')

    invoice = _build_sales_invoice_from_payload(payload, owner_id=current_user.id)

    db.add(invoice)
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invoice Number already exists.') from exc
    except Exception:
        db.rollback()
        raise

    refreshed = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice.id, Invoice.owner_id == current_user.id)
    )
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to load invoice')

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Invoice Created',
        message=f'Invoice {refreshed.invoice_number} has been created and saved.',
        route='/invoices',
    )

    return _invoice_to_response(refreshed)


@router.post('/create/pdf')
def create_invoice_pdf(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one item is required')

    client = db.scalar(
        select(Client).where(Client.id == payload.client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected client is invalid')

    invoice = _build_sales_invoice_from_payload(payload, owner_id=current_user.id)
    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    invoice_pdf_data = _build_invoice_pdf_data(
        invoice,
        owner_id=current_user.id,
        company_details=company_details,
        client=client,
    )

    try:
        generated_pdf_path = generate_invoice_pdf(invoice_pdf_data)
    except Exception as exc:
        _raise_pdf_generation_http_error(exc)

    try:
        absolute_pdf_path = resolve_generated_pdf_path(generated_pdf_path)
    except PDFInvoiceGenerationError as exc:
        _raise_pdf_generation_http_error(exc)

    if not absolute_pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Generated invoice PDF missing')

    filename = build_bill_pdf_filename(
        bill_date=invoice.invoice_date,
        document_number=invoice.invoice_number,
        client_name=client.name if client else None,
    )
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Invoice PDF Exported',
        message=f'Invoice {invoice.invoice_number} PDF has been exported.',
        route='/create',
    )
    background = BackgroundTask(remove_generated_pdf, generated_pdf_path)
    return FileResponse(
        path=str(absolute_pdf_path),
        media_type='application/pdf',
        filename=filename,
        background=background,
    )


@router.get('/export-folder')
def export_folder(
    period: str = Query('monthly'),
    bucket: str = Query(..., min_length=1),
    invoice_type: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    financial_year_start: int | None = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    normalized_period = valid_period(period)
    typed = _parse_invoice_type(invoice_type)

    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.owner_id == current_user.id)
        .order_by(Invoice.invoice_date.asc())
    )

    if typed:
        stmt = stmt.where(Invoice.type == typed)
    if financial_year_start is not None:
        start = date(financial_year_start, 4, 1)
        end = date(financial_year_start + 1, 4, 1)
        stmt = stmt.where(Invoice.invoice_date >= start, Invoice.invoice_date < end)
    elif year is not None:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        stmt = stmt.where(Invoice.invoice_date >= start, Invoice.invoice_date < end)

    invoices = [
        invoice
        for invoice in db.scalars(stmt).all()
        if matches_bucket(invoice.invoice_date, normalized_period, bucket)
    ]

    if not invoices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No invoices in selected folder')

    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    writer = PdfWriter()
    temporary_generated_paths: list[str] = []

    try:
        for invoice in invoices:
            if _is_uploaded_invoice(invoice):
                try:
                    uploaded_pdf_bytes = _uploaded_invoice_pdf_bytes(invoice)
                    _append_pdf_bytes(writer, uploaded_pdf_bytes, invoice_number=invoice.invoice_number)
                    continue
                except HTTPException as exc:
                    if exc.status_code not in {
                        status.HTTP_404_NOT_FOUND,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    }:
                        raise
                    logger.warning(
                        'Falling back to generated PDF for uploaded invoice export due to missing/unsupported source file. '
                        'invoice_id=%s owner_id=%s path=%s status=%s',
                        invoice.id,
                        current_user.id,
                        invoice.original_file_path,
                        exc.status_code,
                    )

            try:
                absolute_pdf_path, cleanup_path = _resolve_invoice_pdf_for_response(
                    invoice,
                    db=db,
                    owner_id=current_user.id,
                    company_details=company_details,
                )
                if cleanup_path:
                    temporary_generated_paths.append(cleanup_path)

                writer.append(str(absolute_pdf_path))
            except HTTPException as exc:
                if exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                    raise
                logger.warning(
                    'Falling back to basic invoice PDF for folder export due to advanced PDF generation failure. '
                    'invoice_id=%s owner_id=%s detail=%s',
                    invoice.id,
                    current_user.id,
                    exc.detail,
                )
                fallback_pdf_bytes = _build_basic_invoice_pdf_bytes(invoice)
                _append_pdf_bytes(writer, fallback_pdf_bytes, invoice_number=invoice.invoice_number)
            except Exception as exc:
                logger.warning(
                    'Falling back to basic invoice PDF for folder export due to append failure. '
                    'invoice_id=%s owner_id=%s error=%s',
                    invoice.id,
                    current_user.id,
                    str(exc),
                )
                fallback_pdf_bytes = _build_basic_invoice_pdf_bytes(invoice)
                _append_pdf_bytes(writer, fallback_pdf_bytes, invoice_number=invoice.invoice_number)

        output = BytesIO()
        try:
            writer.write(output)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to build merged folder export PDF.',
            ) from exc
        pdf_bytes = output.getvalue()
    finally:
        if hasattr(writer, 'close'):
            writer.close()
        for path in temporary_generated_paths:
            remove_generated_pdf(path)

    if not pdf_bytes:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to build folder export PDF')

    filename = f'{normalized_period}-{bucket}-export.pdf'.replace(' ', '-').lower()

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Invoice Folder Exported',
        message=f'{bucket} folder export is ready for download.',
        route='/invoices',
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@router.delete(
    '/{invoice_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    invoice = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')
    invoice_number = invoice.invoice_number

    uploads = list(
        db.scalars(
            select(BillUpload).where(
                BillUpload.invoice_id == invoice.id,
                BillUpload.owner_id == current_user.id,
            )
        ).all()
    )
    stored_paths = {path for path in [invoice.original_file_path, *(item.file_path for item in uploads)] if path}

    for upload in uploads:
        db.delete(upload)
    db.delete(invoice)
    db.commit()

    storage = get_storage_backend()
    for stored_path in stored_paths:
        try:
            storage.delete_file(stored_path)
        except Exception:
            continue

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Invoice Deleted',
        message=f'Invoice {invoice_number} has been deleted.',
        route='/invoices',
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/{invoice_id}', response_model=InvoiceResponse)
def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceResponse:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')

    return _invoice_to_response(invoice)


@router.get('/{invoice_id}/preview')
def get_invoice_preview(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')

    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    if _is_uploaded_invoice(invoice):
        try:
            return _as_uploaded_invoice_file_response(invoice, inline=True)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            logger.warning(
                'Uploaded invoice preview source file missing. Falling back to generated PDF. '
                'invoice_id=%s owner_id=%s path=%s',
                invoice.id,
                current_user.id,
                invoice.original_file_path,
            )

    return _generated_invoice_pdf_file_response(
        invoice,
        db=db,
        owner_id=current_user.id,
        company_details=company_details,
        inline=True,
    )


@router.get('/{invoice_id}/pdf')
def get_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')

    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    if _is_uploaded_invoice(invoice):
        try:
            _create_notification_best_effort(
                db,
                user_id=current_user.id,
                title='Invoice File Downloaded',
                message=f'Invoice {invoice.invoice_number} file has been downloaded.',
                route='/invoices',
            )
            return _as_uploaded_invoice_file_response(invoice, inline=False)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            logger.warning(
                'Uploaded invoice download source file missing. Falling back to generated PDF. '
                'invoice_id=%s owner_id=%s path=%s',
                invoice.id,
                current_user.id,
                invoice.original_file_path,
            )

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Invoice PDF Downloaded',
        message=f'Invoice {invoice.invoice_number} PDF has been downloaded.',
        route='/invoices',
    )

    return _generated_invoice_pdf_file_response(
        invoice,
        db=db,
        owner_id=current_user.id,
        company_details=company_details,
        inline=False,
    )
