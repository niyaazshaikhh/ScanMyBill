import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.core.validators import ensure_password_strength
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole

LEGACY_DEFAULT_ADMIN_EMAILS = {
    'niyaz7@scanmybill.xyz',
    'admin_niyaz7@scanmybill.xyz',
}
logger = logging.getLogger(__name__)


def default_admin_identity() -> tuple[str, str]:
    admin_user_id = settings.default_admin_user_id.strip()
    admin_email = settings.default_admin_email.strip().lower()
    return admin_user_id, admin_email


def ensure_default_admin_user(db: Session) -> User | None:
    if not settings.seed_default_admin:
        return None

    _, admin_email = default_admin_identity()
    default_password = settings.default_admin_password
    default_full_name = settings.default_admin_full_name.strip() or 'Admin User'
    try:
        ensure_password_strength(default_password)
    except ValueError:
        logger.warning('Skipping default admin seeding because DEFAULT_ADMIN_PASSWORD is not strong enough.')
        return None

    user = db.scalar(select(User).where(func.lower(User.email) == admin_email))
    updated = False

    if user is None and admin_email not in LEGACY_DEFAULT_ADMIN_EMAILS:
        legacy_user = db.scalar(
            select(User)
            .where(
                func.lower(User.email).in_(LEGACY_DEFAULT_ADMIN_EMAILS),
                User.role == UserRole.ADMIN,
            )
            .order_by(User.created_at.asc())
        )
        if legacy_user is not None:
            legacy_user.email = admin_email
            user = legacy_user
            updated = True

    if user is None:
        user = User(
            email=admin_email,
            full_name=default_full_name,
            hashed_password=get_password_hash(default_password),
            role=UserRole.ADMIN,
            is_active=True,
            subscription_plan=SubscriptionPlan.BUSINESS,
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN
        updated = True
    if not user.is_active:
        user.is_active = True
        updated = True
    if not user.hashed_password or not verify_password(default_password, user.hashed_password):
        user.hashed_password = get_password_hash(default_password)
        updated = True
    if user.subscription_plan != SubscriptionPlan.BUSINESS:
        user.subscription_plan = SubscriptionPlan.BUSINESS
        updated = True
    if user.subscription_status != SubscriptionStatus.ACTIVE:
        user.subscription_status = SubscriptionStatus.ACTIVE
        updated = True

    if updated:
        db.commit()
        db.refresh(user)

    return user
