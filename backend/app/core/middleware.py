from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.errors import error_response

logger = logging.getLogger('scanmybill.request')


def _client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            first = forwarded_for.split(',')[0].strip()
            if first:
                return first
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return 'unknown'


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        request_id = request.headers.get('X-Request-ID') or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers.setdefault('X-Request-ID', request_id)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        started_at = time.perf_counter()
        response: Response | None = None
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            request_id = getattr(request.state, 'request_id', 'n/a')
            user_id = getattr(request.state, 'auth_user_id', None)
            logger.info(
                'request_completed timestamp=%s request_id=%s user_id=%s endpoint=%s method=%s status_code=%s execution_time_ms=%.2f',
                datetime.now(timezone.utc).isoformat(),
                request_id,
                user_id or '-',
                request.url.path,
                request.method,
                status_code,
                elapsed_ms,
            )


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                payload_size = int(content_length)
            except ValueError:
                return error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='INVALID_CONTENT_LENGTH',
                    message='Invalid Content-Length header.',
                    request_id=getattr(request.state, 'request_id', None),
                )

            if payload_size > settings.max_request_bytes:
                return error_response(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    code='REQUEST_BODY_TOO_LARGE',
                    message=f'Request body exceeds {settings.request_max_mb}MB limit.',
                    request_id=getattr(request.state, 'request_id', None),
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('X-XSS-Protection', '1; mode=block')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
        response.headers.setdefault('Content-Security-Policy', settings.security_csp)

        if settings.enforce_https or settings.is_production or request.url.scheme == 'https':
            response.headers.setdefault(
                'Strict-Transport-Security',
                f'max-age={settings.hsts_max_age_seconds}; includeSubDomains',
            )

        return response


@dataclass(frozen=True)
class _RateLimitPolicy:
    name: str
    limit_per_minute: int


class _SlidingWindowRateLimiter:
    def __init__(self, *, max_keys: int = 100_000) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._max_keys = max_keys

    def allow(self, key: str, *, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._events.get(key)
            if bucket is None:
                bucket = deque()
                self._events[key] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                oldest = bucket[0]
                retry_after = max(1, int(window_seconds - (now - oldest)))
                return False, retry_after

            bucket.append(now)
            if len(self._events) > self._max_keys:
                self._cleanup(cutoff)
            return True, 0

    def _cleanup(self, cutoff: float) -> None:
        for key in list(self._events.keys()):
            bucket = self._events.get(key)
            if bucket is None:
                continue
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                self._events.pop(key, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._limiter = _SlidingWindowRateLimiter()

    def _policy_for_request(self, request: Request) -> _RateLimitPolicy:
        path = request.url.path

        if path.endswith('/auth/login') or path.endswith('/auth/admin/login'):
            return _RateLimitPolicy('login', max(1, settings.rate_limit_login_per_minute))

        if '/auth/' in path:
            return _RateLimitPolicy('auth', max(1, settings.rate_limit_auth_per_minute))

        if (
            path.endswith('/invoices/create')
            or path.endswith('/delivery-challans/create')
            or (path.endswith('/pdf') and ('/invoices/' in path or '/delivery-challans/' in path))
        ):
            return _RateLimitPolicy('invoice_pdf', max(1, settings.rate_limit_invoice_pdf_per_minute))

        return _RateLimitPolicy('default', max(1, settings.rate_limit_default_per_minute))

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        if not settings.enable_rate_limiting or request.method == 'OPTIONS' or request.url.path in {
            '/health',
            '/health/live',
            '/health/ready',
        }:
            return await call_next(request)

        policy = self._policy_for_request(request)
        auth_user_id = getattr(request.state, 'auth_user_id', None)
        identifier = f'user:{auth_user_id}' if isinstance(auth_user_id, str) and auth_user_id else f'ip:{_client_ip(request)}'
        key = f'{policy.name}:{identifier}'

        allowed, retry_after = self._limiter.allow(key, limit=policy.limit_per_minute)
        if not allowed:
            return error_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code='RATE_LIMIT_EXCEEDED',
                message='Rate limit exceeded. Please retry shortly.',
                request_id=getattr(request.state, 'request_id', None),
                headers={
                    'Retry-After': str(retry_after),
                    'X-RateLimit-Policy': policy.name,
                    'X-RateLimit-Limit': str(policy.limit_per_minute),
                },
            )

        response = await call_next(request)
        response.headers.setdefault('X-RateLimit-Policy', policy.name)
        response.headers.setdefault('X-RateLimit-Limit', str(policy.limit_per_minute))
        return response
