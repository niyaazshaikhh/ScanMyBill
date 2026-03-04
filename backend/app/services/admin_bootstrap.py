from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole


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

    user = db.scalar(select(User).where(User.email == admin_email))
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

    updated = False
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
