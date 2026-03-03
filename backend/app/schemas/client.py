from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.validation_rules import (
    COMPANY_NAME_PATTERN,
    STATE_CODE_BY_NAME,
    STATE_CODE_PATTERN,
    STATE_NAME_BY_LOWERCASE,
    strip_required,
    validate_required_gstin,
)


class ClientWriteBase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=15)
    address: str = Field(min_length=1, max_length=115)
    state_name: str = Field(min_length=1, max_length=64)
    state_code: str = Field(min_length=2, max_length=2)
    gst_number: str = Field(min_length=15, max_length=15)
    email: EmailStr | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = strip_required(value, 'Name')
        if not COMPANY_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError('Name should be alphanumeric and special characters are not allowed.')
        return cleaned

    @field_validator('address')
    @classmethod
    def validate_address(cls, value: str) -> str:
        cleaned = strip_required(value, 'Address')
        if len(cleaned) > 115:
            raise ValueError('Address should be up to 115 characters only.')
        return cleaned

    @field_validator('state_name')
    @classmethod
    def validate_state_name(cls, value: str) -> str:
        cleaned = strip_required(value, 'State Name')
        state_name = STATE_NAME_BY_LOWERCASE.get(cleaned.lower())
        if state_name is None:
            raise ValueError('Please select a valid Indian state or union territory.')
        return state_name

    @field_validator('state_code')
    @classmethod
    def validate_state_code(cls, value: str) -> str:
        cleaned = strip_required(value, 'State Code')
        if not STATE_CODE_PATTERN.fullmatch(cleaned):
            raise ValueError('State Code should be exactly 2 digits.')
        return cleaned

    @field_validator('gst_number')
    @classmethod
    def validate_gst_number(cls, value: str) -> str:
        return validate_required_gstin(value)

    @model_validator(mode='after')
    def validate_state_name_and_code(self) -> 'ClientWriteBase':
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
