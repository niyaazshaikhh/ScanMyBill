from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.invoice import InvoiceType


class GSTInvoiceExtractedItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    description: str
    hsn_sac: str
    quantity: float
    rate: float
    tax_rate: float


class DeliveryChallanExtractedItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    description: str
    quantity: float
    rate: float


class GSTInvoiceExtractedPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    invoice_number: str | None
    invoice_date: date | None
    place_of_supply: str | None
    place_of_supply_code: str | None
    gst_number: str | None
    subtotal: float
    gst_amount: float
    total_amount: float
    notes: str | None
    items: list[GSTInvoiceExtractedItem] = Field(default_factory=list)


class DeliveryChallanExtractedPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    challan_number: int | None
    order_number: str | None
    challan_date: date | None
    from_party: str | None
    to_party: str | None
    subtotal: float
    notes: str | None
    items: list[DeliveryChallanExtractedItem] = Field(default_factory=list)


class BillStructuredData(BaseModel):
    model_config = ConfigDict(extra='forbid')

    document_type: Literal['gst_invoice', 'delivery_challan']
    bill_type: InvoiceType
    gst_invoice: GSTInvoiceExtractedPayload | None
    delivery_challan: DeliveryChallanExtractedPayload | None
    warnings: list[str] = Field(default_factory=list)


class BillUploadResponse(BaseModel):
    upload_id: str
    invoice_id: str | None
    delivery_challan_id: str | None = None
    document_type: Literal['gst_invoice', 'delivery_challan']
    target_route: Literal['/invoices', '/invoices/delivery-challan']
    file_name: str
    file_path: str
    invoice_date: date | None
    gst_number: str | None
    total_amount: float
    type: InvoiceType
    structured_data: BillStructuredData
    extracted_text_preview: str | None
    created_at: datetime


class OCRExtractionResult(BaseModel):
    document_type: Literal['gst_invoice', 'delivery_challan']
    bill_date: date | None
    gst_number: str | None
    total_amount: float
    inferred_type: InvoiceType
