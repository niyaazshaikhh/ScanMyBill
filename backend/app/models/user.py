from enum import Enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserRole(str, Enum):
    ADMIN = 'admin'
    USER = 'user'


class SubscriptionPlan(str, Enum):
    FREE = 'FREE'
    STANDARD = 'STANDARD'
    PRO = 'PRO'
    BUSINESS = 'BUSINESS'


class SubscriptionStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    CANCELLED = 'CANCELLED'
    EXPIRED = 'EXPIRED'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        SqlEnum(SubscriptionPlan, name='subscription_plan_enum'),
        default=SubscriptionPlan.FREE,
        nullable=False,
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(SubscriptionStatus, name='subscription_status_enum'),
        default=SubscriptionStatus.EXPIRED,
        nullable=False,
    )
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    subscription_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    reset_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    clients = relationship('Client', back_populates='owner', cascade='all,delete-orphan')
    invoices = relationship('Invoice', back_populates='owner', cascade='all,delete-orphan')
    non_gst_challans = relationship('NonGSTChallan', back_populates='owner', cascade='all,delete-orphan')
    bill_uploads = relationship('BillUpload', back_populates='owner', cascade='all,delete-orphan')
    payments = relationship('PaymentEvent', back_populates='owner', cascade='all,delete-orphan')
    hsn_sac_masters = relationship('HSNSACMaster', back_populates='owner', cascade='all,delete-orphan')
    password_reset_tokens = relationship('PasswordResetToken', cascade='all,delete-orphan')
    personal_details = relationship(
        'PersonalDetails',
        back_populates='owner',
        uselist=False,
        cascade='all,delete-orphan',
    )
    auth_sessions = relationship('UserSession', back_populates='owner', cascade='all,delete-orphan')
