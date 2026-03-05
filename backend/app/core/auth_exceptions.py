from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from app.core.errors import error_payload, error_response


class AuthException(Exception):
    """Custom auth exception with structured error payload."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
        error_code: str = 'AUTH_ERROR',
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.headers = headers or {}
        super().__init__(message)


def auth_error_payload(message: str, error_code: str = 'AUTH_ERROR') -> dict[str, Any]:
    return error_payload(code=error_code, message=message)


def auth_error_response(
    message: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    error_code: str = 'AUTH_ERROR',
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return error_response(
        status_code=status_code,
        message=message,
        code=error_code,
        headers=headers or {},
    )
