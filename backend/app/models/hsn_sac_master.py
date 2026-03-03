from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class HSNSACMaster(Base):
    __tablename__ = 'hsn_sac_masters'
    __table_args__ = (
        UniqueConstraint('owner_id', 'hsn_sac_code', name='uq_hsn_sac_masters_owner_code'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    description: Mapped[str] = mapped_column(String(15))
    hsn_sac_code: Mapped[str] = mapped_column(String(8), index=True)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship('User', back_populates='hsn_sac_masters')
