from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader

from app.models.invoice import InvoiceType

GST_REGEX = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b')
DATE_PATTERNS = [
    '%d/%m/%Y',
    '%d-%m-%Y',
    '%d.%m.%Y',
    '%Y-%m-%d',
    '%d/%m/%y',
    '%d-%m-%y',
]


def extract_text_from_file(file_path: str, mime_type: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return ''

    try:
        if mime_type.startswith('image/'):
            image = Image.open(path)
            return pytesseract.image_to_string(image)

        if mime_type == 'application/pdf':
            return _extract_text_from_pdf(path)

        return ''
    except Exception:
        return ''


def _extract_text_from_pdf(path: Path) -> str:
    # OCR first 2 pages for scanned PDFs, then fallback to embedded text extraction.
    text_parts: list[str] = []
    try:
        images = convert_from_path(str(path), first_page=1, last_page=2)
        for image in images:
            text_parts.append(pytesseract.image_to_string(image))
    except Exception:
        pass

    if ''.join(text_parts).strip():
        return '\n'.join(text_parts)

    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:2]:
            text_parts.append(page.extract_text() or '')
    except Exception:
        return ''

    return '\n'.join(text_parts)


def extract_structured_data(text: str, fallback_type: InvoiceType) -> dict:
    normalized_text = text or ''
    lowered = normalized_text.lower()

    date_value = _extract_date(normalized_text)
    gst_number = _extract_gst_number(normalized_text)
    total_amount = _extract_total_amount(normalized_text)

    inferred_type = fallback_type
    sale_keywords = ['sales invoice', 'tax invoice', 'outward', 'billed to']
    purchase_keywords = ['purchase', 'supplier', 'vendor bill', 'inward']

    if any(keyword in lowered for keyword in sale_keywords):
        inferred_type = InvoiceType.SALES
    elif any(keyword in lowered for keyword in purchase_keywords):
        inferred_type = InvoiceType.PURCHASE

    return {
        'bill_date': date_value,
        'gst_number': gst_number,
        'total_amount': total_amount,
        'inferred_type': inferred_type,
    }


def _extract_date(text: str) -> date | None:
    matches = re.findall(r'\b(\d{1,4}[./-]\d{1,2}[./-]\d{2,4})\b', text)
    for match in matches:
        candidate = match.strip()
        for pattern in DATE_PATTERNS:
            try:
                parsed = datetime.strptime(candidate, pattern)
                if parsed.year < 2000:
                    parsed = parsed.replace(year=parsed.year + 2000)
                return parsed.date()
            except ValueError:
                continue
    return None


def _extract_gst_number(text: str) -> str | None:
    match = GST_REGEX.search(text.upper())
    return match.group(0) if match else None


def _extract_total_amount(text: str) -> float:
    patterns = [
        r'(?:grand\s*total|amount\s*due|total\s*amount|invoice\s*total)\s*[:\-]?\s*[₹Rs.\s]*([0-9,]+(?:\.\d{1,2})?)',
        r'(?:payable|net\s*amount)\s*[:\-]?\s*[₹Rs.\s]*([0-9,]+(?:\.\d{1,2})?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _to_float(match.group(1))

    numeric_candidates = re.findall(r'\b([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.\d{1,2})?)\b', text)
    if numeric_candidates:
        values = [_to_float(value) for value in numeric_candidates]
        values = [value for value in values if value > 0]
        if values:
            return max(values)

    return 0.0


def _to_float(value: str) -> float:
    try:
        return float(value.replace(',', '').strip())
    except ValueError:
        return 0.0