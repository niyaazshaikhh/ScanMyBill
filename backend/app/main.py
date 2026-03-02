from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api.v1.api import api_router
from app.core.auth_exceptions import AuthException, auth_error_payload
from app.core.auth_middleware import AuthSessionMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403

app = FastAPI(
    title=settings.app_name,
    version='1.0.0',
    docs_url='/docs',
    redoc_url='/redoc',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=['X-Access-Token', 'X-Token-Refreshed'],
)
app.add_middleware(AuthSessionMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(AuthException)
async def auth_exception_handler(_: Request, exc: AuthException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=auth_error_payload(message=exc.message, error_code=exc.error_code),
        headers=exc.headers,
    )


def _ensure_personal_details_columns() -> None:
    expected_columns: dict[str, str] = {
        'address': 'VARCHAR(115)',
        'state_name': 'VARCHAR(64)',
        'state_code': 'VARCHAR(2)',
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


@app.on_event('startup')
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_personal_details_columns()
    _ensure_clients_columns()
    _ensure_invoice_item_columns()
    _ensure_invoice_columns()


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


uploads_path = Path(settings.uploads_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount('/uploads', StaticFiles(directory=str(uploads_path)), name='uploads')
