from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.invoice import InvoiceSource, InvoiceType


class InvoiceItemBase(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    gst_percent: float = Field(ge=0, le=100)


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemResponse(InvoiceItemBase):
    id: str
    line_total: float

    model_config = {'from_attributes': True}


class InvoiceCreate(BaseModel):
    client_id: str | None = None
    invoice_number: str | None = Field(default=None, max_length=60)
    invoice_date: date
    gst_number: str | None = Field(default=None, max_length=20)
    type: InvoiceType = InvoiceType.SALES
    notes: str | None = None
    items: list[InvoiceItemCreate]


class InvoiceResponse(BaseModel):
    id: str
    client_id: str | None
    client_name: str | None = None
    invoice_number: str
    invoice_date: date
    gst_number: str | None
    type: InvoiceType
    subtotal: float
    gst_amount: float
    total_amount: float
    source: InvoiceSource
    notes: str | None
    original_file_path: str | None
    created_at: datetime
    items: list[InvoiceItemResponse]

    model_config = {'from_attributes': True}


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    count: int