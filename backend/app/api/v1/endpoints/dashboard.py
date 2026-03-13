import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.invoice import Invoice
from app.schemas.dashboard import DashboardAssistantRequest, DashboardAssistantResponse, DashboardSummary
from app.services.analytics import build_dashboard_summary
from app.services.dashboard_assistant import DashboardAssistantError, generate_dashboard_assistant_reply
from app.utils.period import valid_period

router = APIRouter()
logger = logging.getLogger(__name__)


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
