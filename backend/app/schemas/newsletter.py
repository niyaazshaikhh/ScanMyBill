from pydantic import BaseModel, EmailStr


class NewsletterCreate(BaseModel):
    email: EmailStr


class NewsletterSubscribeResponse(BaseModel):
    success: bool
    message: str
