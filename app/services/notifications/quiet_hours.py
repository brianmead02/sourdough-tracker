"""Quiet hours arithmetic.

Pure, because the tricky parts are all edge cases: windows that wrap midnight,
users in timezones far from UTC, and the difference between "hold this" and
"send it anyway".
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(name: str | None) -> ZoneInfo:
    """A bad or missing timezone must not stop a reminder — fall back to UTC."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def is_quiet(
    moment: datetime, start_hour: int | None, end_hour: int | None, timezone: str | None
) -> bool:
    """Is `moment` inside the user's quiet window, judged in their local time?"""
    if start_hour is None or end_hour is None or start_hour == end_hour:
        return False

    local_hour = moment.astimezone(resolve_timezone(timezone)).hour

    if start_hour < end_hour:
        # A window inside one day, e.g. 13:00-15:00.
        return start_hour <= local_hour < end_hour
    # A window that wraps midnight, e.g. 22:00-07:00 — the common case.
    return local_hour >= start_hour or local_hour < end_hour


def next_wake_time(
    moment: datetime, start_hour: int | None, end_hour: int | None, timezone: str | None
) -> datetime:
    """When the quiet window ends, as an aware UTC datetime.

    Returns `moment` unchanged if it is not currently quiet, so callers can use
    the result unconditionally.
    """
    if not is_quiet(moment, start_hour, end_hour, timezone):
        return moment

    assert end_hour is not None
    zone = resolve_timezone(timezone)
    local = moment.astimezone(zone)

    wake = local.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if wake <= local:
        wake += timedelta(days=1)

    return wake.astimezone(moment.tzinfo or zone)


def is_stale(due_at: datetime, now: datetime, expires_after_hours: int | None) -> bool:
    """Has this reminder outlived its usefulness?

    A "your dough is ready" that surfaces six hours late is worse than silence:
    it is wrong, and it teaches the baker to distrust the next one.
    """
    if expires_after_hours is None:
        return False
    return now - due_at > timedelta(hours=expires_after_hours)
