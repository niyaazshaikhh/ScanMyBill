from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Client(Base):
    __tablename__ = 'clients'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(30), index=True)
    address: Mapped[str | None] = mapped_column(String(115), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(25), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(15), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship('User', back_populates='clients')
    invoices = relationship('Invoice', back_populates='client')
