"""Validation rules on the auth request schemas. No database required."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest

VALID = {
    "email": "baker@example.com",
    "password": "a-long-enough-password",
    "handle": "crumb_chaser",
    "display_name": "Crumb Chaser",
}


def test_valid_registration() -> None:
    req = RegisterRequest(**VALID)
    assert req.handle == "crumb_chaser"
    assert req.timezone == "UTC"


def test_handle_is_lowercased() -> None:
    assert RegisterRequest(**{**VALID, "handle": "CrumbChaser"}).handle == "crumbchaser"


@pytest.mark.parametrize(
    "handle",
    ["ab", "a" * 31, "has space", "has-dash", "has.dot", "Ünïcode", ""],
)
def test_invalid_handles_rejected(handle: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "handle": handle})


@pytest.mark.parametrize("handle", ["admin", "me", "support", "API"])
def test_reserved_handles_rejected(handle: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "handle": handle})


def test_short_password_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "password": "short"})


def test_absurdly_long_password_rejected() -> None:
    """Bounded so an attacker cannot force expensive argon2 work."""
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "password": "x" * 129})


def test_invalid_email_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "email": "not-an-email"})


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "timezone": "Mars/Olympus_Mons"})


def test_known_timezone_accepted() -> None:
    assert RegisterRequest(**{**VALID, "timezone": "America/Chicago"}).timezone == (
        "America/Chicago"
    )
