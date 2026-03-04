from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client

DEFAULT_CLIENT_ADDRESS = 'Unknown'
DEFAULT_STATE_NAME = 'Maharashtra'
DEFAULT_STATE_CODE = '27'
DEFAULT_GST_NUMBER = 'URP'


def resolve_client(db: Session, client_name: str, owner_id: str) -> str:
    normalized_name = _normalize_client_name(client_name)
    if not normalized_name:
        raise ValueError('client_name is required')

    existing_client = db.scalar(
        select(Client)
        .where(
            Client.owner_id == owner_id,
            Client.name.ilike(normalized_name),
        )
        .limit(1)
    )
    if existing_client is not None:
        return existing_client.id

    client = Client(
        owner_id=owner_id,
        name=normalized_name[:30],
        address=DEFAULT_CLIENT_ADDRESS,
        state_name=DEFAULT_STATE_NAME,
        state_code=DEFAULT_STATE_CODE,
        gst_number=DEFAULT_GST_NUMBER,
    )
    db.add(client)
    db.flush()
    return client.id


def _normalize_client_name(value: str | None) -> str:
    if value is None:
        return ''
    cleaned = re.sub(r'\s+', ' ', value).strip()
    return cleaned
