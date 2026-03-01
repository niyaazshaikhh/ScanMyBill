from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.schemas.newsletter import NewsletterCreate, NewsletterSubscribeResponse

router = APIRouter()


@router.post('/subscribe', response_model=NewsletterSubscribeResponse, status_code=status.HTTP_201_CREATED)
def subscribe(payload: NewsletterCreate, db: Session = Depends(get_db)) -> NewsletterSubscribeResponse:
    normalized_email = str(payload.email).strip().lower()

    # Prevent duplicate subscriptions for the same email.
    existing = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == normalized_email))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Already subscribed')

    db.add(NewsletterSubscriber(email=normalized_email))
    db.commit()
    return NewsletterSubscribeResponse(message='Subscribed successfully')
