from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.client import Client
from app.models.non_gst_challan import NonGSTChallan, NonGSTChallanItem
from app.models.user import User
from app.schemas.non_gst_challan import (
    LatestCreatedNonGSTChallanResponse,
    NonGSTChallanCreate,
    NonGSTChallanListResponse,
    NonGSTChallanResponse,
)
from app.services.pdf_invoice_service import (
    PDFInvoiceGenerationError,
    remove_generated_pdf,
    resolve_generated_pdf_path,
)
from app.utils.pdf_filename import build_bill_pdf_filename

router = APIRouter()

APP_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = APP_ROOT.parent


def _is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _uploads_root() -> Path:
    configured = Path(settings.uploads_dir)
    candidate = configured if configured.is_absolute() else BACKEND_ROOT / configured
    resolved = candidate.resolve()
    if not _is_within(BACKEND_ROOT, resolved):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='UPLOADS_DIR must be inside backend directory.',
        )
    return resolved


def _sanitize_owner_id(owner_id: str) -> str:
    return ''.join(char for char in owner_id if char.isalnum() or char in {'-', '_'})


def _challan_to_response(challan: NonGSTChallan) -> NonGSTChallanResponse:
    serialized_items = [
        {
            'id': item.id,
            'description': item.description,
            'quantity': round(item.quantity, 2),
            'rate': round(item.rate, 2),
            'line_total': round(item.line_total, 2),
        }
        for item in challan.items
    ]
    return NonGSTChallanResponse(
        id=challan.id,
        client_id=challan.client_id,
        client_name=challan.client.name if challan.client else None,
        challan_number=challan.challan_number,
        challan_date=challan.challan_date,
        subtotal=round(challan.subtotal, 2),
        notes=challan.notes,
        original_file_path=challan.original_file_path,
        created_at=challan.created_at,
        items=serialized_items,
    )


def _build_challan_from_payload(payload: NonGSTChallanCreate, *, owner_id: str) -> NonGSTChallan:
    challan = NonGSTChallan(
        owner_id=owner_id,
        client_id=payload.client_id,
        challan_number=payload.challan_number,
        challan_date=payload.challan_date,
        notes=payload.notes,
    )
    subtotal = 0.0
    for item_data in payload.items:
        line_total = item_data.quantity * item_data.rate
        subtotal += line_total
        challan.items.append(
            NonGSTChallanItem(
                description=item_data.description,
                quantity=item_data.quantity,
                rate=item_data.rate,
                line_total=line_total,
            )
        )
    challan.subtotal = round(subtotal, 2)
    return challan


def _build_delivery_challan_pdf_bytes(challan: NonGSTChallan, *, client_name: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('ScanMyBill.in - Delivery Challan', styles['Title']))
    elements.append(Spacer(1, 10))

    details_data = [
        ['Challan #', challan.challan_number],
        ['Date', challan.challan_date.strftime('%d/%b/%Y')],
        ['Client', client_name],
        ['Subtotal', f'{challan.subtotal:.2f}'],
    ]
    details_table = Table(details_data, hAlign='LEFT', colWidths=[120, 340])
    details_table.setStyle(
        TableStyle(
            [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    elements.append(details_table)
    elements.append(Spacer(1, 16))

    item_rows = [['Description', 'Qty', 'Rate', 'Amount']]
    for item in challan.items:
        item_rows.append(
            [
                item.description,
                f'{item.quantity:.2f}',
                f'{item.rate:.2f}',
                f'{item.line_total:.2f}',
            ]
        )

    items_table = Table(item_rows, hAlign='LEFT', colWidths=[280, 70, 90, 90])
    items_table.setStyle(
        TableStyle(
            [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ]
        )
    )
    elements.append(items_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f'<b>Total:</b> {challan.subtotal:.2f}', styles['Normal']))
    if challan.notes:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f'<b>Note:</b> {challan.notes}', styles['Normal']))

    doc.build(elements)
    return buffer.getvalue()


def _persist_pdf_bytes(*, owner_id: str, pdf_bytes: bytes) -> str:
    uploads_root = _uploads_root()
    safe_owner_id = _sanitize_owner_id(owner_id)
    if not safe_owner_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Unable to resolve storage directory for challan PDF.',
        )

    relative_dir = Path('bills') / safe_owner_id
    target_dir = (uploads_root / relative_dir).resolve()
    if not _is_within(uploads_root, target_dir):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Resolved storage directory is invalid.',
        )
    target_dir.mkdir(parents=True, exist_ok=True)

    relative_path = (relative_dir / f'{uuid4().hex}.pdf').as_posix()
    try:
        absolute_path = resolve_generated_pdf_path(relative_path)
    except PDFInvoiceGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to resolve generated challan PDF path.',
        ) from exc
    absolute_path.write_bytes(pdf_bytes)
    return relative_path


def _as_pdf_file_response(
    *,
    challan_number: str,
    challan_date,
    client_name: str | None,
    stored_path: str,
    cleanup_after_response: bool,
) -> FileResponse:
    try:
        absolute_path = resolve_generated_pdf_path(stored_path)
    except PDFInvoiceGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to resolve generated challan PDF path.',
        ) from exc

    if not absolute_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Generated challan PDF missing.',
        )

    filename = build_bill_pdf_filename(
        bill_date=challan_date,
        document_number=challan_number,
        client_name=client_name,
    )
    background = BackgroundTask(remove_generated_pdf, stored_path) if cleanup_after_response else None
    return FileResponse(
        path=str(absolute_path),
        media_type='application/pdf',
        filename=filename,
        background=background,
    )


@router.get('', response_model=NonGSTChallanListResponse)
def list_non_gst_challans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NonGSTChallanListResponse:
    challans = list(
        db.scalars(
            select(NonGSTChallan)
            .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
            .where(NonGSTChallan.owner_id == current_user.id)
            .order_by(NonGSTChallan.challan_date.desc(), NonGSTChallan.created_at.desc())
        ).all()
    )
    serialized = [_challan_to_response(challan) for challan in challans]
    return NonGSTChallanListResponse(challans=serialized, count=len(serialized))


@router.get('/latest-created', response_model=LatestCreatedNonGSTChallanResponse)
def latest_created_non_gst_challan(
    client_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LatestCreatedNonGSTChallanResponse:
    if not client_id:
        return LatestCreatedNonGSTChallanResponse(challan_number=None)

    client = db.scalar(
        select(Client).where(Client.id == client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected client is invalid')

    latest = db.scalar(
        select(NonGSTChallan)
        .where(
            NonGSTChallan.owner_id == current_user.id,
            NonGSTChallan.client_id == client_id,
        )
        .order_by(NonGSTChallan.created_at.desc(), NonGSTChallan.challan_date.desc())
        .limit(1)
    )
    if not latest:
        return LatestCreatedNonGSTChallanResponse(challan_number=None)
    return LatestCreatedNonGSTChallanResponse(challan_number=latest.challan_number)


@router.post('/create', response_model=NonGSTChallanResponse, status_code=status.HTTP_201_CREATED)
def create_non_gst_challan(
    payload: NonGSTChallanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NonGSTChallanResponse:
    client = db.scalar(
        select(Client).where(Client.id == payload.client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected client is invalid')

    duplicate = db.scalar(
        select(NonGSTChallan).where(
            NonGSTChallan.owner_id == current_user.id,
            NonGSTChallan.client_id == payload.client_id,
            NonGSTChallan.challan_number == payload.challan_number,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Challan Number already exists for this client.',
        )

    challan = _build_challan_from_payload(payload, owner_id=current_user.id)
    db.add(challan)
    db.flush()

    pdf_bytes = _build_delivery_challan_pdf_bytes(challan, client_name=client.name)
    challan.original_file_path = _persist_pdf_bytes(owner_id=current_user.id, pdf_bytes=pdf_bytes)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if challan.original_file_path:
            remove_generated_pdf(challan.original_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Challan Number already exists for this client.',
        ) from exc
    except Exception:
        db.rollback()
        if challan.original_file_path:
            remove_generated_pdf(challan.original_file_path)
        raise

    refreshed = db.scalar(
        select(NonGSTChallan)
        .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
        .where(NonGSTChallan.id == challan.id, NonGSTChallan.owner_id == current_user.id)
    )
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to load challan')

    return _challan_to_response(refreshed)


@router.post('/create/pdf')
def create_non_gst_challan_pdf(
    payload: NonGSTChallanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    client = db.scalar(
        select(Client).where(Client.id == payload.client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected client is invalid')

    challan = _build_challan_from_payload(payload, owner_id=current_user.id)
    pdf_bytes = _build_delivery_challan_pdf_bytes(challan, client_name=client.name)
    stored_path = _persist_pdf_bytes(owner_id=current_user.id, pdf_bytes=pdf_bytes)
    return _as_pdf_file_response(
        challan_number=challan.challan_number,
        challan_date=challan.challan_date,
        client_name=client.name,
        stored_path=stored_path,
        cleanup_after_response=True,
    )


@router.get('/{challan_id}/pdf')
def get_non_gst_challan_pdf(
    challan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    challan = db.scalar(
        select(NonGSTChallan)
        .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
        .where(NonGSTChallan.id == challan_id, NonGSTChallan.owner_id == current_user.id)
    )
    if not challan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Challan not found')

    generated_path: str | None = None
    if challan.original_file_path:
        try:
            existing_path = resolve_generated_pdf_path(challan.original_file_path)
        except PDFInvoiceGenerationError:
            existing_path = None
        if existing_path and existing_path.exists():
            generated_path = challan.original_file_path

    if not generated_path:
        client_name = challan.client.name if challan.client else 'N/A'
        pdf_bytes = _build_delivery_challan_pdf_bytes(challan, client_name=client_name)
        generated_path = _persist_pdf_bytes(owner_id=current_user.id, pdf_bytes=pdf_bytes)
        challan.original_file_path = generated_path
        try:
            db.commit()
        except Exception:
            db.rollback()
            remove_generated_pdf(generated_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to persist generated challan PDF path.',
            )

    return _as_pdf_file_response(
        challan_number=challan.challan_number,
        challan_date=challan.challan_date,
        client_name=challan.client.name if challan.client else None,
        stored_path=generated_path,
        cleanup_after_response=False,
    )
