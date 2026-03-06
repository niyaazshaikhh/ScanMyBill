from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.utils.gstin import normalize_gstin

DEFAULT_CLIENT_ADDRESS = 'Unknown'
DEFAULT_STATE_NAME = 'Maharashtra'
DEFAULT_STATE_CODE = '27'
DEFAULT_GST_NUMBER = 'URP'


def resolve_client(
    db: Session,
    client_name: str,
    owner_id: str,
    gst_number: str | None = None,
) -> str:
    normalized_name = _normalize_client_name(client_name)
    if not normalized_name:
        raise ValueError('client_name is required')
    canonical_name = normalized_name[:30]
    normalized_gst = normalize_gstin(gst_number)

    if normalized_gst:
        existing_by_gst = db.scalar(
            select(Client)
            .where(
                Client.owner_id == owner_id,
                func.upper(Client.gst_number) == normalized_gst,
            )
            .limit(1)
        )
        if existing_by_gst is not None:
            return existing_by_gst.id

    existing_client = db.scalar(
        select(Client)
        .where(
            Client.owner_id == owner_id,
            Client.name.ilike(canonical_name),
        )
        .limit(1)
    )
    if existing_client is not None:
        if normalized_gst and _is_placeholder_gst(existing_client.gst_number):
            existing_client.gst_number = normalized_gst
            db.flush()
        return existing_client.id

    client = Client(
        owner_id=owner_id,
        name=canonical_name,
        address=DEFAULT_CLIENT_ADDRESS,
        state_name=DEFAULT_STATE_NAME,
        state_code=DEFAULT_STATE_CODE,
        gst_number=normalized_gst or DEFAULT_GST_NUMBER,
    )
    db.add(client)
    db.flush()
    return client.id


def _normalize_client_name(value: str | None) -> str:
    if value is None:
        return ''
    cleaned = re.sub(r'\s+', ' ', value).strip()
    return cleaned


def _is_placeholder_gst(value: str | None) -> bool:
    cleaned = (value or '').strip().upper()
    if cleaned in {'', DEFAULT_GST_NUMBER}:
        return True
    return normalize_gstin(cleaned) is None
