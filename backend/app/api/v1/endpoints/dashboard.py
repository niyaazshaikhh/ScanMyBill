from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.invoice import Invoice
from app.schemas.dashboard import DashboardSummary
from app.services.analytics import build_dashboard_summary
from app.utils.period import valid_period

router = APIRouter()


@router.get('/summary', response_model=DashboardSummary)
def summary(
    period: str = Query('monthly'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    return build_dashboard_summary(db=db, user_id=current_user.id, period=valid_period(period))


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
