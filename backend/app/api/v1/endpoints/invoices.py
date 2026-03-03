from __future__ import annotations

from datetime import date
from io import BytesIO
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.storage import get_storage_backend
from app.core.database import get_db
from app.core.deps import get_current_user
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
from app.services.pdf_service import build_folder_export_pdf
from app.utils.period import matches_bucket, valid_period

router = APIRouter()


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


def _guess_media_type(stored_path: str) -> str:
    guessed, _ = mimetypes.guess_type(stored_path)
    return guessed or 'application/octet-stream'


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

    return {
        'user_id': owner_id,
        'company_name': company_details.company_name if company_details and company_details.company_name else 'ScanMyBill.in',
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LatestCreatedInvoiceResponse:
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

    invoice = _build_sales_invoice_from_payload(payload, owner_id=current_user.id)

    db.add(invoice)
    db.flush()

    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    invoice_pdf_data = _build_invoice_pdf_data(
        invoice,
        owner_id=current_user.id,
        company_details=company_details,
        client=client,
    )

    try:
        invoice.original_file_path = generate_invoice_pdf(invoice_pdf_data)
    except Exception as exc:
        db.rollback()
        _raise_pdf_generation_http_error(exc)

    try:
        db.commit()
    except Exception:
        if invoice.original_file_path:
            remove_generated_pdf(invoice.original_file_path)
        raise

    refreshed = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice.id, Invoice.owner_id == current_user.id)
    )
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to load invoice')

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

    filename = f'{invoice.invoice_number}.pdf'.replace(' ', '-')
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

    pdf_bytes = build_folder_export_pdf(invoices, folder_label=bucket, period=normalized_period)
    filename = f'{normalized_period}-{bucket}-export.pdf'.replace(' ', '-').lower()

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
        select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')
    if not invoice.original_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Preview file not found')

    upload = db.scalar(
        select(BillUpload).where(
            BillUpload.invoice_id == invoice.id,
            BillUpload.owner_id == current_user.id,
        )
    )

    storage = get_storage_backend()
    try:
        payload = storage.read_bytes(invoice.original_file_path)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Preview file not found') from exc

    media_type = upload.mime_type if upload and upload.mime_type else _guess_media_type(invoice.original_file_path)
    filename = upload.file_name if upload and upload.file_name else Path(invoice.original_file_path).name

    return Response(
        content=payload,
        media_type=media_type,
        headers={'Content-Disposition': f'inline; filename="{filename}"'},
    )


@router.get('/{invoice_id}/pdf')
def get_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')

    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))

    generated_pdf_path: str | None = None
    should_cleanup_after_response = False

    if (
        invoice.source == InvoiceSource.CREATED
        and invoice.original_file_path
        and invoice.original_file_path.lower().endswith('.pdf')
    ):
        try:
            existing_path = resolve_generated_pdf_path(invoice.original_file_path)
        except PDFInvoiceGenerationError:
            existing_path = None

        if existing_path and existing_path.exists():
            generated_pdf_path = invoice.original_file_path

    if not generated_pdf_path:
        invoice_pdf_data = _build_invoice_pdf_data(
            invoice,
            owner_id=current_user.id,
            company_details=company_details,
            client=invoice.client,
        )
        try:
            generated_pdf_path = generate_invoice_pdf(invoice_pdf_data)
        except Exception as exc:
            _raise_pdf_generation_http_error(exc)

        if invoice.source == InvoiceSource.CREATED:
            invoice.original_file_path = generated_pdf_path
            try:
                db.commit()
            except Exception:
                db.rollback()
                remove_generated_pdf(generated_pdf_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to persist generated invoice PDF path',
                )
        else:
            should_cleanup_after_response = True

    if not generated_pdf_path:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to resolve invoice PDF path')

    try:
        absolute_pdf_path = resolve_generated_pdf_path(generated_pdf_path)
    except PDFInvoiceGenerationError as exc:
        _raise_pdf_generation_http_error(exc)

    if not absolute_pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Generated invoice PDF missing')

    filename = f'{invoice.invoice_number}.pdf'.replace(' ', '-')
    background = BackgroundTask(remove_generated_pdf, generated_pdf_path) if should_cleanup_after_response else None
    return FileResponse(
        path=str(absolute_pdf_path),
        media_type='application/pdf',
        filename=filename,
        background=background,
    )
