import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.invoice import Invoice
from app.models.non_gst_challan import NonGSTChallan
from app.models.recent_upload_state import RecentUploadState
from app.schemas.dashboard import (
    DashboardAssistantRequest,
    DashboardAssistantResponse,
    DashboardSummary,
    RecentUploadsClearResponse,
    RecentUploadRecord,
    RecentUploadsResponse,
)
from app.services.analytics import build_dashboard_summary
from app.services.dashboard_assistant import DashboardAssistantError, generate_dashboard_assistant_reply
from app.utils.period import valid_period

router = APIRouter()
logger = logging.getLogger(__name__)


def _as_sortable_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.get('/summary', response_model=DashboardSummary)
def summary(
    period: str = Query('monthly'),
    year: int | None = Query(None, ge=2000, le=2100),
    financial_year_start: int | None = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    return build_dashboard_summary(
        db=db,
        user_id=current_user.id,
        period=valid_period(period),
        year=year,
        financial_year_start=financial_year_start,
    )


@router.get('/admin-overview')
def admin_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> dict:
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_invoices = db.scalar(select(func.count(Invoice.id))) or 0
    return {
        'message': f'Admin access granted for {current_user.email}',
        'total_users': int(total_users),
        'total_invoices': int(total_invoices),
    }


@router.post('/assistant', response_model=DashboardAssistantResponse)
def dashboard_assistant_chat(
    payload: DashboardAssistantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardAssistantResponse:
    try:
        answer, model_name = generate_dashboard_assistant_reply(
            db=db,
            user_id=current_user.id,
            question=payload.message,
            user_role=current_user.role.value,
            period=payload.period,
            financial_year_start=payload.financial_year_start,
            history=[item.model_dump() for item in payload.history],
        )
        return DashboardAssistantResponse(answer=answer, model=model_name)
    except DashboardAssistantError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Dashboard AI assistant request failed for user_id=%s', current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='AI assistant is temporarily unavailable. Please try again.',
        ) from exc


@router.get('/recent-uploads', response_model=RecentUploadsResponse)
def recent_uploads(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecentUploadsResponse:
    recent_upload_state = db.scalar(
        select(RecentUploadState).where(RecentUploadState.owner_id == current_user.id)
    )
    cleared_at = recent_upload_state.cleared_at if recent_upload_state else None

    query_limit = max(limit * 4, 40)
    invoice_filters = [
        Invoice.owner_id == current_user.id,
        Invoice.original_file_path.is_not(None),
    ]
    challan_filters = [
        NonGSTChallan.owner_id == current_user.id,
        NonGSTChallan.original_file_path.is_not(None),
    ]
    if cleared_at is not None:
        invoice_filters.append(Invoice.created_at > cleared_at)
        challan_filters.append(NonGSTChallan.created_at > cleared_at)

    invoices = list(
        db.scalars(
            select(Invoice)
            .where(*invoice_filters)
            .order_by(Invoice.created_at.desc())
            .limit(query_limit)
        ).all()
    )
    challans = list(
        db.scalars(
            select(NonGSTChallan)
            .where(*challan_filters)
            .order_by(NonGSTChallan.created_at.desc())
            .limit(query_limit)
        ).all()
    )

    uploads: list[RecentUploadRecord] = []
    for invoice in invoices:
        uploads.append(
            RecentUploadRecord(
                upload_key=f'invoice:{invoice.id}',
                record_id=invoice.id,
                document_type='gst_invoice',
                document_number=invoice.invoice_number,
                target_route='/invoices',
                preview_path=f'/invoices/{invoice.id}/preview',
                total_amount=round(invoice.total_amount, 2),
                invoice_type=invoice.type,
                bill_date=invoice.invoice_date,
                created_at=invoice.created_at or datetime.now(timezone.utc),
            )
        )

    for challan in challans:
        document_number = challan.challan_number or str(challan.sequence_number or 'N/A')
        uploads.append(
            RecentUploadRecord(
                upload_key=f'delivery-challan:{challan.id}',
                record_id=challan.id,
                document_type='delivery_challan',
                document_number=document_number,
                target_route='/invoices/delivery-challan',
                preview_path=f'/delivery-challans/{challan.id}/preview',
                total_amount=round(challan.subtotal, 2),
                invoice_type=None,
                bill_date=challan.challan_date,
                created_at=challan.created_at or datetime.now(timezone.utc),
            )
        )

    uploads.sort(key=lambda item: _as_sortable_datetime(item.created_at), reverse=True)
    limited_uploads = uploads[:limit]
    return RecentUploadsResponse(uploads=limited_uploads, count=len(limited_uploads))


@router.delete('/recent-uploads', response_model=RecentUploadsClearResponse)
def clear_recent_uploads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecentUploadsClearResponse:
    recent_upload_state = db.scalar(
        select(RecentUploadState).where(RecentUploadState.owner_id == current_user.id)
    )
    previous_cleared_at = recent_upload_state.cleared_at if recent_upload_state else None

    invoice_filters = [
        Invoice.owner_id == current_user.id,
        Invoice.original_file_path.is_not(None),
    ]
    challan_filters = [
        NonGSTChallan.owner_id == current_user.id,
        NonGSTChallan.original_file_path.is_not(None),
    ]
    if previous_cleared_at is not None:
        invoice_filters.append(Invoice.created_at > previous_cleared_at)
        challan_filters.append(NonGSTChallan.created_at > previous_cleared_at)

    invoices_count = int(
        db.scalar(
            select(func.count(Invoice.id)).where(*invoice_filters)
        )
        or 0
    )
    challans_count = int(
        db.scalar(
            select(func.count(NonGSTChallan.id)).where(*challan_filters)
        )
        or 0
    )
    cleared = invoices_count + challans_count

    current_timestamp = datetime.now(timezone.utc)
    if recent_upload_state is None:
        recent_upload_state = RecentUploadState(
            owner_id=current_user.id,
            cleared_at=current_timestamp,
        )
        db.add(recent_upload_state)
    else:
        recent_upload_state.cleared_at = current_timestamp

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return RecentUploadsClearResponse(cleared=cleared)
