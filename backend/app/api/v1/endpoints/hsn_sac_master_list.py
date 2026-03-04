from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.hsn_sac_master import HSNSACMaster
from app.models.user import User
from app.schemas.hsn_sac_master import HSNSACMasterCreate, HSNSACMasterResponse
from app.services.notifications import create_notification

router = APIRouter()


def _to_response(entry: HSNSACMaster) -> HSNSACMasterResponse:
    return HSNSACMasterResponse(
        id=entry.id,
        description=entry.description,
        hsn_sac_code=entry.hsn_sac_code,
        tax_rate=round(entry.tax_rate, 2),
        created_at=entry.created_at,
    )


def _create_notification_best_effort(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None = '/hsn-sac-master-list',
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


@router.get('', response_model=list[HSNSACMasterResponse])
def list_hsn_sac_master_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HSNSACMasterResponse]:
    rows = db.scalars(
        select(HSNSACMaster)
        .where(HSNSACMaster.owner_id == current_user.id)
        .order_by(HSNSACMaster.created_at.desc())
    ).all()

    unique_by_code: dict[str, HSNSACMaster] = {}
    for row in rows:
        if row.hsn_sac_code in unique_by_code:
            continue
        unique_by_code[row.hsn_sac_code] = row

    unique_rows = list(unique_by_code.values())
    unique_rows.sort(key=lambda item: item.created_at, reverse=True)
    unique_rows.sort(key=lambda item: item.description.casefold())
    return [_to_response(row) for row in unique_rows]


@router.post('', response_model=HSNSACMasterResponse, status_code=status.HTTP_201_CREATED)
def create_hsn_sac_master_entry(
    payload: HSNSACMasterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HSNSACMasterResponse:
    existing = db.scalar(
        select(HSNSACMaster).where(
            HSNSACMaster.owner_id == current_user.id,
            HSNSACMaster.hsn_sac_code == payload.hsn_sac_code,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='HSN/SAC code already exists.')

    record = HSNSACMaster(
        owner_id=current_user.id,
        description=payload.description,
        hsn_sac_code=payload.hsn_sac_code,
        tax_rate=payload.tax_rate,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='HSN/SAC code already exists.') from exc
    db.refresh(record)
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='HSN/SAC Entry Created',
        message=f'HSN/SAC {record.hsn_sac_code} has been added to master list.',
    )
    return _to_response(record)


@router.put('/{entry_id}', response_model=HSNSACMasterResponse)
def update_hsn_sac_master_entry(
    entry_id: str,
    payload: HSNSACMasterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HSNSACMasterResponse:
    record = db.scalar(
        select(HSNSACMaster).where(
            HSNSACMaster.id == entry_id,
            HSNSACMaster.owner_id == current_user.id,
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='HSN/SAC entry not found')

    duplicate = db.scalar(
        select(HSNSACMaster).where(
            HSNSACMaster.owner_id == current_user.id,
            HSNSACMaster.hsn_sac_code == payload.hsn_sac_code,
            HSNSACMaster.id != entry_id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='HSN/SAC code already exists.')

    record.description = payload.description
    record.hsn_sac_code = payload.hsn_sac_code
    record.tax_rate = payload.tax_rate

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='HSN/SAC code already exists.') from exc
    db.refresh(record)
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='HSN/SAC Entry Updated',
        message=f'HSN/SAC {record.hsn_sac_code} has been updated in master list.',
    )
    return _to_response(record)


@router.delete('/{entry_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_hsn_sac_master_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    record = db.scalar(
        select(HSNSACMaster).where(
            HSNSACMaster.id == entry_id,
            HSNSACMaster.owner_id == current_user.id,
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='HSN/SAC entry not found')
    hsn_sac_code = record.hsn_sac_code

    db.delete(record)
    db.commit()
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='HSN/SAC Entry Deleted',
        message=f'HSN/SAC {hsn_sac_code} has been removed from master list.',
    )
