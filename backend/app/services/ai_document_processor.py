from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from PIL import Image

from app.core.config import settings

_SUPPORTED_MIME = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/webp',
}
_MAX_PDF_PAGES = 3
_MAX_TOKENS = 1500


def _detect_mime(payload: bytes, file_path: Path) -> str | None:
    if payload.startswith(b'%PDF-'):
        return 'application/pdf'
    if payload.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if payload.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if len(payload) >= 12 and payload[:4] == b'RIFF' and payload[8:12] == b'WEBP':
        return 'image/webp'

    suffix = file_path.suffix.lower()
    if suffix == '.pdf':
        return 'application/pdf'
    if suffix == '.png':
        return 'image/png'
    if suffix in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if suffix == '.webp':
        return 'image/webp'
    return None


def _encode_pil_to_jpeg_data_url(image: Image.Image) -> str | None:
    try:
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/jpeg;base64,{encoded}'
    except Exception:
        return None


def _build_image_blocks(file_path: Path, mime_type: str, payload: bytes) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    if mime_type == 'application/pdf':
        try:
            pages = convert_from_path(str(file_path), first_page=1, last_page=_MAX_PDF_PAGES)
        except Exception:
            return blocks

        for page in pages:
            data_url = _encode_pil_to_jpeg_data_url(page)
            if data_url:
                blocks.append({'type': 'image_url', 'image_url': {'url': data_url}})
        return blocks

    if mime_type.startswith('image/'):
        try:
            with Image.open(file_path) as image:
                data_url = _encode_pil_to_jpeg_data_url(image)
        except Exception:
            data_url = None

        if not data_url:
            normalized_mime = 'image/jpeg' if mime_type in {'image/jpg', 'image/jpeg'} else mime_type
            encoded = base64.b64encode(payload).decode('ascii')
            data_url = f'data:{normalized_mime};base64,{encoded}'

        blocks.append({'type': 'image_url', 'image_url': {'url': data_url}})

    return blocks


def _system_prompt() -> str:
    return (
        'You are a finance document extraction engine. '
        'Return only valid JSON. No markdown or explanation. '
        'First identify document_type as gst_invoice or delivery_challan. '
        'Identify transaction_type as sales or purchase. '
        'For gst_invoice output keys: '
        'document_type, transaction_type, invoice_number, invoice_date, seller, buyer, items. '
        'For delivery_challan output keys: '
        'document_type, transaction_type, challan_number, order_number, challan_date, from_party, to_party, items. '
        'If any value is unavailable, use null. Keep keys present.'
    )


def _build_user_instruction() -> str:
    return (
        'Extract structured bill information from this document. '
        'Return JSON object only with fields required for either gst_invoice or delivery_challan. '
        'Do not include any text outside JSON.'
    )


def _validate_document_type(data: dict[str, Any]) -> dict[str, Any]:
    document_type = str(data.get('document_type') or '').strip().lower()
    if document_type not in {'gst_invoice', 'delivery_challan'}:
        return {'error': 'Model returned unknown document type'}
    return data


def _extract_content_text(completion: Any) -> str:
    try:
        choice = completion.choices[0]
        message = choice.message
        content = message.content
    except Exception:
        return ''

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get('text'), str):
                chunks.append(part['text'])
        return ''.join(chunks)
    return ''


def _sync_completion(image_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from openai import AzureOpenAI
    except Exception:
        return {'error': 'OpenAI SDK is not installed on server'}

    endpoint = settings.azure_openai_endpoint
    deployment = settings.azure_openai_deployment
    api_key = settings.openai_api_key or settings.azure_openai_api_key

    if not endpoint or not deployment or not api_key:
        return {'error': 'Azure OpenAI configuration missing'}

    client = AzureOpenAI(
        api_version=settings.azure_openai_api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
    )

    try:
        completion = client.chat.completions.create(
            model=deployment,
            messages=[
                {'role': 'system', 'content': _system_prompt()},
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': _build_user_instruction()},
                        *image_blocks,
                    ],
                },
            ],
            temperature=0,
            max_tokens=_MAX_TOKENS,
            response_format={'type': 'json_object'},
        )
    except Exception:
        return {'error': 'Failed to extract data from AI model'}

    content = _extract_content_text(completion)
    if not content:
        return {'error': 'AI model returned empty response'}

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {'error': 'Model returned invalid JSON'}

    if not isinstance(parsed, dict):
        return {'error': 'Model returned invalid JSON object'}

    return _validate_document_type(parsed)


async def extract_document_data(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return {'error': 'File cannot be processed'}

    try:
        payload = path.read_bytes()
    except Exception:
        return {'error': 'File cannot be processed'}

    mime_type = _detect_mime(payload, path)
    if mime_type not in _SUPPORTED_MIME:
        return {'error': 'Unsupported file type for AI processing'}

    image_blocks = _build_image_blocks(path, mime_type, payload)
    if not image_blocks:
        return {'error': 'File cannot be processed'}

    return await asyncio.to_thread(_sync_completion, image_blocks)
