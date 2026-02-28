from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.client import Client
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.client import ClientAnalytics, ClientCreate, ClientResponse, ClientsOverview

router = APIRouter()


@router.get('', response_model=list[ClientResponse])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClientResponse]:
    clients = db.scalars(
        select(Client)
        .where(Client.owner_id == current_user.id)
        .order_by(Client.created_at.desc())
    ).all()

    totals = db.execute(
        select(
            Invoice.client_id,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
        )
        .where(Invoice.owner_id == current_user.id)
        .group_by(Invoice.client_id)
    ).all()
    totals_map = {row[0]: (int(row[1]), float(row[2])) for row in totals if row[0]}

    response: list[ClientResponse] = []
    for client in clients:
        transactions, revenue = totals_map.get(client.id, (0, 0.0))
        response.append(
            ClientResponse(
                **client.__dict__,
                total_transactions=transactions,
                total_revenue=round(revenue, 2),
            )
        )

    return response


@router.post('', response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClientResponse:
    existing = db.scalar(
        select(Client).where(
            Client.owner_id == current_user.id,
            Client.name == payload.name,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Client already exists')

    client = Client(owner_id=current_user.id, **payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)

    return ClientResponse(
        **client.__dict__,
        total_transactions=0,
        total_revenue=0.0,
    )


@router.get('/analytics', response_model=ClientsOverview)
def client_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClientsOverview:
    total_clients = db.scalar(
        select(func.count(Client.id)).where(Client.owner_id == current_user.id)
    ) or 0

    grouped = db.execute(
        select(
            Client.id,
            Client.name,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
        )
        .join(Invoice, Invoice.client_id == Client.id, isouter=True)
        .where(Client.owner_id == current_user.id)
        .group_by(Client.id, Client.name)
        .order_by(func.coalesce(func.sum(Invoice.total_amount), 0.0).desc())
    ).all()

    top_clients = [
        ClientAnalytics(
            client_id=row[0],
            client_name=row[1],
            transactions=int(row[2]),
            revenue=round(float(row[3]), 2),
        )
        for row in grouped[:10]
    ]

    total_transactions = sum(item.transactions for item in top_clients)
    total_revenue = sum(item.revenue for item in top_clients)

    return ClientsOverview(
        total_clients=int(total_clients),
        total_transactions=int(total_transactions),
        total_revenue=round(total_revenue, 2),
        top_clients=top_clients,
    )