from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse


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
    return {
        'success': False,
        'message': message,
        'error_code': error_code,
    }


def auth_error_response(
    message: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    error_code: str = 'AUTH_ERROR',
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=auth_error_payload(message=message, error_code=error_code),
        headers=headers or {},
    )
