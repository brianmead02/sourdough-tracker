"""End-to-end identity flows against live Postgres and Redis.

Run with `pytest -m integration`.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import token_from_email, unique_account

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]


async def register(client: AsyncClient, account: dict[str, str]) -> None:
    resp = await client.post("/api/v1/auth/register", json=account)
    assert resp.status_code == 202, resp.text


async def login(client: AsyncClient, account: dict[str, str]) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --- registration and verification -------------------------------------------


async def test_register_sends_verification_and_verifies(
    client: AsyncClient, outbox: Outbox
) -> None:
    account = unique_account()
    await register(client, account)

    assert len(outbox) == 1
    to, subject, body = outbox[0]
    assert to == account["email"]
    assert "Confirm" in subject

    tokens = await login(client, account)
    me = await client.get("/api/v1/auth/me", headers=auth_header(tokens))
    assert me.json()["is_verified"] is False

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token_from_email(body)})
    assert resp.status_code == 200, resp.text

    me = await client.get("/api/v1/auth/me", headers=auth_header(tokens))
    assert me.json()["is_verified"] is True
    assert me.json()["profile"]["handle"] == account["handle"]


async def test_verification_token_is_single_use(client: AsyncClient, outbox: Outbox) -> None:
    account = unique_account()
    await register(client, account)
    token = token_from_email(outbox[0][2])

    first = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 200
    second = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400


async def test_verify_rejects_unknown_token(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "made-up-token"})
    assert resp.status_code == 400


async def test_duplicate_email_does_not_leak_existence(client: AsyncClient, outbox: Outbox) -> None:
    """Both responses must be byte-identical, or registration becomes an oracle."""
    account = unique_account()
    await register(client, account)
    first = await client.post("/api/v1/auth/register", json=account | {"handle": "otherhandle1"})

    fresh = unique_account()
    second = await client.post("/api/v1/auth/register", json=fresh)

    assert first.status_code == second.status_code
    assert first.json() == second.json()
    # The real owner is told an attempt happened.
    assert any("already exists" in body for _, _, body in outbox)


async def test_duplicate_handle_is_rejected(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    other = unique_account() | {"handle": account["handle"]}
    resp = await client.post("/api/v1/auth/register", json=other)
    assert resp.status_code == 409


# --- login -------------------------------------------------------------------


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": account["email"], "password": "wrong-password-here"}
    )
    assert resp.status_code == 401


async def test_login_for_unknown_account_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "some-password-x"}
    )
    assert resp.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401


async def test_me_never_exposes_password_hash(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)
    body = (await client.get("/api/v1/auth/me", headers=auth_header(tokens))).json()
    assert "password_hash" not in body
    assert "password" not in str(body).lower().replace("password_min", "")


# --- refresh token rotation --------------------------------------------------


async def test_refresh_rotates_and_invalidates_the_old_token(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)

    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The new access token works.
    me = await client.get("/api/v1/auth/me", headers=auth_header(new_tokens))
    assert me.status_code == 200


async def test_refresh_token_reuse_revokes_the_whole_family(client: AsyncClient) -> None:
    """The core anti-theft property: replaying a rotated token kills the session."""
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)

    rotated = (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()

    # Attacker replays the token the legitimate client already spent.
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # ...and the legitimate client's successor token is now dead too.
    legit = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert legit.status_code == 401


async def test_logout_revokes_the_refresh_token(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)

    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 200

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


# --- password reset ----------------------------------------------------------


async def test_password_reset_flow_signs_out_existing_sessions(
    client: AsyncClient, outbox: Outbox
) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)
    outbox.clear()

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": account["email"]})
    assert forgot.status_code == 200
    reset_token = token_from_email(outbox[0][2])

    new_password = "a-brand-new-password"
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": new_password},
    )
    assert resp.status_code == 200, resp.text

    # Old refresh token no longer works.
    stale = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert stale.status_code == 401

    # Old password no longer works; the new one does.
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
    ).status_code == 401
    await login(client, account | {"password": new_password})


async def test_forgot_password_for_unknown_email_is_indistinguishable(
    client: AsyncClient, outbox: Outbox
) -> None:
    known = unique_account()
    await register(client, known)
    outbox.clear()

    hit = await client.post("/api/v1/auth/forgot-password", json={"email": known["email"]})
    miss = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody-here@example.com"}
    )
    assert hit.status_code == miss.status_code == 200
    assert hit.json() == miss.json()
    # Exactly one email was actually sent — to the address that exists.
    assert [to for to, _, _ in outbox] == [known["email"]]


async def test_change_password_requires_the_current_one(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "another-good-password"},
        headers=auth_header(tokens),
    )
    assert wrong.status_code == 400

    right = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": account["password"], "new_password": "another-good-password"},
        headers=auth_header(tokens),
    )
    assert right.status_code == 200
    # Sessions are cut after a password change.
    stale = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert stale.status_code == 401


# --- profiles ----------------------------------------------------------------


async def test_profile_is_private_until_published(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)
    handle = account["handle"]

    assert (await client.get(f"/api/v1/profiles/{handle}")).status_code == 404

    patched = await client.patch(
        "/api/v1/profiles/me",
        json={"is_public": True, "bio": "I bake bread.", "timezone": "America/Chicago"},
        headers=auth_header(tokens),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["timezone"] == "America/Chicago"

    public = await client.get(f"/api/v1/profiles/{handle}")
    assert public.status_code == 200
    assert public.json()["bio"] == "I bake bread."


async def test_public_profile_never_includes_email(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)
    await client.patch("/api/v1/profiles/me", json={"is_public": True}, headers=auth_header(tokens))

    body = (await client.get(f"/api/v1/profiles/{account['handle']}")).json()
    assert "email" not in body
    assert account["email"] not in str(body)


async def test_profile_rejects_unknown_timezone(client: AsyncClient) -> None:
    account = unique_account()
    await register(client, account)
    tokens = await login(client, account)
    resp = await client.patch(
        "/api/v1/profiles/me",
        json={"timezone": "Mars/Olympus_Mons"},
        headers=auth_header(tokens),
    )
    assert resp.status_code == 422
