from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _masked_preview(value: str | None) -> str | None:
    cleaned = _normalize(value)
    if not cleaned:
        return None
    if len(cleaned) <= 6:
        return '*' * len(cleaned)
    return f'{cleaned[:3]}***{cleaned[-3:]}'


@router.get('/ai-config')
def ai_config_debug(
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    del current_user

    endpoint = _normalize(settings.azure_openai_endpoint)
    deployment = _normalize(settings.azure_openai_deployment)
    api_version = _normalize(settings.azure_openai_api_version)
    openai_key = _normalize(settings.openai_api_key)
    azure_key = _normalize(settings.azure_openai_api_key)

    has_openai_key = bool(openai_key)
    has_azure_key = bool(azure_key)
    has_any_key = has_openai_key or has_azure_key
    key_source = 'OPENAI_API_KEY' if has_openai_key else ('AZURE_OPENAI_API_KEY' if has_azure_key else None)

    missing: list[str] = []
    if not endpoint:
        missing.append('AZURE_OPENAI_ENDPOINT')
    if not deployment:
        missing.append('AZURE_OPENAI_DEPLOYMENT')
    if not api_version:
        missing.append('AZURE_OPENAI_API_VERSION')
    if not has_any_key:
        missing.append('OPENAI_API_KEY or AZURE_OPENAI_API_KEY')

    return {
        'ok': len(missing) == 0,
        'missing': missing,
        'configured': {
            'azure_openai_endpoint': bool(endpoint),
            'azure_openai_deployment': bool(deployment),
            'azure_openai_api_version': bool(api_version),
            'openai_api_key': has_openai_key,
            'azure_openai_api_key': has_azure_key,
            'any_api_key': has_any_key,
        },
        'effective': {
            'endpoint': endpoint,
            'deployment': deployment,
            'api_version': api_version,
            'key_source': key_source,
            'key_preview': _masked_preview(openai_key or azure_key),
        },
    }
