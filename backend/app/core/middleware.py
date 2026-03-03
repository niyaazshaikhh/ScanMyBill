from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


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
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={'detail': 'Invalid Content-Length header'},
                )

            if payload_size > settings.max_request_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={'detail': f'Request body exceeds {settings.request_max_mb}MB limit'},
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

        if path.endswith('/auth/login') or path.endswith('/auth/refresh'):
            return _RateLimitPolicy('auth', max(1, settings.rate_limit_auth_per_minute))

        if path.endswith('/invoices/create') or (path.endswith('/pdf') and '/invoices/' in path):
            return _RateLimitPolicy('invoice_pdf', max(1, settings.rate_limit_invoice_pdf_per_minute))

        return _RateLimitPolicy('default', max(1, settings.rate_limit_default_per_minute))

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        if not settings.enable_rate_limiting or request.method == 'OPTIONS' or request.url.path == '/health':
            return await call_next(request)

        policy = self._policy_for_request(request)
        identifier = _client_ip(request)
        key = f'{policy.name}:{identifier}'

        allowed, retry_after = self._limiter.allow(key, limit=policy.limit_per_minute)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={'detail': 'Rate limit exceeded. Please retry shortly.'},
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
