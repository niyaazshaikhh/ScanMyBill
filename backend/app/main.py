import logging
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from requests import exceptions as request_exceptions
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.api import api_router
from app.core.auth_exceptions import AuthException
from app.core.auth_middleware import AuthSessionMiddleware
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.errors import error_response
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestLoggingMiddleware,
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
app.router.redirect_slashes = False

DEFAULT_LOCAL_TRUSTED_HOSTS = ['localhost', '127.0.0.1', '*.localhost']
DEFAULT_PRODUCTION_TRUSTED_HOSTS = [
    'api.scanmybill.xyz',
    'app.scanmybill.xyz',
    'scanmybill-backend.kindriver-b1141450.centralindia.azurecontainerapps.io',
]
DEFAULT_LOCAL_CORS_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']
DEFAULT_PRODUCTION_CORS_ORIGINS = ['https://app.scanmybill.xyz']


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().rstrip('/') for item in value.split(',') if item.strip()]


def _as_list(value: list[str] | str | None) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.split(',')
    else:
        raw_items = []
    return [item.strip().rstrip('/') for item in raw_items if isinstance(item, str) and item.strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _resolve_trusted_hosts() -> list[str]:
    env_hosts = _split_csv(os.getenv('TRUSTED_HOSTS'))
    configured_hosts = _as_list(settings.trusted_hosts)
    hosts = env_hosts or configured_hosts

    baseline_hosts = DEFAULT_PRODUCTION_TRUSTED_HOSTS if settings.is_production else DEFAULT_LOCAL_TRUSTED_HOSTS
    missing_hosts = [host for host in baseline_hosts if host not in hosts]
    if missing_hosts:
        logger.warning(
            'Appending baseline TRUSTED_HOSTS entries to avoid host-header rejections: %s',
            ', '.join(missing_hosts),
        )
        hosts.extend(missing_hosts)
    return _unique(hosts)


def _resolve_cors_origins() -> list[str]:
    env_origins = _split_csv(os.getenv('CORS_ORIGINS'))
    configured_origins = _as_list(settings.cors_origins)
    origins = env_origins or configured_origins

    baseline_origins = DEFAULT_PRODUCTION_CORS_ORIGINS if settings.is_production else DEFAULT_LOCAL_CORS_ORIGINS
    missing_origins = [origin for origin in baseline_origins if origin not in origins]
    if missing_origins:
        logger.info(
            'Appending baseline CORS origins: %s',
            ', '.join(missing_origins),
        )
        origins.extend(missing_origins)
    return _unique(origins)


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
        if settings.debug:
            issues.append('DEBUG must be false in production.')
        if settings.enable_docs:
            issues.append('ENABLE_DOCS must be false in production.')
        if not settings.cookie_secure:
            issues.append('COOKIE_SECURE must be true in production.')
        if settings.expose_password_reset_token:
            issues.append('EXPOSE_PASSWORD_RESET_TOKEN must be false in production.')
        if '*' in settings.cors_origins:
            issues.append("CORS_ORIGINS cannot include '*' in production.")
        if settings.seed_default_admin:
            issues.append('SEED_DEFAULT_ADMIN must be false in production.')
        # When DATABASE_URL_OVERRIDE is provided (managed DB/cloud), POSTGRES_* values may be placeholders.
        if not settings.database_url_override and settings.postgres_password.strip().lower() in {'', 'postgres'}:
            issues.append('POSTGRES_PASSWORD must be configured with a strong value in production.')
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


app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthSessionMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
cors_origins = _resolve_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials='*' not in cors_origins,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['*'],
    expose_headers=['X-Access-Token', 'X-Token-Refreshed'],
)

trusted_hosts = _resolve_trusted_hosts()
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

if settings.trust_proxy_headers:
    # Trust proxy-provided scheme/client metadata when running behind ingress.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts='*')

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> JSONResponse:
    return error_response(
        status_code=exc.status_code,
        message=exc.message,
        code=exc.error_code,
        request_id=getattr(request.state, 'request_id', None),
        headers=exc.headers,
    )


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', None)
    detail = exc.detail
    error_code = None
    message: str | None = None

    if isinstance(detail, dict):
        nested_error = detail.get('error')
        if isinstance(nested_error, dict):
            nested_code = nested_error.get('code')
            nested_message = nested_error.get('message')
            if isinstance(nested_code, str) and nested_code:
                error_code = nested_code
            if isinstance(nested_message, str) and nested_message:
                message = nested_message
        if message is None:
            if isinstance(detail.get('message'), str):
                message = detail.get('message')
            elif isinstance(detail.get('detail'), str):
                message = detail.get('detail')
        if error_code is None and isinstance(detail.get('error_code'), str):
            error_code = detail.get('error_code')
    elif isinstance(detail, str):
        message = detail

    return error_response(
        status_code=exc.status_code,
        message=message,
        code=error_code,
        request_id=request_id,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.warning(
        'Validation failed request_id=%s path=%s errors=%s',
        request_id,
        request.url.path,
        exc.errors(),
    )
    return error_response(
        status_code=422,
        code='VALIDATION_ERROR',
        message='Invalid request payload.',
        request_id=request_id if request_id != 'n/a' else None,
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Database exception request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        status_code=500,
        code='DATABASE_ERROR',
        message='A database error occurred. Please try again.',
        request_id=request_id if request_id != 'n/a' else None,
    )


@app.exception_handler(request_exceptions.Timeout)
async def upstream_timeout_handler(request: Request, exc: request_exceptions.Timeout) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Upstream timeout request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        status_code=504,
        code='UPSTREAM_TIMEOUT',
        message='Upstream service timed out. Please try again.',
        request_id=request_id if request_id != 'n/a' else None,
    )


@app.exception_handler(request_exceptions.ConnectionError)
async def upstream_network_handler(request: Request, exc: request_exceptions.ConnectionError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Upstream network failure request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        status_code=502,
        code='UPSTREAM_NETWORK_ERROR',
        message='Could not reach upstream service.',
        request_id=request_id if request_id != 'n/a' else None,
    )


@app.exception_handler(TimeoutError)
async def timeout_exception_handler(request: Request, exc: TimeoutError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Internal timeout request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        status_code=504,
        code='TIMEOUT',
        message='Request timed out.',
        request_id=request_id if request_id != 'n/a' else None,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', 'n/a')
    logger.exception(
        'Unhandled exception request_id=%s method=%s path=%s',
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        status_code=500,
        code='INTERNAL_SERVER_ERROR',
        message='Internal server error.',
        request_id=request_id if request_id != 'n/a' else None,
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

    def _financial_year_start_from_value(value: object) -> int | None:
        if isinstance(value, date):
            return value.year if value.month >= 4 else value.year - 1
        if isinstance(value, str):
            normalized = value.strip()
            if len(normalized) >= 10:
                normalized = normalized[:10]
            try:
                parsed_date = date.fromisoformat(normalized)
            except ValueError:
                return None
            return parsed_date.year if parsed_date.month >= 4 else parsed_date.year - 1
        return None

    with engine.begin() as connection:
        if 'sequence_number' not in existing_columns:
            connection.execute(text('ALTER TABLE non_gst_challans ADD COLUMN sequence_number INTEGER'))
        if 'financial_year_start' not in existing_columns:
            connection.execute(text('ALTER TABLE non_gst_challans ADD COLUMN financial_year_start INTEGER'))

        ordered_rows = connection.execute(
            text(
                'SELECT id, owner_id, challan_date, financial_year_start, sequence_number '
                'FROM non_gst_challans '
                'ORDER BY owner_id ASC, challan_date ASC, created_at ASC, id ASC'
            )
        ).fetchall()

        counters: dict[tuple[str, int], int] = {}
        for row_id, owner_id, challan_date, financial_year_start, sequence_number in ordered_rows:
            resolved_financial_year_start: int | None
            if financial_year_start is not None:
                try:
                    resolved_financial_year_start = int(financial_year_start)
                except (TypeError, ValueError):
                    resolved_financial_year_start = _financial_year_start_from_value(challan_date)
            else:
                resolved_financial_year_start = _financial_year_start_from_value(challan_date)
            if resolved_financial_year_start is None:
                continue

            key = (owner_id, resolved_financial_year_start)
            counters[key] = counters.get(key, 0) + 1
            expected_sequence = counters[key]
            if (
                sequence_number == expected_sequence
                and financial_year_start == resolved_financial_year_start
            ):
                continue

            connection.execute(
                text(
                    'UPDATE non_gst_challans '
                    'SET financial_year_start = :financial_year_start, sequence_number = :sequence_number '
                    'WHERE id = :row_id'
                ),
                {
                    'financial_year_start': resolved_financial_year_start,
                    'sequence_number': expected_sequence,
                    'row_id': row_id,
                },
            )

        dialect = engine.dialect.name
        if dialect == 'postgresql':
            connection.execute(
                text(
                    'ALTER TABLE non_gst_challans DROP CONSTRAINT IF EXISTS '
                    'uq_non_gst_challans_owner_sequence_number'
                )
            )
            connection.execute(
                text(
                    'ALTER TABLE non_gst_challans DROP CONSTRAINT IF EXISTS '
                    'uq_non_gst_challans_owner_financial_year_sequence_number'
                )
            )
            connection.execute(text('DROP INDEX IF EXISTS uq_non_gst_challans_owner_sequence_number'))
            connection.execute(text('DROP INDEX IF EXISTS uq_non_gst_challans_owner_financial_year_sequence_number'))
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX IF NOT EXISTS '
                    'uq_non_gst_challans_owner_financial_year_sequence_number '
                    'ON non_gst_challans (owner_id, financial_year_start, sequence_number)'
                )
            )
            return

        if dialect == 'sqlite':
            connection.execute(text('DROP INDEX IF EXISTS uq_non_gst_challans_owner_sequence_number'))
            connection.execute(text('DROP INDEX IF EXISTS uq_non_gst_challans_owner_financial_year_sequence_number'))
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX IF NOT EXISTS '
                    'uq_non_gst_challans_owner_financial_year_sequence_number '
                    'ON non_gst_challans (owner_id, financial_year_start, sequence_number)'
                )
            )
            return

        try:
            connection.execute(
                text(
                    'ALTER TABLE non_gst_challans DROP CONSTRAINT '
                    'uq_non_gst_challans_owner_sequence_number'
                )
            )
        except Exception:
            pass
        try:
            connection.execute(
                text(
                    'ALTER TABLE non_gst_challans DROP CONSTRAINT '
                    'uq_non_gst_challans_owner_financial_year_sequence_number'
                )
            )
        except Exception:
            pass
        try:
            connection.execute(text('DROP INDEX uq_non_gst_challans_owner_sequence_number ON non_gst_challans'))
        except Exception:
            pass
        try:
            connection.execute(text('DROP INDEX uq_non_gst_challans_owner_financial_year_sequence_number ON non_gst_challans'))
        except Exception:
            pass
        try:
            connection.execute(
                text(
                    'CREATE UNIQUE INDEX uq_non_gst_challans_owner_financial_year_sequence_number '
                    'ON non_gst_challans (owner_id, financial_year_start, sequence_number)'
                )
            )
        except Exception:
            pass


def _ensure_user_columns() -> None:
    inspector = inspect(engine)
    if 'users' not in inspector.get_table_names():
        return

    dialect = engine.dialect.name
    timestamp_type = 'TIMESTAMP WITH TIME ZONE' if dialect == 'postgresql' else 'DATETIME'
    expected_columns: dict[str, str] = {
        'notifications_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'failed_login_attempts': 'INTEGER NOT NULL DEFAULT 0',
        'account_locked_until': timestamp_type,
        'last_failed_login_at': timestamp_type,
    }

    existing_columns = {column['name'] for column in inspector.get_columns('users')}
    missing_columns = [column for column in expected_columns if column not in existing_columns]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = expected_columns[column_name]
            connection.execute(text(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}'))


def _ensure_newsletter_subscriber_columns() -> None:
    inspector = inspect(engine)
    if 'newsletter_subscribers' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('newsletter_subscribers')}
    dialect = engine.dialect.name
    timestamp_type = 'TIMESTAMP WITH TIME ZONE' if dialect == 'postgresql' else 'DATETIME'

    with engine.begin() as connection:
        if 'subscribed_at' not in existing_columns:
            connection.execute(
                text(
                    f'ALTER TABLE newsletter_subscribers '
                    f'ADD COLUMN subscribed_at {timestamp_type}'
                )
            )

            if 'created_at' in existing_columns:
                connection.execute(
                    text(
                        'UPDATE newsletter_subscribers '
                        'SET subscribed_at = created_at '
                        'WHERE subscribed_at IS NULL'
                    )
                )

            now_expression = 'NOW()' if dialect == 'postgresql' else 'CURRENT_TIMESTAMP'
            connection.execute(
                text(
                    'UPDATE newsletter_subscribers '
                    f'SET subscribed_at = {now_expression} '
                    'WHERE subscribed_at IS NULL'
                )
            )
        else:
            now_expression = 'NOW()' if dialect == 'postgresql' else 'CURRENT_TIMESTAMP'
            connection.execute(
                text(
                    'UPDATE newsletter_subscribers '
                    f'SET subscribed_at = {now_expression} '
                    'WHERE subscribed_at IS NULL'
                )
            )

        if 'unsubscribed_at' not in existing_columns:
            connection.execute(
                text(
                    f'ALTER TABLE newsletter_subscribers '
                    f'ADD COLUMN unsubscribed_at {timestamp_type}'
                )
            )

        if dialect == 'postgresql':
            connection.execute(
                text(
                    'ALTER TABLE newsletter_subscribers '
                    'ALTER COLUMN subscribed_at SET DEFAULT NOW()'
                )
            )
            connection.execute(
                text(
                    'ALTER TABLE newsletter_subscribers '
                    'ALTER COLUMN subscribed_at SET NOT NULL'
                )
            )


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
    _ensure_newsletter_subscriber_columns()
    _ensure_default_admin()


def _database_ready() -> bool:
    session = SessionLocal()
    try:
        session.execute(text('SELECT 1'))
        return True
    except Exception:
        logger.exception('Database readiness probe failed')
        return False
    finally:
        session.close()


@app.get('/health/live')
def health_live() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/health/ready')
def health_ready() -> JSONResponse:
    db_ready = _database_ready()
    if not db_ready:
        return JSONResponse(
            status_code=503,
            content={'status': 'degraded', 'database': 'unavailable'},
        )
    return JSONResponse(status_code=200, content={'status': 'ok', 'database': 'ready'})


@app.get('/healthz')
@app.get('/healthz/', include_in_schema=False)
def healthz() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/health', include_in_schema=False)
@app.get('/health/', include_in_schema=False)
def health() -> dict[str, str]:
    return {'status': 'ok'}


uploads_path = _resolved_uploads_path()
uploads_path.mkdir(parents=True, exist_ok=True)
if settings.serve_public_uploads:
    app.mount('/uploads', StaticFiles(directory=str(uploads_path)), name='uploads')
