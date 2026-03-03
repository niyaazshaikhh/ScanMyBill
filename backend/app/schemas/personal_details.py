from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.validation_rules import (
    ACCOUNT_NUMBER_PATTERN,
    COMPANY_NAME_PATTERN,
    EMAIL_PATTERN,
    IFSC_PATTERN,
    STATE_CODE_BY_NAME,
    STATE_CODE_PATTERN,
    STATE_NAME_BY_LOWERCASE,
    strip_required,
    validate_required_gstin,
)


class PersonalDetailsUpsertRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=20)
    gstin_number: str = Field(min_length=15, max_length=15)
    address: str = Field(min_length=1, max_length=115)
    state_name: str = Field(min_length=1, max_length=64)
    state_code: str = Field(min_length=2, max_length=2)
    email: str = Field(min_length=3, max_length=255)
    bank_name: str = Field(min_length=1, max_length=15)
    account_number: str = Field(min_length=6, max_length=34)
    branch: str = Field(min_length=1, max_length=15)
    ifsc_code: str = Field(min_length=11, max_length=11)

    @field_validator(
        'company_name',
        'gstin_number',
        'address',
        'state_name',
        'state_code',
        'email',
        'bank_name',
        'account_number',
        'branch',
        'ifsc_code',
    )
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        return strip_required(value, 'Field')

    @field_validator('company_name')
    @classmethod
    def validate_company_name(cls, value: str) -> str:
        cleaned = strip_required(value, 'Company Name')
        if not COMPANY_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError('Company Name should be alphanumeric and special characters are not allowed.')
        return cleaned

    @field_validator('gstin_number')
    @classmethod
    def validate_gstin(cls, value: str) -> str:
        return validate_required_gstin(value)

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

    @field_validator('email')
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = strip_required(value, 'Email').lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError('Email is invalid.')
        return normalized

    @field_validator('bank_name')
    @classmethod
    def validate_bank_name(cls, value: str) -> str:
        return strip_required(value, 'Bank Name')

    @field_validator('account_number')
    @classmethod
    def validate_account_number(cls, value: str) -> str:
        cleaned = strip_required(value, 'A/c No.')
        if not ACCOUNT_NUMBER_PATTERN.fullmatch(cleaned):
            raise ValueError('A/c No. should contain only digits (6 to 34 digits).')
        return cleaned

    @field_validator('branch')
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return strip_required(value, 'Branch')

    @field_validator('ifsc_code')
    @classmethod
    def validate_ifsc_code(cls, value: str) -> str:
        normalized = strip_required(value, 'IFSC Code').upper()
        if not IFSC_PATTERN.fullmatch(normalized):
            raise ValueError('IFSC Code should be an 11-character alphanumeric code.')
        return normalized

    @model_validator(mode='after')
    def validate_state_name_and_code(self) -> 'PersonalDetailsUpsertRequest':
        expected_code = STATE_CODE_BY_NAME.get(self.state_name.lower())
        if expected_code and self.state_code != expected_code:
            raise ValueError('State Code does not match the selected State Name.')
        return self


class PersonalDetailsResponse(BaseModel):
    company_name: str | None
    gstin_number: str | None
    address: str | None
    state_name: str | None
    state_code: str | None
    email: str | None
    bank_name: str | None
    account_number: str | None
    branch: str | None
    ifsc_code: str | None
    updated_at: datetime | None

    model_config = {'from_attributes': True}
