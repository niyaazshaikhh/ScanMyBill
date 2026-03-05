from __future__ import annotations

from datetime import datetime, timedelta


def is_account_locked(*, locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and locked_until > now


def next_failed_login_state(
    *,
    failed_attempts: int,
    now: datetime,
    max_failed_attempts: int,
    lockout_minutes: int,
) -> tuple[int, datetime | None]:
    attempts = max(0, int(failed_attempts)) + 1
    if attempts >= max(1, max_failed_attempts):
        return 0, now + timedelta(minutes=max(1, lockout_minutes))
    return attempts, None

