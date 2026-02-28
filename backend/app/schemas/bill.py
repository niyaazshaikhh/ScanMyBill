from datetime import date, datetime

from pydantic import BaseModel

from app.models.invoice import InvoiceType


class BillUploadResponse(BaseModel):
    upload_id: str
    invoice_id: str | None
    file_name: str
    file_path: str
    invoice_date: date | None
    gst_number: str | None
    total_amount: float
    type: InvoiceType
    extracted_text_preview: str | None
    created_at: datetime


class OCRExtractionResult(BaseModel):
    bill_date: date | None
    gst_number: str | None
    total_amount: float
    inferred_type: InvoiceType