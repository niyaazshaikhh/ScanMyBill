from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.validation_rules import (
    COMPANY_NAME_PATTERN,
    STATE_CODE_BY_NAME,
    STATE_CODE_PATTERN,
    STATE_NAME_BY_LOWERCASE,
    strip_required,
    validate_optional_gstin,
)


class ClientWriteBase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=30)
    address: str | None = Field(default=None, max_length=115)
    state_name: str | None = Field(default=None, max_length=64)
    state_code: str | None = Field(default=None, max_length=2)
    gst_number: str | None = Field(default=None, max_length=15)
    email: EmailStr | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = strip_required(value, 'Name')
        if len(cleaned) > 30:
            raise ValueError('Name should be up to 30 characters only.')
        if not COMPANY_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError('Name should be alphanumeric and special characters are not allowed.')
        return cleaned

    @field_validator('address')
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > 115:
            raise ValueError('Address should be up to 115 characters only.')
        return cleaned

    @field_validator('state_name')
    @classmethod
    def validate_state_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        state_name = STATE_NAME_BY_LOWERCASE.get(cleaned.lower())
        if state_name is None:
            raise ValueError('Please select a valid Indian state or union territory.')
        return state_name

    @field_validator('state_code')
    @classmethod
    def validate_state_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not STATE_CODE_PATTERN.fullmatch(cleaned):
            raise ValueError('State Code should be exactly 2 digits.')
        return cleaned

    @field_validator('gst_number')
    @classmethod
    def validate_gst_number(cls, value: str | None) -> str | None:
        return validate_optional_gstin(value)

    @model_validator(mode='after')
    def validate_state_name_and_code(self) -> 'ClientWriteBase':
        if not self.state_name and not self.state_code:
            return self
        if not self.state_name or not self.state_code:
            raise ValueError('State Name and State Code should both be provided.')

        expected_code = STATE_CODE_BY_NAME.get(self.state_name.lower())
        if expected_code and self.state_code != expected_code:
            raise ValueError('State Code does not match the selected State Name.')
        return self


class ClientCreate(ClientWriteBase):
    pass


class ClientUpdate(ClientWriteBase):
    pass


class ClientResponse(BaseModel):
    id: str
    name: str
    address: str | None = None
    state_name: str | None = None
    state_code: str | None = None
    email: EmailStr | None = None
    gst_number: str | None = None
    created_at: datetime
    total_transactions: int = 0
    total_revenue: float = 0.0

    model_config = {'from_attributes': True}


class ClientAnalytics(BaseModel):
    client_id: str
    client_name: str
    transactions: int
    revenue: float


class ClientsOverview(BaseModel):
    total_clients: int
    total_transactions: int
    total_revenue: float
    top_clients: list[ClientAnalytics]
