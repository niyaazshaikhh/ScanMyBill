from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.personal_details import PersonalDetails
from app.models.user import User
from app.schemas.personal_details import PersonalDetailsResponse, PersonalDetailsUpsertRequest
from app.schemas.user import CurrentUserResponse
from app.services.notifications import create_notification

router = APIRouter()


def _create_notification_best_effort(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None = '/settings/personal_details',
) -> None:
    try:
        notification = create_notification(
            db,
            user_id=user_id,
            title=title,
            message=message,
            route=route,
        )
        if notification:
            db.commit()
    except Exception:
        db.rollback()


@router.get('/me', response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)


@router.get('/personal-details', response_model=PersonalDetailsResponse)
def get_personal_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonalDetailsResponse:
    details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))
    if details is None:
        return PersonalDetailsResponse(
            company_name=None,
            gstin_number=None,
            address=None,
            state_name=None,
            state_code=None,
            email=None,
            bank_name=None,
            account_number=None,
            branch=None,
            ifsc_code=None,
            updated_at=None,
        )
    return PersonalDetailsResponse.model_validate(details)


@router.put('/personal-details', response_model=PersonalDetailsResponse)
def upsert_personal_details(
    payload: PersonalDetailsUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonalDetailsResponse:
    gstin_used_by_other_user = db.scalar(
        select(PersonalDetails.owner_id).where(
            PersonalDetails.gstin_number == payload.gstin_number,
            PersonalDetails.owner_id != current_user.id,
        )
    )
    if gstin_used_by_other_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='GST/IN Number already exists for another account',
        )

    details = db.scalar(select(PersonalDetails).where(PersonalDetails.owner_id == current_user.id))

    if details is None:
        details = PersonalDetails(
            owner_id=current_user.id,
            company_name=payload.company_name,
            gstin_number=payload.gstin_number,
            address=payload.address,
            state_name=payload.state_name,
            state_code=payload.state_code,
            email=payload.email,
            bank_name=payload.bank_name,
            account_number=payload.account_number,
            branch=payload.branch,
            ifsc_code=payload.ifsc_code,
        )
        db.add(details)
    else:
        details.company_name = payload.company_name
        details.gstin_number = payload.gstin_number
        details.address = payload.address
        details.state_name = payload.state_name
        details.state_code = payload.state_code
        details.email = payload.email
        details.bank_name = payload.bank_name
        details.account_number = payload.account_number
        details.branch = payload.branch
        details.ifsc_code = payload.ifsc_code

    db.commit()
    db.refresh(details)

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Personal Details Updated',
        message='Your personal and business details have been updated.',
    )

    return PersonalDetailsResponse.model_validate(details)
