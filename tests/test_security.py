"""Unit tests for the crypto primitives. No database required."""

import uuid

import pytest

from app.services.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    tokens_match,
    verify_password,
)


def test_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password entirely", hashed)


def test_password_hashes_are_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_rejects_malformed_hash() -> None:
    """A corrupt stored hash must fail closed, not raise."""
    assert not verify_password("anything", "not-a-real-argon2-hash")


def test_generated_tokens_are_unique_and_long() -> None:
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 40 for t in tokens)


def test_token_hashing_is_stable_and_comparable() -> None:
    token = generate_token()
    stored = hash_token(token)
    assert len(stored) == 64  # sha256 hex
    assert tokens_match(token, stored)
    assert not tokens_match(generate_token(), stored)


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id, "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"
    assert payload["typ"] == "access"
    assert expires_in > 0


def test_access_token_rejects_tampering() -> None:
    token, _ = create_access_token(uuid.uuid4(), "user")
    header, body, signature = token.split(".")
    tampered = f"{header}.{body}.{signature[:-4]}AAAA"
    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_access_token_rejects_garbage() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt")
