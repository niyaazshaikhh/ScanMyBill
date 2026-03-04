from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceType
from app.models.non_gst_challan import NonGSTChallan
from app.models.user import User
from app.schemas.client import ClientAnalytics, ClientCreate, ClientResponse, ClientUpdate, ClientsOverview
from app.services.notifications import create_notification

router = APIRouter()


def _create_notification_best_effort(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None = '/clients',
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


@router.get('', response_model=list[ClientResponse])
def list_clients(
    invoice_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClientResponse]:
    typed_invoice_type: InvoiceType | None = None
    if invoice_type:
        normalized = invoice_type.lower().strip()
        if normalized not in {InvoiceType.SALES.value, InvoiceType.PURCHASE.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid invoice type')
        typed_invoice_type = InvoiceType(normalized)

    clients = db.scalars(
        select(Client)
        .where(Client.owner_id == current_user.id)
        .order_by(Client.created_at.desc())
    ).all()

    totals_query = (
        select(
            Invoice.client_id,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
        )
        .where(Invoice.owner_id == current_user.id)
        .group_by(Invoice.client_id)
    )
    if typed_invoice_type is not None:
        totals_query = totals_query.where(Invoice.type == typed_invoice_type)

    totals = db.execute(totals_query).all()
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

    client = Client(
        owner_id=current_user.id,
        name=payload.name,
        address=payload.address,
        state_name=payload.state_name,
        state_code=payload.state_code,
        email=payload.email,
        gst_number=payload.gst_number,
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Client Created',
        message=f'Client {client.name} has been added.',
    )

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


@router.put('/{client_id}', response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClientResponse:
    client = db.scalar(
        select(Client).where(Client.id == client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Client not found')

    duplicate = db.scalar(
        select(Client).where(
            Client.owner_id == current_user.id,
            Client.name == payload.name,
            Client.id != client_id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Client already exists')

    client.name = payload.name
    client.address = payload.address
    client.state_name = payload.state_name
    client.state_code = payload.state_code
    client.email = payload.email
    client.gst_number = payload.gst_number

    db.commit()
    db.refresh(client)

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Client Updated',
        message=f'Client {client.name} has been updated.',
    )

    totals = db.execute(
        select(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
        ).where(
            Invoice.owner_id == current_user.id,
            Invoice.client_id == client.id,
        )
    ).one()

    return ClientResponse(
        **client.__dict__,
        total_transactions=int(totals[0] or 0),
        total_revenue=round(float(totals[1] or 0.0), 2),
    )


@router.delete('/{client_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    client = db.scalar(
        select(Client).where(Client.id == client_id, Client.owner_id == current_user.id)
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Client not found')
    client_name = client.name

    invoices = db.scalars(
        select(Invoice).where(
            Invoice.owner_id == current_user.id,
            Invoice.client_id == client.id,
        )
    ).all()
    for invoice in invoices:
        invoice.client_id = None

    challans = db.scalars(
        select(NonGSTChallan).where(
            NonGSTChallan.owner_id == current_user.id,
            NonGSTChallan.client_id == client.id,
        )
    ).all()
    for challan in challans:
        challan.client_id = None

    db.delete(client)
    db.commit()

    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Client Deleted',
        message=f'Client {client_name} has been deleted.',
    )
