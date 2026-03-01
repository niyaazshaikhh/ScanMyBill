from pydantic import BaseModel, EmailStr


class NewsletterCreate(BaseModel):
    email: EmailStr


class NewsletterSubscribeResponse(BaseModel):
    message: str
