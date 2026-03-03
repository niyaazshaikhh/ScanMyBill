from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.hsn_sac_master import HSNSACMaster
from app.models.user import User
from app.schemas.hsn_sac_master import HSNSACMasterCreate, HSNSACMasterResponse

router = APIRouter()


def _to_response(entry: HSNSACMaster) -> HSNSACMasterResponse:
    return HSNSACMasterResponse(
        id=entry.id,
        description=entry.description,
        hsn_sac_code=entry.hsn_sac_code,
        tax_rate=round(entry.tax_rate, 2),
        created_at=entry.created_at,
    )


@router.get('', response_model=list[HSNSACMasterResponse])
def list_hsn_sac_master_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HSNSACMasterResponse]:
    rows = db.scalars(
        select(HSNSACMaster)
        .where(HSNSACMaster.owner_id == current_user.id)
        .order_by(HSNSACMaster.description.asc(), HSNSACMaster.created_at.desc())
    ).all()
    return [_to_response(row) for row in rows]


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

    db.delete(record)
    db.commit()

