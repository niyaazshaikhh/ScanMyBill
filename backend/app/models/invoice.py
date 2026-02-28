from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as SqlEnum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class InvoiceType(str, Enum):
    SALES = 'sales'
    PURCHASE = 'purchase'


class InvoiceSource(str, Enum):
    UPLOADED = 'uploaded'
    CREATED = 'created'


class Invoice(Base):
    __tablename__ = 'invoices'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    client_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('clients.id', ondelete='SET NULL'), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(60), index=True)
    invoice_date: Mapped[Date] = mapped_column(Date, index=True)
    gst_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    type: Mapped[InvoiceType] = mapped_column(SqlEnum(InvoiceType), default=InvoiceType.PURCHASE, index=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    gst_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[InvoiceSource] = mapped_column(SqlEnum(InvoiceSource), default=InvoiceSource.CREATED)
    original_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship('User', back_populates='invoices')
    client = relationship('Client', back_populates='invoices')
    items = relationship('InvoiceItem', back_populates='invoice', cascade='all,delete-orphan')
    bill_upload = relationship('BillUpload', back_populates='invoice', uselist=False)


class InvoiceItem(Base):
    __tablename__ = 'invoice_items'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey('invoices.id', ondelete='CASCADE'), index=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    gst_percent: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    invoice = relationship('Invoice', back_populates='items')