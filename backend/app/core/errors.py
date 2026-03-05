from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

DEFAULT_ERROR_MESSAGES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: 'Invalid request.',
    status.HTTP_401_UNAUTHORIZED: 'Authentication required.',
    status.HTTP_403_FORBIDDEN: 'You do not have permission to perform this action.',
    status.HTTP_404_NOT_FOUND: 'Requested resource was not found.',
    status.HTTP_408_REQUEST_TIMEOUT: 'Request timed out.',
    status.HTTP_409_CONFLICT: 'Request could not be completed due to a conflict.',
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: 'Uploaded payload is too large.',
    status.HTTP_422_UNPROCESSABLE_ENTITY: 'Invalid request payload.',
    status.HTTP_429_TOO_MANY_REQUESTS: 'Too many requests. Please try again later.',
    status.HTTP_500_INTERNAL_SERVER_ERROR: 'Internal server error.',
    status.HTTP_502_BAD_GATEWAY: 'Upstream service error.',
    status.HTTP_503_SERVICE_UNAVAILABLE: 'Service unavailable.',
    status.HTTP_504_GATEWAY_TIMEOUT: 'Upstream service timeout.',
}

DEFAULT_ERROR_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: 'BAD_REQUEST',
    status.HTTP_401_UNAUTHORIZED: 'UNAUTHORIZED',
    status.HTTP_403_FORBIDDEN: 'FORBIDDEN',
    status.HTTP_404_NOT_FOUND: 'NOT_FOUND',
    status.HTTP_408_REQUEST_TIMEOUT: 'REQUEST_TIMEOUT',
    status.HTTP_409_CONFLICT: 'CONFLICT',
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: 'PAYLOAD_TOO_LARGE',
    status.HTTP_422_UNPROCESSABLE_ENTITY: 'VALIDATION_ERROR',
    status.HTTP_429_TOO_MANY_REQUESTS: 'RATE_LIMIT_EXCEEDED',
    status.HTTP_500_INTERNAL_SERVER_ERROR: 'INTERNAL_SERVER_ERROR',
    status.HTTP_502_BAD_GATEWAY: 'UPSTREAM_SERVICE_ERROR',
    status.HTTP_503_SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
    status.HTTP_504_GATEWAY_TIMEOUT: 'UPSTREAM_TIMEOUT',
}


def error_payload(
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        'success': False,
        'error': {
            'code': code,
            'message': message,
        },
    }


def status_code_to_error_code(status_code: int) -> str:
    return DEFAULT_ERROR_CODES.get(status_code, 'REQUEST_FAILED')


def status_code_to_default_message(status_code: int) -> str:
    return DEFAULT_ERROR_MESSAGES.get(status_code, 'Request failed.')


def error_response(
    *,
    status_code: int,
    message: str | None = None,
    code: str | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = error_payload(
        code=code or status_code_to_error_code(status_code),
        message=message or status_code_to_default_message(status_code),
    )
    response_headers = dict(headers or {})
    if request_id:
        response_headers.setdefault('X-Request-ID', request_id)
    return JSONResponse(status_code=status_code, content=payload, headers=response_headers or None)

