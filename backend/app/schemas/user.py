from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr

    model_config = {'from_attributes': True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=255)
    new_password: str = Field(min_length=8, max_length=128)
