"""Password hashing, JWT access tokens, and single-use secret tokens."""

import contextlib
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings


@lru_cache
def _hasher() -> PasswordHasher:
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
    )


def reset_caches() -> None:
    """Re-read cost parameters after a settings change (used by tests)."""
    _hasher.cache_clear()
    _dummy_hash.cache_clear()


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates a cost-parameter change."""
    try:
        return _hasher().check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache
def _dummy_hash() -> str:
    """A real argon2 hash of a random secret, computed once per process.

    Must be genuinely valid: verifying against a malformed hash raises immediately
    and does no work, which would leave the timing side channel wide open.
    """
    return _hasher().hash(secrets.token_urlsafe(32))


def spend_dummy_hash() -> None:
    """Constant-work path for logins against a non-existent account, so response
    time does not reveal whether an email is registered."""
    # The mismatch is expected — the argon2 work is the point, not the result.
    with contextlib.suppress(VerifyMismatchError):
        _hasher().verify(_dummy_hash(), "not-the-password")


# --- single-use tokens (email verification, password reset, refresh) ---------


def generate_token() -> str:
    """URL-safe secret handed to the user. Never stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a high-entropy token. Cheap by design — these are not passwords,
    and a database leak must not yield usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(candidate: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_token(candidate), stored_hash)


# --- access tokens ----------------------------------------------------------


class TokenError(Exception):
    """Access token missing, malformed, expired, or of the wrong type."""


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("typ") != "access":
        raise TokenError("not an access token")
    return payload
