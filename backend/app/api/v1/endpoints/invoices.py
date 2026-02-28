from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.invoice import Invoice, InvoiceItem, InvoiceSource, InvoiceType
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceListResponse, InvoiceResponse
from app.services.pdf_service import build_folder_export_pdf, build_invoice_pdf
from app.utils.period import matches_bucket, valid_period

router = APIRouter()


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        client_id=invoice.client_id,
        client_name=invoice.client.name if invoice.client else None,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        gst_number=invoice.gst_number,
        type=invoice.type,
        subtotal=round(invoice.subtotal, 2),
        gst_amount=round(invoice.gst_amount, 2),
        total_amount=round(invoice.total_amount, 2),
        source=invoice.source,
        notes=invoice.notes,
        original_file_path=invoice.original_file_path,
        created_at=invoice.created_at,
        items=[
            {
                'id': item.id,
                'description': item.description,
                'quantity': item.quantity,
                'price': item.price,
                'gst_percent': item.gst_percent,
                'line_total': round(item.line_total, 2),
            }
            for item in invoice.items
        ],
    )


def _parse_invoice_type(invoice_type: str | None) -> InvoiceType | None:
    if not invoice_type:
        return None
    value = invoice_type.lower()
    if value not in {InvoiceType.SALES.value, InvoiceType.PURCHASE.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid invoice type')
    return InvoiceType(value)


@router.get('', response_model=InvoiceListResponse)
def list_invoices(
    period: str = Query('monthly'),
    invoice_type: str | None = Query(None),
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

    invoices = list(db.scalars(stmt).all())
    if bucket:
        invoices = [inv for inv in invoices if matches_bucket(inv.invoice_date, normalized_period, bucket)]

    serialized = [_invoice_to_response(invoice) for invoice in invoices]
    return InvoiceListResponse(invoices=serialized, count=len(serialized))


@router.post('/create', response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceResponse:
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one item is required')

    subtotal = 0.0
    gst_amount = 0.0

    invoice = Invoice(
        owner_id=current_user.id,
        client_id=payload.client_id,
        invoice_number=payload.invoice_number
        or f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        invoice_date=payload.invoice_date,
        gst_number=payload.gst_number,
        type=payload.type,
        source=InvoiceSource.CREATED,
        notes=payload.notes,
    )

    for item_data in payload.items:
        base = item_data.quantity * item_data.price
        item_gst = base * (item_data.gst_percent / 100.0)
        line_total = base + item_gst

        subtotal += base
        gst_amount += item_gst

        item = InvoiceItem(
            description=item_data.description,
            quantity=item_data.quantity,
            price=item_data.price,
            gst_percent=item_data.gst_percent,
            line_total=line_total,
        )
        invoice.items.append(item)

    invoice.subtotal = round(subtotal, 2)
    invoice.gst_amount = round(gst_amount, 2)
    invoice.total_amount = round(subtotal + gst_amount, 2)

    db.add(invoice)
    db.commit()
    refreshed = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice.id, Invoice.owner_id == current_user.id)
    )
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to load invoice')

    return _invoice_to_response(refreshed)


@router.get('/export-folder')
def export_folder(
    period: str = Query('monthly'),
    bucket: str = Query(..., min_length=1),
    invoice_type: str | None = Query(None),
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


@router.get('/{invoice_id}/pdf')
def get_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found')

    pdf_bytes = build_invoice_pdf(invoice)
    filename = f'{invoice.invoice_number}.pdf'.replace(' ', '-')

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
