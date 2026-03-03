from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'ScanMyBill.in API'
    api_v1_prefix: str = '/api/v1'
    environment: Literal['development', 'staging', 'production'] = 'development'
    debug: bool = False
    enable_docs: bool = True
    log_level: str = 'INFO'
    trust_proxy_headers: bool = True
    enforce_https: bool = False
    trusted_hosts: list[str] | str = ['localhost', '127.0.0.1', '*.localhost']

    postgres_server: str = 'localhost'
    postgres_port: int = 5432
    postgres_user: str = 'postgres'
    postgres_password: str = 'postgres'
    postgres_db: str = 'scanmybill'
    database_url_override: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    secret_key: str = 'change-this-in-production'
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    session_inactivity_timeout_minutes: int = 30
    access_token_refresh_threshold_minutes: int = 3
    jwt_algorithm: str = 'HS256'
    cookie_secure: bool = False
    cookie_samesite: str = 'lax'
    cookie_domain: str | None = None

    cors_origins: list[str] | str = ['http://localhost:3000']
    security_csp: str = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    hsts_max_age_seconds: int = 31536000
    request_max_mb: int = 25
    enable_rate_limiting: bool = True
    rate_limit_default_per_minute: int = 240
    rate_limit_auth_per_minute: int = 20
    rate_limit_invoice_pdf_per_minute: int = 60

    storage_backend: str = 'local'
    uploads_dir: str = 'uploads'
    max_upload_mb: int = 10
    serve_public_uploads: bool = False

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = 'ap-south-1'
    aws_s3_bucket: str | None = None

    google_client_id: str | None = None
    google_client_ids: list[str] | str | None = None
    next_public_google_client_id: str | None = None

    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_plan_id: str | None = None
    razorpay_plan_ids: list[str] | str | None = None
    razorpay_webhook_secret: str | None = None
    expose_password_reset_token: bool = True

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override.strip()
        return (
            f'postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}'
        )

    @property
    def is_production(self) -> bool:
        return self.environment == 'production'

    @property
    def docs_enabled(self) -> bool:
        return self.enable_docs and not self.is_production

    @property
    def max_request_bytes(self) -> int:
        return max(1, self.request_max_mb) * 1024 * 1024

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('trusted_hosts', mode='before')
    @classmethod
    def parse_trusted_hosts(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('google_client_ids', mode='before')
    @classmethod
    def parse_google_client_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('razorpay_plan_ids', mode='before')
    @classmethod
    def parse_razorpay_plan_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('log_level', mode='before')
    @classmethod
    def parse_log_level(cls, value: Any) -> str:
        if not isinstance(value, str):
            return 'INFO'
        normalized = value.strip().upper()
        if normalized in {'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'}:
            return normalized
        return 'INFO'

    @field_validator('cookie_samesite', mode='before')
    @classmethod
    def parse_cookie_samesite(cls, value: Any) -> str:
        if not isinstance(value, str):
            return 'lax'
        normalized = value.strip().lower()
        if normalized in {'lax', 'strict', 'none'}:
            return normalized
        return 'lax'

    @field_validator('jwt_algorithm', mode='before')
    @classmethod
    def parse_jwt_algorithm(cls, value: Any) -> str:
        if not isinstance(value, str):
            return 'HS256'
        normalized = value.strip().upper()
        if normalized in {'HS256', 'HS384', 'HS512'}:
            return normalized
        return 'HS256'

    @property
    def allowed_google_client_ids(self) -> list[str]:
        values: list[str] = []

        if isinstance(self.google_client_ids, list):
            values.extend(self.google_client_ids)
        elif isinstance(self.google_client_ids, str):
            values.extend([item.strip() for item in self.google_client_ids.split(',') if item.strip()])

        if self.google_client_id:
            values.extend([item.strip() for item in self.google_client_id.split(',') if item.strip()])

        if self.next_public_google_client_id:
            values.append(self.next_public_google_client_id.strip())

        # Preserve order while removing duplicates.
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique

    @property
    def allowed_razorpay_plan_ids(self) -> list[str]:
        values: list[str] = []

        if isinstance(self.razorpay_plan_ids, list):
            values.extend(self.razorpay_plan_ids)
        elif isinstance(self.razorpay_plan_ids, str):
            values.extend([item.strip() for item in self.razorpay_plan_ids.split(',') if item.strip()])

        if self.razorpay_plan_id:
            values.extend([item.strip() for item in self.razorpay_plan_id.split(',') if item.strip()])

        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
