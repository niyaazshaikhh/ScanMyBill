from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DESCRIPTION_PATTERN = re.compile(r'^[A-Za-z0-9 ]+$')
ORDER_NUMBER_PATTERN = re.compile(r'^\d{1,5}$')


def _decimal_places_within(value: float, max_places: int) -> bool:
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation:
        return False
    return abs(decimal_value.as_tuple().exponent) <= max_places


class NonGSTChallanItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=20)
    quantity: float = Field(gt=0, le=5_000_000)
    rate: float = Field(ge=0)

    @field_validator('description')
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Description is required.')
        if not DESCRIPTION_PATTERN.fullmatch(cleaned):
            raise ValueError('Description should be alphanumeric and special characters are not allowed.')
        return cleaned

    @field_validator('rate')
    @classmethod
    def validate_rate(cls, value: float) -> float:
        if not _decimal_places_within(value, 2):
            raise ValueError('Rate should have up to 2 decimal places.')
        return value


class NonGSTChallanCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    client_id: str
    order_number: str = Field(min_length=1, max_length=5)
    challan_number: int = Field(ge=1)
    challan_date: date
    notes: str | None = None
    items: list[NonGSTChallanItemCreate]

    @model_validator(mode='before')
    @classmethod
    def map_legacy_challan_number(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        legacy_value = normalized.get('challan_number')
        if 'order_number' not in normalized and isinstance(legacy_value, str):
            normalized['order_number'] = legacy_value
            normalized.pop('challan_number', None)
        return normalized

    @field_validator('client_id')
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Client is required.')
        return cleaned

    @field_validator('order_number')
    @classmethod
    def validate_order_number(cls, value: str) -> str:
        cleaned = value.strip()
        if not ORDER_NUMBER_PATTERN.fullmatch(cleaned):
            raise ValueError('Order Number should contain up to 5 digits.')
        return cleaned

    @field_validator('items')
    @classmethod
    def validate_items_not_empty(cls, value: list[NonGSTChallanItemCreate]) -> list[NonGSTChallanItemCreate]:
        if not value:
            raise ValueError('At least one item is required.')
        return value


class NonGSTChallanItemResponse(BaseModel):
    id: str
    description: str
    quantity: float
    rate: float
    line_total: float

    model_config = {'from_attributes': True}


class NonGSTChallanResponse(BaseModel):
    id: str
    client_id: str | None
    client_name: str | None
    challan_number: int
    order_number: str
    challan_date: date
    subtotal: float
    notes: str | None
    original_file_path: str | None
    created_at: datetime
    items: list[NonGSTChallanItemResponse]

    model_config = {'from_attributes': True}


class NonGSTChallanListResponse(BaseModel):
    challans: list[NonGSTChallanResponse]
    count: int


class LatestCreatedNonGSTChallanResponse(BaseModel):
    challan_number: int | None = None
    order_number: str | None = None
