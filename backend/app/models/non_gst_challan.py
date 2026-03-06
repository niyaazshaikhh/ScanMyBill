from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class NonGSTChallan(Base):
    __tablename__ = 'non_gst_challans'
    __table_args__ = (
        UniqueConstraint('owner_id', 'client_id', 'challan_number', name='uq_non_gst_challans_owner_client_number'),
        UniqueConstraint(
            'owner_id',
            'financial_year_start',
            'sequence_number',
            name='uq_non_gst_challans_owner_financial_year_sequence_number',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    client_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('clients.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    challan_number: Mapped[str] = mapped_column(String(5), index=True)
    financial_year_start: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    challan_date: Mapped[Date] = mapped_column(Date, index=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship('User', back_populates='non_gst_challans')
    client = relationship('Client')
    items = relationship('NonGSTChallanItem', back_populates='challan', cascade='all,delete-orphan')


class NonGSTChallanItem(Base):
    __tablename__ = 'non_gst_challan_items'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    challan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('non_gst_challans.id', ondelete='CASCADE'),
        index=True,
    )
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    rate: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    challan = relationship('NonGSTChallan', back_populates='items')
