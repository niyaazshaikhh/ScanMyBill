from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

HSN_SAC_CODE_PATTERN = re.compile(r'^\d{4,15}$')


def _decimal_places_within(value: float, max_places: int) -> bool:
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation:
        return False
    return abs(decimal_value.as_tuple().exponent) <= max_places


class HSNSACMasterCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=15)
    hsn_sac_code: str = Field(min_length=4, max_length=15)
    tax_rate: float = Field(ge=0, le=99.99)

    @field_validator('description')
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Description is required.')
        return cleaned

    @field_validator('hsn_sac_code')
    @classmethod
    def validate_hsn_sac_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not HSN_SAC_CODE_PATTERN.fullmatch(cleaned):
            raise ValueError('HSN/SAC code should contain 4 to 15 digits.')
        return cleaned

    @field_validator('tax_rate')
    @classmethod
    def validate_tax_rate(cls, value: float) -> float:
        if not _decimal_places_within(value, 2):
            raise ValueError('Tax Rate should have up to 2 decimal places.')
        return value


class HSNSACMasterResponse(BaseModel):
    id: str
    description: str
    hsn_sac_code: str
    tax_rate: float
    created_at: datetime

    model_config = {'from_attributes': True}
