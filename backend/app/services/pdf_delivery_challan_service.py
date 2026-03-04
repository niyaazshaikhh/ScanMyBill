from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape

from app.core.config import settings
from app.services.pdf_invoice_service import PDFInvoiceDataError, PDFInvoiceGenerationError, PDFInvoiceTemplateError

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = APP_ROOT.parent
PRIMARY_TEMPLATE_DIR = APP_ROOT / 'templates'
LEGACY_TEMPLATE_DIR = BACKEND_ROOT / 'templates'
TEMPLATE_NAME = 'delivery_challan_template.html'

_REQUIRED_FIELDS = (
    'user_id',
    'challan_number',
    'order_number',
    'challan_date',
    'client_name',
    'items',
    'subtotal',
)

_REQUIRED_ITEM_FIELDS = (
    'description',
    'quantity',
    'rate',
    'line_total',
)

_REQUIRED_NUMERIC_FIELDS = ('challan_number', 'subtotal')
_REQUIRED_ITEM_NUMERIC_FIELDS = ('quantity', 'rate', 'line_total')


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


def _validate_delivery_challan_data(challan_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(challan_data, dict):
        raise PDFInvoiceDataError('challan_data must be a dictionary.')

    missing_fields = [field for field in _REQUIRED_FIELDS if field not in challan_data]
    if missing_fields:
        raise PDFInvoiceDataError(f'Missing required challan fields: {", ".join(missing_fields)}')

    user_id = challan_data.get('user_id')
    if user_id is None or not str(user_id).strip():
        raise PDFInvoiceDataError('user_id is required for challan PDF generation.')
    if not _sanitize_user_id(str(user_id)):
        raise PDFInvoiceDataError('user_id contains no valid safe characters.')

    for field in _REQUIRED_NUMERIC_FIELDS:
        _validate_numeric_field(challan_data[field], field)

    items = challan_data.get('items')
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

    return challan_data


def generate_delivery_challan_pdf(challan_data: dict[str, Any]) -> str:
    validated_data = _validate_delivery_challan_data(challan_data)
    safe_user_id = _sanitize_user_id(str(validated_data['user_id']))

    uploads_root = _uploads_root()
    relative_dir = Path('bills') / safe_user_id
    target_dir = (uploads_root / relative_dir).resolve()
    if not _is_within(uploads_root, target_dir):
        raise PDFInvoiceGenerationError('Invalid target directory for challan PDF generation.')

    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f'{uuid4().hex}.pdf'
    relative_path = (relative_dir / file_name).as_posix()
    final_path = target_dir / file_name
    temp_path = target_dir / f'.{uuid4().hex}.tmp'

    try:
        template = _template_environment().get_template(TEMPLATE_NAME)
    except TemplateNotFound as exc:
        raise PDFInvoiceTemplateError(f'Delivery challan template not found: {TEMPLATE_NAME}') from exc

    render_context = dict(validated_data)
    render_context.pop('user_id', None)

    try:
        rendered_html = template.render(**render_context)
    except Exception as exc:
        raise PDFInvoiceTemplateError('Failed to render delivery challan template.') from exc

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
        raise PDFInvoiceGenerationError('Failed to generate delivery challan PDF.') from exc
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return relative_path
