from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PersonalDetails(Base):
    __tablename__ = 'personal_details'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(20))
    gstin_number: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(115))
    state_name: Mapped[str | None] = mapped_column(String(64))
    state_code: Mapped[str | None] = mapped_column(String(2))
    gst_filing_period: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(15))
    account_number: Mapped[str | None] = mapped_column(String(34))
    branch: Mapped[str | None] = mapped_column(String(15))
    ifsc_code: Mapped[str | None] = mapped_column(String(11))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner = relationship('User', back_populates='personal_details')
