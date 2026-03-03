from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape

from app.core.config import settings

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = APP_ROOT.parent
PRIMARY_TEMPLATE_DIR = APP_ROOT / 'templates'
LEGACY_TEMPLATE_DIR = BACKEND_ROOT / 'templates'
TEMPLATE_NAME = 'invoice_template.html'

_REQUIRED_FIELDS = (
    'company_name',
    'company_address',
    'gstin',
    'invoice_number',
    'invoice_date',
    'place_of_supply',
    'state_code',
    'client_name',
    'client_address',
    'client_gstin',
    'items',
    'subtotal',
    'cgst',
    'sgst',
    'igst',
    'total',
    'bank_details',
)

_REQUIRED_ITEM_FIELDS = (
    'description',
    'hsn',
    'quantity',
    'rate',
    'tax_percent',
    'amount',
)

_REQUIRED_NUMERIC_FIELDS = ('subtotal', 'cgst', 'sgst', 'igst', 'total')
_REQUIRED_ITEM_NUMERIC_FIELDS = ('quantity', 'rate', 'tax_percent', 'amount')


class PDFInvoiceError(RuntimeError):
    pass


class PDFInvoiceTemplateError(PDFInvoiceError):
    pass


class PDFInvoiceDataError(PDFInvoiceError):
    pass


class PDFInvoiceGenerationError(PDFInvoiceError):
    pass


def _is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _uploads_root() -> Path:
    configured = Path(settings.uploads_dir)
    candidate = configured if configured.is_absolute() else BACKEND_ROOT / configured
    resolved = candidate.resolve()

    if not _is_within(BACKEND_ROOT, resolved):
        raise PDFInvoiceGenerationError('uploads_dir must be inside the backend directory.')
    return resolved


def _template_dirs() -> list[str]:
    dirs: list[str] = []
    for candidate in (PRIMARY_TEMPLATE_DIR, LEGACY_TEMPLATE_DIR):
        if candidate.exists() and candidate.is_dir():
            dirs.append(str(candidate))

    if not dirs:
        dirs.append(str(PRIMARY_TEMPLATE_DIR))
    return dirs


def _template_base_dir() -> Path:
    if PRIMARY_TEMPLATE_DIR.exists() and PRIMARY_TEMPLATE_DIR.is_dir():
        return PRIMARY_TEMPLATE_DIR
    return LEGACY_TEMPLATE_DIR


def _template_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_template_dirs()),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _sanitize_user_id(user_id: str) -> str:
    return ''.join(char for char in user_id if char.isalnum() or char in {'-', '_'})


def _validate_numeric_field(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise PDFInvoiceDataError(f'{field_name} must be numeric.')
    return float(value)


def _validate_invoice_data(invoice_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(invoice_data, dict):
        raise PDFInvoiceDataError('invoice_data must be a dictionary.')

    missing_fields = [field for field in _REQUIRED_FIELDS if field not in invoice_data]
    if missing_fields:
        raise PDFInvoiceDataError(f'Missing required invoice fields: {", ".join(missing_fields)}')

    user_id = invoice_data.get('user_id')
    if user_id is None or not str(user_id).strip():
        raise PDFInvoiceDataError('user_id is required for invoice PDF generation.')
    if not _sanitize_user_id(str(user_id)):
        raise PDFInvoiceDataError('user_id contains no valid safe characters.')

    for field in _REQUIRED_NUMERIC_FIELDS:
        _validate_numeric_field(invoice_data[field], field)

    items = invoice_data.get('items')
    if not isinstance(items, list) or not items:
        raise PDFInvoiceDataError('items must be a non-empty list.')

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise PDFInvoiceDataError(f'items[{index}] must be an object.')

        missing_item_fields = [field for field in _REQUIRED_ITEM_FIELDS if field not in item]
        if missing_item_fields:
            raise PDFInvoiceDataError(
                f'Missing required item fields in items[{index}]: {", ".join(missing_item_fields)}'
            )

        for field in _REQUIRED_ITEM_NUMERIC_FIELDS:
            _validate_numeric_field(item[field], f'items[{index}].{field}')

    return invoice_data


def resolve_generated_pdf_path(stored_path: str) -> Path:
    uploads_root = _uploads_root()
    raw_path = Path(stored_path)
    candidate = raw_path if raw_path.is_absolute() else uploads_root / raw_path
    resolved = candidate.resolve()

    if not _is_within(uploads_root, resolved):
        raise PDFInvoiceGenerationError('Resolved invoice PDF path is outside uploads directory.')
    return resolved


def remove_generated_pdf(stored_path: str) -> None:
    try:
        target = resolve_generated_pdf_path(stored_path)
    except PDFInvoiceGenerationError:
        return

    if target.exists():
        target.unlink()

    bills_root = (_uploads_root() / 'bills').resolve()
    parent = target.parent
    while parent.exists() and _is_within(bills_root, parent) and parent != bills_root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def generate_invoice_pdf(invoice_data: dict) -> str:
    validated_data = _validate_invoice_data(invoice_data)
    safe_user_id = _sanitize_user_id(str(validated_data['user_id']))

    uploads_root = _uploads_root()
    relative_dir = Path('bills') / safe_user_id
    target_dir = (uploads_root / relative_dir).resolve()
    if not _is_within(uploads_root, target_dir):
        raise PDFInvoiceGenerationError('Invalid target directory for invoice PDF generation.')

    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f'{uuid4().hex}.pdf'
    relative_path = (relative_dir / file_name).as_posix()
    final_path = target_dir / file_name
    temp_path = target_dir / f'.{uuid4().hex}.tmp'

    try:
        template = _template_environment().get_template(TEMPLATE_NAME)
    except TemplateNotFound as exc:
        raise PDFInvoiceTemplateError(f'Invoice template not found: {TEMPLATE_NAME}') from exc

    render_context = dict(validated_data)
    render_context.pop('user_id', None)

    try:
        rendered_html = template.render(**render_context)
    except Exception as exc:
        raise PDFInvoiceTemplateError('Failed to render invoice template.') from exc

    try:
        from weasyprint import HTML
    except ModuleNotFoundError as exc:
        raise PDFInvoiceGenerationError(
            'WeasyPrint is not installed. Install backend requirements to enable PDF generation.'
        ) from exc

    try:
        HTML(string=rendered_html, base_url=str(_template_base_dir())).write_pdf(str(temp_path))
        temp_path.replace(final_path)
    except Exception as exc:
        raise PDFInvoiceGenerationError('Failed to generate invoice PDF.') from exc
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return relative_path
