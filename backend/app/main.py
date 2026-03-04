import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.api import api_router
from app.core.auth_exceptions import AuthException, auth_error_payload
from app.core.auth_middleware import AuthSessionMiddleware
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.models import *  # noqa: F401,F403
from app.services.admin_bootstrap import ensure_default_admin_user


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


_configure_logging()
logger = logging.getLogger('scanmybill.api')

app = FastAPI(
    title=settings.app_name,
    version='1.0.0',
    docs_url='/docs' if settings.docs_enabled else None,
    redoc_url='/redoc' if settings.docs_enabled else None,
)


def _path_is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _validate_security_configuration() -> None:
    issues: list[str] = []

    if settings.is_production:
        if settings.secret_key == 'change-this-in-production' or len(settings.secret_key) < 32:
            issues.append('SECRET_KEY must be at least 32 chars and non-default.')
        if not settings.cookie_secure:
            issues.append('COOKIE_SECURE must be true in production.')
        if settings.expose_password_reset_token:
            issues.append('EXPOSE_PASSWORD_RESET_TOKEN must be false in production.')
        if '*' in settings.cors_origins:
            issues.append("CORS_ORIGINS cannot include '*' in production.")

    if issues:
        raise RuntimeError('Security configuration error(s): ' + ' '.join(issues))


def _resolved_uploads_path() -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    configured = Path(settings.uploads_dir)
    candidate = configured if configured.is_absolute() else backend_root / configured
    resolved = candidate.resolve()
    if not _path_is_within(backend_root, resolved):
        raise RuntimeError('UPLOADS_DIR must be inside the backend directory.')
    return resolved


if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))

if settings.enforce_https:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthSessionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials='*' not in settings.cors_origins,
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=['X-Access-Token', 'X-Token-Refreshed'],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(AuthException)
async def auth_exception_handler(_: Request, exc: AuthException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=auth_error_payload(message=exc.message, error_code=exc.error_code),
        headers=exc.headers,
    )


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', None)
    headers = dict(exc.headers or {})
    if request_id:
        headers['X-Request-ID'] = request_id

    detail = exc.detail
    if isinstance(detail, dict):
        payload = detail
    else:
        payload = {'detail': detail}
    return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.warning(
        'Validation failed request_id=%s path=%s errors=%s',
        request_id,
        request.url.path,
        exc.errors(),
    )
    response = await request_validation_exception_handler(request, exc)
    if request_id:
        response.headers['X-Request-ID'] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Unhandled exception request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={'detail': 'Internal server error'},
        headers={'X-Request-ID': request_id} if request_id != 'n/a' else None,
    )


def _ensure_personal_details_columns() -> None:
    expected_columns: dict[str, str] = {
        'address': 'VARCHAR(115)',
        'state_name': 'VARCHAR(64)',
        'state_code': 'VARCHAR(2)',
        'gst_filing_period': 'VARCHAR(16)',
        'email': 'VARCHAR(255)',
        'bank_name': 'VARCHAR(15)',
        'account_number': 'VARCHAR(34)',
        'branch': 'VARCHAR(15)',
        'ifsc_code': 'VARCHAR(11)',
    }

    inspector = inspect(engine)
    if 'personal_details' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('personal_details')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(
                text(f'ALTER TABLE personal_details ADD COLUMN {column_name} {column_type}')
            )


def _ensure_clients_columns() -> None:
    expected_columns: dict[str, str] = {
        'address': 'VARCHAR(115)',
        'state_name': 'VARCHAR(64)',
        'state_code': 'VARCHAR(2)',
    }

    inspector = inspect(engine)
    if 'clients' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('clients')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(
                text(f'ALTER TABLE clients ADD COLUMN {column_name} {column_type}')
            )


def _ensure_clients_name_column_length() -> None:
    inspector = inspect(engine)
    if 'clients' not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == 'postgresql':
            connection.execute(text('ALTER TABLE clients ALTER COLUMN name TYPE VARCHAR(30)'))
            return

        if dialect == 'mysql':
            connection.execute(text('ALTER TABLE clients MODIFY COLUMN name VARCHAR(30)'))
            return


def _ensure_invoice_item_columns() -> None:
    expected_columns: dict[str, str] = {
        'hsn_sac': 'VARCHAR(8)',
    }

    inspector = inspect(engine)
    if 'invoice_items' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('invoice_items')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(
                text(f'ALTER TABLE invoice_items ADD COLUMN {column_name} {column_type}')
            )


def _ensure_invoice_columns() -> None:
    expected_columns: dict[str, str] = {
        'place_of_supply': 'VARCHAR(64)',
        'place_of_supply_code': 'VARCHAR(2)',
    }

    inspector = inspect(engine)
    if 'invoices' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('invoices')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(
                text(f'ALTER TABLE invoices ADD COLUMN {column_name} {column_type}')
            )


def _ensure_invoice_gst_number_column_length() -> None:
    inspector = inspect(engine)
    if 'invoices' not in inspector.get_table_names():
        return

    gst_column = next(
        (column for column in inspector.get_columns('invoices') if column.get('name') == 'gst_number'),
        None,
    )
    if gst_column is None:
        return

    current_length = getattr(gst_column.get('type'), 'length', None)
    if isinstance(current_length, int) and current_length >= 100:
        return

    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == 'postgresql':
            connection.execute(text('ALTER TABLE invoices ALTER COLUMN gst_number TYPE VARCHAR(100)'))
            return
        if dialect == 'mysql':
            connection.execute(text('ALTER TABLE invoices MODIFY COLUMN gst_number VARCHAR(100)'))
            return


def _ensure_invoice_unique_constraint() -> None:
    inspector = inspect(engine)
    if 'invoices' not in inspector.get_table_names():
        return

    existing_indexes = {index['name'] for index in inspector.get_indexes('invoices')}
    if 'uq_invoices_owner_invoice_number' in existing_indexes:
        return

    with engine.begin() as connection:
        duplicate_row = connection.execute(
            text(
                'SELECT owner_id, invoice_number, COUNT(*) AS duplicate_count '
                'FROM invoices '
                'GROUP BY owner_id, invoice_number '
                'HAVING COUNT(*) > 1 '
                'LIMIT 1'
            )
        ).first()
        if duplicate_row:
            logger.warning(
                'Skipping invoice unique index creation due to duplicate invoice numbers. '
                'owner_id=%s invoice_number=%s duplicates=%s',
                duplicate_row[0],
                duplicate_row[1],
                duplicate_row[2],
            )
            return

        connection.execute(
            text(
                'CREATE UNIQUE INDEX uq_invoices_owner_invoice_number '
                'ON invoices (owner_id, invoice_number)'
            )
        )


def _ensure_non_gst_challan_unique_constraint() -> None:
    inspector = inspect(engine)
    if 'non_gst_challans' not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        dialect = engine.dialect.name

        if dialect == 'postgresql':
            connection.execute(
                text('ALTER TABLE non_gst_challans DROP CONSTRAINT IF EXISTS uq_non_gst_challans_owner_number')
            )
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX IF NOT EXISTS uq_non_gst_challans_owner_client_number '
                    'ON non_gst_challans (owner_id, client_id, challan_number)'
                )
            )
            return

        if dialect == 'sqlite':
            connection.execute(text('DROP INDEX IF EXISTS uq_non_gst_challans_owner_number'))
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX IF NOT EXISTS uq_non_gst_challans_owner_client_number '
                    'ON non_gst_challans (owner_id, client_id, challan_number)'
                )
            )
            return

        try:
            connection.execute(
                text('ALTER TABLE non_gst_challans DROP CONSTRAINT IF EXISTS uq_non_gst_challans_owner_number')
            )
        except Exception:
            pass
        connection.execute(
            text(
                'CREATE UNIQUE INDEX IF NOT EXISTS uq_non_gst_challans_owner_client_number '
                'ON non_gst_challans (owner_id, client_id, challan_number)'
            )
        )


def _ensure_non_gst_challan_sequence_numbers() -> None:
    inspector = inspect(engine)
    if 'non_gst_challans' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('non_gst_challans')}
    existing_indexes = {index['name'] for index in inspector.get_indexes('non_gst_challans')}

    with engine.begin() as connection:
        if 'sequence_number' not in existing_columns:
            connection.execute(text('ALTER TABLE non_gst_challans ADD COLUMN sequence_number INTEGER'))

        ordered_rows = connection.execute(
            text(
                'SELECT id, owner_id, sequence_number '
                'FROM non_gst_challans '
                'ORDER BY owner_id ASC, created_at ASC, challan_date ASC, id ASC'
            )
        ).fetchall()

        counters: dict[str, int] = {}
        for row_id, owner_id, sequence_number in ordered_rows:
            if owner_id not in counters:
                counters[owner_id] = 0

            counters[owner_id] += 1
            expected_sequence = counters[owner_id]
            if sequence_number == expected_sequence:
                continue

            connection.execute(
                text(
                    'UPDATE non_gst_challans '
                    'SET sequence_number = :sequence_number '
                    'WHERE id = :row_id'
                ),
                {'sequence_number': expected_sequence, 'row_id': row_id},
            )

        if 'uq_non_gst_challans_owner_sequence_number' in existing_indexes:
            return

        dialect = engine.dialect.name
        if dialect in {'postgresql', 'sqlite'}:
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX IF NOT EXISTS uq_non_gst_challans_owner_sequence_number '
                    'ON non_gst_challans (owner_id, sequence_number)'
                )
            )
            return

        try:
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX uq_non_gst_challans_owner_sequence_number '
                    'ON non_gst_challans (owner_id, sequence_number)'
                )
            )
        except Exception:
            pass


def _ensure_user_columns() -> None:
    expected_columns: dict[str, str] = {
        'notifications_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
    }

    inspector = inspect(engine)
    if 'users' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('users')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(text(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}'))


def _ensure_default_admin() -> None:
    session = SessionLocal()
    try:
        admin_user = ensure_default_admin_user(session)
        if admin_user is None:
            return
        logger.info('Default admin user is ready for %s', admin_user.email)
    finally:
        session.close()


@app.on_event('startup')
def on_startup() -> None:
    _validate_security_configuration()
    Base.metadata.create_all(bind=engine)
    _ensure_personal_details_columns()
    _ensure_clients_columns()
    _ensure_clients_name_column_length()
    _ensure_invoice_item_columns()
    _ensure_invoice_columns()
    _ensure_invoice_gst_number_column_length()
    _ensure_invoice_unique_constraint()
    _ensure_non_gst_challan_unique_constraint()
    _ensure_non_gst_challan_sequence_numbers()
    _ensure_user_columns()
    _ensure_default_admin()


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


uploads_path = _resolved_uploads_path()
uploads_path.mkdir(parents=True, exist_ok=True)
if settings.serve_public_uploads:
    app.mount('/uploads', StaticFiles(directory=str(uploads_path)), name='uploads')
