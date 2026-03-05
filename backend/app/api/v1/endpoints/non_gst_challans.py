from __future__ import annotations

import mimetypes
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.storage import get_storage_backend
from app.models.client import Client
from app.models.non_gst_challan import NonGSTChallan, NonGSTChallanItem
from app.models.personal_details import PersonalDetails
from app.models.user import User
from app.schemas.non_gst_challan import (
    LatestCreatedNonGSTChallanResponse,
    NonGSTChallanCreate,
    NonGSTChallanListResponse,
    NonGSTChallanResponse,
)
from app.services.pdf_delivery_challan_service import generate_delivery_challan_pdf
from app.services.pdf_invoice_service import (
    PDFInvoiceDataError,
    PDFInvoiceGenerationError,
    PDFInvoiceTemplateError,
    remove_generated_pdf,
    resolve_generated_pdf_path,
)
from app.services.notifications import create_notification
from app.utils.pdf_filename import build_bill_pdf_filename

router = APIRouter()


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
        challan_number=challan.sequence_number or 0,
        order_number=challan.challan_number,
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
        challan_number=payload.order_number,
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


def _build_delivery_challan_pdf_data(
    challan: NonGSTChallan,
    *,
    owner_id: str,
    client_name: str,
    company_details: PersonalDetails | None,
) -> dict[str, Any]:
    items = [
        {
            'description': item.description,
            'quantity': round(item.quantity, 2),
            'rate': round(item.rate, 2),
            'line_total': round(item.line_total, 2),
        }
        for item in challan.items
    ]
    if not items:
        items.append(
            {
                'description': challan.notes or 'Delivery Item',
                'quantity': 1.0,
                'rate': round(challan.subtotal, 2),
                'line_total': round(challan.subtotal, 2),
            }
        )

    return {
        'user_id': owner_id,
        'company_name': company_details.company_name if company_details and company_details.company_name else 'ScanMyBill',
        'company_address': company_details.address if company_details and company_details.address else 'N/A',
        'company_gstin': company_details.gstin_number if company_details and company_details.gstin_number else 'N/A',
        'challan_number': challan.sequence_number or 0,
        'order_number': challan.challan_number,
        'challan_date': challan.challan_date.isoformat(),
        'client_name': client_name,
        'subtotal': round(challan.subtotal, 2),
        'notes': challan.notes or '',
        'items': items,
    }


def _raise_delivery_challan_pdf_http_error(exc: Exception) -> None:
    if isinstance(exc, PDFInvoiceDataError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if isinstance(exc, PDFInvoiceTemplateError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    if isinstance(exc, PDFInvoiceGenerationError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to generate delivery challan PDF') from exc


def _generate_delivery_challan_pdf_path(
    challan: NonGSTChallan,
    *,
    owner_id: str,
    client_name: str,
    company_details: PersonalDetails | None,
) -> str:
    challan_pdf_data = _build_delivery_challan_pdf_data(
        challan,
        owner_id=owner_id,
        client_name=client_name,
        company_details=company_details,
    )
    try:
        return generate_delivery_challan_pdf(challan_pdf_data)
    except Exception as exc:
        _raise_delivery_challan_pdf_http_error(exc)


def _as_pdf_file_response(
    *,
    order_number: str,
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
        document_number=order_number,
        client_name=client_name,
    )
    background = BackgroundTask(remove_generated_pdf, stored_path) if cleanup_after_response else None
    return FileResponse(
        path=str(absolute_path),
        media_type='application/pdf',
        filename=filename,
        background=background,
    )


def _build_uploaded_challan_filename(challan: NonGSTChallan) -> str:
    suffix = Path(challan.original_file_path or '').suffix.lower() or '.bin'
    base_label = challan.challan_number or str(challan.sequence_number or 'uploaded-challan')
    base = re.sub(r'[^A-Za-z0-9._-]+', '-', base_label).strip('-_.')
    if not base:
        base = 'uploaded-challan'
    return f'{base[:80]}{suffix}'


def _as_uploaded_file_response(
    challan: NonGSTChallan,
    *,
    inline: bool,
) -> Response:
    stored_path = challan.original_file_path
    if not stored_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded challan file not found')

    storage = get_storage_backend()
    try:
        file_bytes = storage.read_bytes(stored_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Uploaded challan file not found') from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to read uploaded challan file',
        ) from exc

    media_type = mimetypes.guess_type(stored_path)[0] or 'application/octet-stream'
    disposition = 'inline' if inline else 'attachment'
    filename = _build_uploaded_challan_filename(challan)
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={'Content-Disposition': f'{disposition}; filename="{filename}"'},
    )


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
    latest_challan_number = db.scalar(
        select(func.max(NonGSTChallan.sequence_number)).where(NonGSTChallan.owner_id == current_user.id)
    )
    if not client_id:
        return LatestCreatedNonGSTChallanResponse(
            challan_number=int(latest_challan_number) if latest_challan_number else None,
            order_number=None,
        )

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
        return LatestCreatedNonGSTChallanResponse(
            challan_number=int(latest_challan_number) if latest_challan_number else None,
            order_number=None,
        )
    return LatestCreatedNonGSTChallanResponse(
        challan_number=int(latest_challan_number) if latest_challan_number else None,
        order_number=latest.challan_number,
    )


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
            NonGSTChallan.challan_number == payload.order_number,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Order Number already exists for this client.',
        )

    duplicate_sequence = db.scalar(
        select(NonGSTChallan.id).where(
            NonGSTChallan.owner_id == current_user.id,
            NonGSTChallan.sequence_number == payload.challan_number,
        )
    )
    if duplicate_sequence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Challan Number already exists. Please use a different number.',
        )

    challan = _build_challan_from_payload(payload, owner_id=current_user.id)
    challan.sequence_number = payload.challan_number
    db.add(challan)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        error_message = str(exc.orig).lower() if getattr(exc, 'orig', None) else str(exc).lower()
        if 'owner_id, client_id, challan_number' in error_message or 'uq_non_gst_challans_owner_client_number' in error_message:
            detail = 'Order Number already exists for this client.'
        elif 'owner_id, sequence_number' in error_message or 'uq_non_gst_challans_owner_sequence_number' in error_message:
            detail = 'Challan Number already exists. Please use a different number.'
        else:
            detail = 'Duplicate value detected while creating delivery challan.'
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc
    except Exception:
        db.rollback()
        raise

    refreshed = db.scalar(
        select(NonGSTChallan)
        .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
        .where(NonGSTChallan.id == challan.id, NonGSTChallan.owner_id == current_user.id)
    )
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to load challan')

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Delivery Challan Created',
        message=f'Delivery challan {refreshed.challan_number} has been created and saved.',
        route='/invoices/delivery-challan',
    )

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
    challan.sequence_number = payload.challan_number
    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    generated_path = _generate_delivery_challan_pdf_path(
        challan,
        owner_id=current_user.id,
        client_name=client.name,
        company_details=company_details,
    )
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Delivery Challan PDF Exported',
        message=f'Delivery challan {challan.challan_number} PDF has been exported.',
        route='/create/delivery-challan',
    )
    return _as_pdf_file_response(
        order_number=challan.challan_number,
        challan_date=challan.challan_date,
        client_name=client.name,
        stored_path=generated_path,
        cleanup_after_response=True,
    )


@router.delete(
    '/{challan_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_non_gst_challan(
    challan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    challan = db.scalar(
        select(NonGSTChallan).where(NonGSTChallan.id == challan_id, NonGSTChallan.owner_id == current_user.id)
    )
    if not challan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Challan not found')

    challan_number = challan.challan_number
    stored_path = challan.original_file_path

    db.delete(challan)
    db.commit()

    if stored_path:
        storage = get_storage_backend()
        try:
            storage.delete_file(stored_path)
        except Exception:
            pass

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Delivery Challan Deleted',
        message=f'Delivery challan {challan_number} has been deleted.',
        route='/invoices/delivery-challan',
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/{challan_id}/preview')
def preview_non_gst_challan_pdf(
    challan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    challan = db.scalar(
        select(NonGSTChallan)
        .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
        .where(NonGSTChallan.id == challan_id, NonGSTChallan.owner_id == current_user.id)
    )
    if not challan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Challan not found')
    if challan.original_file_path:
        return _as_uploaded_file_response(challan, inline=True)

    client_name = challan.client.name if challan.client else 'N/A'
    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    generated_path = _generate_delivery_challan_pdf_path(
        challan,
        owner_id=current_user.id,
        client_name=client_name,
        company_details=company_details,
    )

    return _as_pdf_file_response(
        order_number=challan.challan_number,
        challan_date=challan.challan_date,
        client_name=challan.client.name if challan.client else None,
        stored_path=generated_path,
        cleanup_after_response=True,
    )


@router.get('/{challan_id}/pdf')
def get_non_gst_challan_pdf(
    challan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    challan = db.scalar(
        select(NonGSTChallan)
        .options(selectinload(NonGSTChallan.client), selectinload(NonGSTChallan.items))
        .where(NonGSTChallan.id == challan_id, NonGSTChallan.owner_id == current_user.id)
    )
    if not challan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Challan not found')
    if challan.original_file_path:
        _create_notification_best_effort(
            db,
            user_id=current_user.id,
            title='Delivery Challan File Downloaded',
            message=f'Delivery challan {challan.challan_number} file has been downloaded.',
            route='/invoices/delivery-challan',
        )
        return _as_uploaded_file_response(challan, inline=False)

    client_name = challan.client.name if challan.client else 'N/A'
    company_details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    generated_path = _generate_delivery_challan_pdf_path(
        challan,
        owner_id=current_user.id,
        client_name=client_name,
        company_details=company_details,
    )

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Delivery Challan PDF Downloaded',
        message=f'Delivery challan {challan.challan_number} PDF has been downloaded.',
        route='/invoices/delivery-challan',
    )

    return _as_pdf_file_response(
        order_number=challan.challan_number,
        challan_date=challan.challan_date,
        client_name=challan.client.name if challan.client else None,
        stored_path=generated_path,
        cleanup_after_response=True,
    )

