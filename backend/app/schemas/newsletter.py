from pydantic import BaseModel, ConfigDict, EmailStr


class NewsletterCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: EmailStr


class NewsletterSubscribeResponse(BaseModel):
    success: bool
    message: str
