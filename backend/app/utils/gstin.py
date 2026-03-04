from __future__ import annotations

import re
from typing import Any

GSTIN_PATTERN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')


def normalize_gstin(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if not GSTIN_PATTERN.fullmatch(cleaned):
        return None
    return cleaned
