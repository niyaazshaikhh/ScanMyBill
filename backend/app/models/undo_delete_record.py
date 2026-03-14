from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UndoDeleteRecordType(str, Enum):
    INVOICE = 'invoice'
    CLIENT = 'client'


class UndoDeleteRecord(Base):
    __tablename__ = 'undo_delete_records'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    record_type: Mapped[UndoDeleteRecordType] = mapped_column(
        SqlEnum(UndoDeleteRecordType, name='undo_delete_record_type_enum'),
        nullable=False,
        index=True,
    )
    record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

