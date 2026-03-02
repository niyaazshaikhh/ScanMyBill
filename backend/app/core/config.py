from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'ScanMyBill.in API'
    api_v1_prefix: str = '/api/v1'

    postgres_server: str = 'localhost'
    postgres_port: int = 5432
    postgres_user: str = 'postgres'
    postgres_password: str = 'postgres'
    postgres_db: str = 'scanmybill'

    secret_key: str = 'change-this-in-production'
    access_token_expire_minutes: int = 60 * 24 * 7
    jwt_algorithm: str = 'HS256'

    cors_origins: list[str] | str = ['http://localhost:3000']

    storage_backend: str = 'local'
    uploads_dir: str = 'uploads'
    max_upload_mb: int = 10

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

    @property
    def database_url(self) -> str:
        return (
            f'postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}'
        )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
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
