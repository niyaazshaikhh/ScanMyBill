from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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


@app.on_event('startup')
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


uploads_path = Path(settings.uploads_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount('/uploads', StaticFiles(directory=str(uploads_path)), name='uploads')
