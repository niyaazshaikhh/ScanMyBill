from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.schemas.newsletter import NewsletterCreate, NewsletterSubscribeResponse

router = APIRouter()


@router.post(
    '/subscribe',
    response_model=NewsletterSubscribeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {'model': NewsletterSubscribeResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {'model': NewsletterSubscribeResponse},
    },
)
def subscribe(payload: NewsletterCreate, db: Session = Depends(get_db)) -> NewsletterSubscribeResponse | JSONResponse:
    normalized_email = str(payload.email).strip().lower()
    duplicate_response = NewsletterSubscribeResponse(
        success=False,
        message='You already subscribed for SMB Newsletters',
    )

    # Prevent duplicate subscriptions for the same email.
    existing = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == normalized_email))
    if existing:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=duplicate_response.model_dump(),
        )

    db.add(NewsletterSubscriber(email=normalized_email))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=duplicate_response.model_dump(),
        )
    except SQLAlchemyError:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=NewsletterSubscribeResponse(
                success=False,
                message='Unable to process newsletter subscription',
            ).model_dump(),
        )

    return NewsletterSubscribeResponse(success=True, message='Subscribed successfully')
