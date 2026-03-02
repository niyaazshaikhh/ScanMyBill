from collections.abc import Awaitable, Callable

from fastapi import Request, status
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import or_, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.auth_exceptions import AuthException, auth_error_response
from app.core.database import SessionLocal
from app.core.security import decode_token, hash_token
from app.models.revoked_token import RevokedToken
from app.models.token_blacklist import TokenBlacklist


class AuthSessionMiddleware(BaseHTTPMiddleware):
    """Validate bearer session tokens and normalize auth errors."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == 'OPTIONS':
            return await call_next(request)

        auth_header = request.headers.get('Authorization')
        if auth_header:
            if not auth_header.lower().startswith('bearer '):
                return auth_error_response(
                    message='Invalid authorization header',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

            token = auth_header.split(' ', 1)[1].strip()
            if not token:
                return auth_error_response(
                    message='Authorization token is missing',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

            try:
                payload = decode_token(token)
            except ExpiredSignatureError:
                return auth_error_response(
                    message='Access token has expired',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )
            except JWTError:
                return auth_error_response(
                    message='Invalid token',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

            token_type = payload.get('type')
            if token_type not in (None, 'access'):
                return auth_error_response(
                    message='Invalid token type',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

            jti = payload.get('jti')
            if not isinstance(jti, str) or not jti:
                return auth_error_response(
                    message='Invalid token',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

            token_hash = hash_token(token)
            with SessionLocal() as db:
                blacklisted = db.scalar(
                    select(TokenBlacklist.id).where(TokenBlacklist.token == jti)
                )
                revoked = db.scalar(
                    select(RevokedToken.id).where(
                        or_(RevokedToken.jti == jti, RevokedToken.token_hash == token_hash)
                    )
                )

            if blacklisted or revoked:
                return auth_error_response(
                    message='Token has been revoked',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={'WWW-Authenticate': 'Bearer'},
                )

        try:
            return await call_next(request)
        except AuthException as exc:
            return auth_error_response(
                message=exc.message,
                status_code=exc.status_code,
                error_code=exc.error_code,
                headers=exc.headers,
            )
        except ExpiredSignatureError:
            return auth_error_response(
                message='Token has expired',
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        except JWTError:
            return auth_error_response(
                message='Invalid token',
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
