from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.invoice import Invoice, InvoiceItem, InvoiceSource, InvoiceType
from app.models.undo_delete_record import UndoDeleteRecord, UndoDeleteRecordType

UNDO_DELETE_RECORD_ID_QUERY_PARAM = 'undo_record_id'
UNDO_DELETE_RECORD_TYPE_QUERY_PARAM = 'undo_record_type'
UNDO_DELETE_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class NotificationUndoMetadata:
    undo_record_id: str
    record_type: UndoDeleteRecordType
    base_route: str | None


@dataclass(frozen=True)
class UndoDeleteResult:
    record_type: UndoDeleteRecordType
    route: str
    title: str
    message: str


def build_notification_undo_route(base_route: str, undo_record: UndoDeleteRecord) -> str:
    parsed = urlsplit(base_route)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {UNDO_DELETE_RECORD_ID_QUERY_PARAM, UNDO_DELETE_RECORD_TYPE_QUERY_PARAM}
    ]
    query_items.append((UNDO_DELETE_RECORD_ID_QUERY_PARAM, undo_record.id))
    query_items.append((UNDO_DELETE_RECORD_TYPE_QUERY_PARAM, undo_record.record_type.value))
    query = urlencode(query_items, doseq=True)
    return urlunsplit(('', '', parsed.path, query, parsed.fragment))


def parse_notification_undo_metadata(route: str | None) -> NotificationUndoMetadata | None:
    if not route:
        return None

    parsed = urlsplit(route)
    if not parsed.path:
        return None

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    undo_record_id = (query.get(UNDO_DELETE_RECORD_ID_QUERY_PARAM) or '').strip()
    record_type_raw = (query.get(UNDO_DELETE_RECORD_TYPE_QUERY_PARAM) or '').strip().lower()
    if not undo_record_id:
        return None

    if record_type_raw not in {UndoDeleteRecordType.INVOICE.value, UndoDeleteRecordType.CLIENT.value}:
        return None
    record_type = UndoDeleteRecordType(record_type_raw)

    cleaned_query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {UNDO_DELETE_RECORD_ID_QUERY_PARAM, UNDO_DELETE_RECORD_TYPE_QUERY_PARAM}
    ]
    cleaned_query = urlencode(cleaned_query_items, doseq=True)
    base_route = urlunsplit(('', '', parsed.path, cleaned_query, parsed.fragment))
    return NotificationUndoMetadata(
        undo_record_id=undo_record_id,
        record_type=record_type,
        base_route=base_route or parsed.path,
    )


def create_deleted_invoice_undo_record(
    db: Session,
    *,
    owner_id: str,
    invoice: Invoice,
) -> UndoDeleteRecord:
    snapshot = {
        'id': invoice.id,
        'client_id': invoice.client_id,
        'invoice_number': invoice.invoice_number,
        'invoice_date': invoice.invoice_date.isoformat(),
        'place_of_supply': invoice.place_of_supply,
        'place_of_supply_code': invoice.place_of_supply_code,
        'gst_number': invoice.gst_number,
        'type': invoice.type.value,
        'subtotal': float(invoice.subtotal or 0.0),
        'gst_amount': float(invoice.gst_amount or 0.0),
        'total_amount': float(invoice.total_amount or 0.0),
        'source': invoice.source.value,
        'original_file_path': invoice.original_file_path,
        'notes': invoice.notes,
        'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
        'items': [
            {
                'id': item.id,
                'description': item.description,
                'hsn_sac': item.hsn_sac,
                'quantity': float(item.quantity or 0.0),
                'price': float(item.price or 0.0),
                'gst_percent': float(item.gst_percent or 0.0),
                'line_total': float(item.line_total or 0.0),
            }
            for item in invoice.items
        ],
    }

    undo_record = UndoDeleteRecord(
        owner_id=owner_id,
        record_type=UndoDeleteRecordType.INVOICE,
        record_id=invoice.id,
        payload_json=json.dumps(snapshot, separators=(',', ':')),
        expires_at=datetime.now(timezone.utc) + UNDO_DELETE_TTL,
        consumed_at=None,
    )
    db.add(undo_record)
    db.flush()
    return undo_record


def create_deleted_client_undo_record(
    db: Session,
    *,
    owner_id: str,
    client: Client,
) -> UndoDeleteRecord:
    snapshot = {
        'id': client.id,
        'name': client.name,
        'address': client.address,
        'state_name': client.state_name,
        'state_code': client.state_code,
        'email': client.email,
        'gst_number': client.gst_number,
        'created_at': client.created_at.isoformat() if client.created_at else None,
    }

    undo_record = UndoDeleteRecord(
        owner_id=owner_id,
        record_type=UndoDeleteRecordType.CLIENT,
        record_id=client.id,
        payload_json=json.dumps(snapshot, separators=(',', ':')),
        expires_at=datetime.now(timezone.utc) + UNDO_DELETE_TTL,
        consumed_at=None,
    )
    db.add(undo_record)
    db.flush()
    return undo_record


def restore_deleted_record(
    db: Session,
    *,
    owner_id: str,
    undo_record_id: str,
    expected_record_type: UndoDeleteRecordType | None = None,
) -> UndoDeleteResult:
    undo_record = db.scalar(
        select(UndoDeleteRecord).where(
            UndoDeleteRecord.id == undo_record_id,
            UndoDeleteRecord.owner_id == owner_id,
        )
    )
    if not undo_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Undo record not found')

    now = datetime.now(timezone.utc)
    if undo_record.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='This delete action has already been undone.',
        )
    expires_at = undo_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail='Undo window has expired for this delete action.',
        )
    if expected_record_type and undo_record.record_type != expected_record_type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Undo metadata does not match the deleted record type.',
        )

    if undo_record.record_type == UndoDeleteRecordType.INVOICE:
        result = _restore_invoice_snapshot(
            db,
            owner_id=owner_id,
            payload_json=undo_record.payload_json,
        )
    elif undo_record.record_type == UndoDeleteRecordType.CLIENT:
        result = _restore_client_snapshot(
            db,
            owner_id=owner_id,
            payload_json=undo_record.payload_json,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Undo record type is not supported.',
        )

    undo_record.consumed_at = now
    return result


def _restore_invoice_snapshot(
    db: Session,
    *,
    owner_id: str,
    payload_json: str,
) -> UndoDeleteResult:
    try:
        snapshot = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Undo payload for invoice is corrupted.',
        ) from exc

    invoice_id = str(snapshot.get('id') or '').strip()
    invoice_number = str(snapshot.get('invoice_number') or '').strip()
    invoice_date_raw = str(snapshot.get('invoice_date') or '').strip()
    if not invoice_id or not invoice_number or not invoice_date_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Undo payload for invoice is incomplete.',
        )

    existing_by_id = db.scalar(
        select(Invoice.id).where(
            Invoice.id == invoice_id,
            Invoice.owner_id == owner_id,
        )
    )
    if existing_by_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Invoice already exists and cannot be restored again.',
        )

    existing_by_number = db.scalar(
        select(Invoice.id).where(
            Invoice.owner_id == owner_id,
            Invoice.invoice_number == invoice_number,
        )
    )
    if existing_by_number:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Invoice number already exists. Rename/remove it to undo this delete.',
        )

    try:
        invoice_date = date.fromisoformat(invoice_date_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Undo payload has an invalid invoice date.',
        ) from exc

    client_id = snapshot.get('client_id')
    linked_client_id = str(client_id).strip() if isinstance(client_id, str) else None
    if linked_client_id:
        client_exists = db.scalar(
            select(Client.id).where(
                Client.id == linked_client_id,
                Client.owner_id == owner_id,
            )
        )
        if not client_exists:
            linked_client_id = None

    type_value_raw = str(snapshot.get('type') or InvoiceType.PURCHASE.value).lower()
    source_value_raw = str(snapshot.get('source') or InvoiceSource.CREATED.value).lower()
    try:
        invoice_type = InvoiceType(type_value_raw)
    except ValueError:
        invoice_type = InvoiceType.PURCHASE
    try:
        invoice_source = InvoiceSource(source_value_raw)
    except ValueError:
        invoice_source = InvoiceSource.CREATED

    invoice = Invoice(
        id=invoice_id,
        owner_id=owner_id,
        client_id=linked_client_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        place_of_supply=_coerce_optional_text(snapshot.get('place_of_supply')),
        place_of_supply_code=_coerce_optional_text(snapshot.get('place_of_supply_code')),
        gst_number=_coerce_optional_text(snapshot.get('gst_number')),
        type=invoice_type,
        subtotal=_coerce_float(snapshot.get('subtotal')),
        gst_amount=_coerce_float(snapshot.get('gst_amount')),
        total_amount=_coerce_float(snapshot.get('total_amount')),
        source=invoice_source,
        original_file_path=_coerce_optional_text(snapshot.get('original_file_path')),
        notes=_coerce_optional_text(snapshot.get('notes')),
    )

    created_at_raw = snapshot.get('created_at')
    if isinstance(created_at_raw, str) and created_at_raw.strip():
        parsed_created_at = _parse_iso_datetime(created_at_raw.strip())
        if parsed_created_at is not None:
            invoice.created_at = parsed_created_at

    db.add(invoice)

    item_snapshots = snapshot.get('items')
    if isinstance(item_snapshots, list):
        for item_snapshot in item_snapshots:
            if not isinstance(item_snapshot, dict):
                continue

            item_kwargs = {
                'invoice_id': invoice_id,
                'description': str(item_snapshot.get('description') or '').strip() or 'Item',
                'hsn_sac': _coerce_optional_text(item_snapshot.get('hsn_sac')),
                'quantity': _coerce_float(item_snapshot.get('quantity'), fallback=1.0),
                'price': _coerce_float(item_snapshot.get('price')),
                'gst_percent': _coerce_float(item_snapshot.get('gst_percent')),
                'line_total': _coerce_float(item_snapshot.get('line_total')),
            }
            item_id = item_snapshot.get('id')
            if isinstance(item_id, str) and item_id.strip():
                item_kwargs['id'] = item_id.strip()

            db.add(InvoiceItem(**item_kwargs))

    return UndoDeleteResult(
        record_type=UndoDeleteRecordType.INVOICE,
        route='/invoices',
        title='Invoice Restored',
        message=f'Invoice {invoice_number} has been restored.',
    )


def _restore_client_snapshot(
    db: Session,
    *,
    owner_id: str,
    payload_json: str,
) -> UndoDeleteResult:
    try:
        snapshot = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Undo payload for client is corrupted.',
        ) from exc

    client_id = str(snapshot.get('id') or '').strip()
    client_name = str(snapshot.get('name') or '').strip()
    if not client_id or not client_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Undo payload for client is incomplete.',
        )

    existing_by_id = db.scalar(
        select(Client.id).where(
            Client.id == client_id,
            Client.owner_id == owner_id,
        )
    )
    if existing_by_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Client already exists and cannot be restored again.',
        )

    existing_by_name = db.scalar(
        select(Client.id).where(
            Client.owner_id == owner_id,
            Client.name == client_name,
        )
    )
    if existing_by_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Client name already exists. Rename/remove it to undo this delete.',
        )

    gst_number = _coerce_optional_text(snapshot.get('gst_number'))
    if gst_number:
        duplicate_gst = db.scalar(
            select(Client.id).where(
                Client.owner_id == owner_id,
                Client.gst_number == gst_number,
            )
        )
        if duplicate_gst:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Client GST number already exists. Update it first to undo this delete.',
            )

    client = Client(
        id=client_id,
        owner_id=owner_id,
        name=client_name,
        address=_coerce_optional_text(snapshot.get('address')),
        state_name=_coerce_optional_text(snapshot.get('state_name')),
        state_code=_coerce_optional_text(snapshot.get('state_code')),
        email=_coerce_optional_text(snapshot.get('email')),
        gst_number=gst_number,
    )

    created_at_raw = snapshot.get('created_at')
    if isinstance(created_at_raw, str) and created_at_raw.strip():
        parsed_created_at = _parse_iso_datetime(created_at_raw.strip())
        if parsed_created_at is not None:
            client.created_at = parsed_created_at

    db.add(client)
    return UndoDeleteResult(
        record_type=UndoDeleteRecordType.CLIENT,
        route='/clients',
        title='Client Restored',
        message=f'Client {client_name} has been restored.',
    )


def _coerce_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _coerce_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_iso_datetime(value: str) -> datetime | None:
    normalized = value
    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
