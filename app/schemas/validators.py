"""Field validators shared across request schemas."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings

HANDLE_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$")

# Reserved so profile URLs can never collide with app routes or impersonate staff.
RESERVED_HANDLES = frozenset(
    {
        "admin",
        "administrator",
        "api",
        "auth",
        "docs",
        "help",
        "login",
        "logout",
        "me",
        "moderator",
        "profiles",
        "register",
        "root",
        "settings",
        "sourdough",
        "staff",
        "support",
        "system",
        "user",
    }
)


def validate_password(value: str) -> str:
    minimum = get_settings().password_min_length
    if len(value) < minimum:
        raise ValueError(f"password must be at least {minimum} characters")
    return value


def validate_handle(value: str) -> str:
    handle = value.strip().lower()
    if not HANDLE_PATTERN.match(handle):
        raise ValueError("handle must be 3-30 characters, lowercase letters, numbers or underscore")
    if handle in RESERVED_HANDLES:
        raise ValueError("that handle is reserved")
    return handle


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("unknown IANA timezone") from exc
    return value
