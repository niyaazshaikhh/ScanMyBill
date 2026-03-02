from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from pydantic import BaseModel, Field, field_validator

from app.models.invoice import InvoiceSource, InvoiceType
from app.schemas.validation_rules import STATE_CODE_BY_NAME, STATE_CODE_PATTERN, STATE_NAME_BY_LOWERCASE

INVOICE_NUMBER_PATTERN = re.compile(r'^\d{4}-\d{2}/\d{3}$')
DESCRIPTION_PATTERN = re.compile(r'^[A-Za-z0-9 ]+$')
HSN_SAC_PATTERN = re.compile(r'^\d{1,8}$')


def _decimal_places_within(value: float, max_places: int) -> bool:
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation:
        return False
    return abs(decimal_value.as_tuple().exponent) <= max_places


class InvoiceItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=20)
    hsn_sac: str = Field(min_length=1, max_length=8)
    quantity: float = Field(gt=0, le=5_000_000)
    rate: float = Field(ge=0)
    tax_rate: float = Field(ge=0, le=99.99)

    @field_validator('description')
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Description is required.')
        if not DESCRIPTION_PATTERN.fullmatch(cleaned):
            raise ValueError('Description should be alphanumeric and special characters are not allowed.')
        return cleaned

    @field_validator('hsn_sac')
    @classmethod
    def validate_hsn_sac(cls, value: str) -> str:
        cleaned = value.strip()
        if not HSN_SAC_PATTERN.fullmatch(cleaned):
            raise ValueError('HSN/SAC should contain only digits and be up to 8 digits.')
        return cleaned

    @field_validator('rate')
    @classmethod
    def validate_rate(cls, value: float) -> float:
        if not _decimal_places_within(value, 2):
            raise ValueError('Rate should have up to 2 decimal places.')
        return value

    @field_validator('tax_rate')
    @classmethod
    def validate_tax_rate(cls, value: float) -> float:
        if not _decimal_places_within(value, 2):
            raise ValueError('Tax Rate should have up to 2 decimal places.')
        return value


class InvoiceItemResponse(BaseModel):
    id: str
    description: str
    hsn_sac: str | None = None
    quantity: float
    rate: float
    tax_rate: float
    amount_before_tax: float
    cgst: float
    sgst_utgst: float
    total_tax_amount: float
    grand_total: float

    model_config = {'from_attributes': True}


class InvoiceCreate(BaseModel):
    client_id: str
    invoice_number: str = Field(min_length=11, max_length=11)
    invoice_date: date
    place_of_supply: str = Field(min_length=1, max_length=64)
    place_of_supply_code: str = Field(min_length=2, max_length=2)
    notes: str | None = None
    items: list[InvoiceItemCreate]

    @field_validator('client_id')
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Client is required.')
        return cleaned

    @field_validator('invoice_number')
    @classmethod
    def validate_invoice_number(cls, value: str) -> str:
        cleaned = value.strip()
        if not INVOICE_NUMBER_PATTERN.fullmatch(cleaned):
            raise ValueError('Invoice Number should be in format YYYY-YY/NNN.')

        start_year = int(cleaned[:4])
        next_year_short = int(cleaned[5:7])
        expected_next_year_short = (start_year + 1) % 100
        if next_year_short != expected_next_year_short:
            raise ValueError('Invoice Number year segment is invalid. Expected YYYY-(YYYY+1)/NNN format.')
        return cleaned

    @field_validator('place_of_supply')
    @classmethod
    def validate_place_of_supply(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Place of Supply is required.')
        normalized = STATE_NAME_BY_LOWERCASE.get(cleaned.lower())
        if normalized is None:
            raise ValueError('Please select a valid Indian state or union territory for Place of Supply.')
        return normalized

    @field_validator('place_of_supply_code')
    @classmethod
    def validate_place_of_supply_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not STATE_CODE_PATTERN.fullmatch(cleaned):
            raise ValueError('Place of Supply Code should be exactly 2 digits.')
        return cleaned

    @field_validator('items')
    @classmethod
    def validate_items_not_empty(cls, value: list[InvoiceItemCreate]) -> list[InvoiceItemCreate]:
        if not value:
            raise ValueError('At least one item is required.')
        return value

    @field_validator('place_of_supply_code')
    @classmethod
    def validate_place_of_supply_code_match(cls, value: str, info) -> str:
        place_of_supply = info.data.get('place_of_supply')
        if not place_of_supply:
            return value
        expected_code = STATE_CODE_BY_NAME.get(place_of_supply.lower())
        if expected_code and value != expected_code:
            raise ValueError('Place of Supply Code does not match the selected Place of Supply.')
        return value


class InvoiceResponse(BaseModel):
    id: str
    client_id: str | None
    client_name: str | None = None
    invoice_number: str
    invoice_date: date
    place_of_supply: str | None = None
    place_of_supply_code: str | None = None
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
