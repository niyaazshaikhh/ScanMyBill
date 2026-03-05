from __future__ import annotations

import re

PASSWORD_COMPLEXITY_PATTERN = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,128}$'
)
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 .,'&()-]{1,254}$")


def ensure_password_strength(password: str) -> str:
    if not PASSWORD_COMPLEXITY_PATTERN.fullmatch(password):
        raise ValueError(
            'Password must be 8-128 characters long and include uppercase, lowercase, number, and special character.'
        )
    return password


def ensure_safe_person_name(value: str, field_name: str = 'Name') -> str:
    candidate = (value or '').strip()
    if not SAFE_NAME_PATTERN.fullmatch(candidate):
        raise ValueError(
            f'{field_name} contains invalid characters. Use letters, numbers, spaces, and basic punctuation only.'
        )
    return candidate

