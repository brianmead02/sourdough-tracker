"""Administration, moderation, data export and account erasure."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.db import get_session_factory
from app.models.user import User, UserRole
from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]

INGREDIENTS = [
    {"name": "flour", "kind": "flour", "percentage": 100},
    {"name": "water", "kind": "liquid", "percentage": 70},
]


async def make_admin(email: str, role: UserRole = UserRole.admin) -> None:
    """Promote out-of-band, the way `sdt create-admin` does."""
    async with get_session_factory()() as session:
        await session.execute(update(User).where(User.email == email.lower()).values(role=role))
        await session.commit()


async def register_admin(
    client: AsyncClient, outbox: Outbox, role: UserRole = UserRole.admin
) -> tuple[Headers, dict[str, str]]:
    headers, account = await register_user(client, outbox)
    await make_admin(account["email"], role)
    # The role is read from the database per request, so the existing token is
    # already an admin token — no re-login needed.
    return headers, account


# --- access control -----------------------------------------------------------


async def test_admin_endpoints_reject_ordinary_users(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    for method, path in [
        ("get", "/api/v1/admin/users"),
        ("get", "/api/v1/admin/stats"),
        ("get", "/api/v1/admin/moderation/queue"),
    ]:
        resp = await getattr(client, method)(path, headers=headers)
        assert resp.status_code == 403, path


async def test_admin_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/users")).status_code == 401


async def test_a_moderator_can_moderate(client: AsyncClient, outbox: Outbox) -> None:
    """Moderation is the moderator role's whole purpose."""
    headers, _ = await register_admin(client, outbox, UserRole.moderator)
    assert (await client.get("/api/v1/admin/moderation/queue", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/admin/users", headers=headers)).status_code == 200


# --- user administration ------------------------------------------------------


async def test_user_search_by_email_and_handle(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    _, target = await register_user(client, outbox)

    by_handle = (
        await client.get(f"/api/v1/admin/users?q={target['handle']}", headers=admin)
    ).json()
    assert [row["handle"] for row in by_handle] == [target["handle"]]

    by_email = (
        await client.get(f"/api/v1/admin/users?q={target['email'][:12]}", headers=admin)
    ).json()
    assert any(row["email"] == target["email"] for row in by_email)


async def test_user_rows_carry_activity_counts(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    baker, account = await register_user(client, outbox)
    await client.post(
        "/api/v1/recipes",
        json={"name": "Public", "is_public": True, "ingredients": INGREDIENTS},
        headers=baker,
    )
    await client.post("/api/v1/bakes", json={"title": "One"}, headers=baker)

    row = next(
        r
        for r in (await client.get("/api/v1/admin/users", headers=admin)).json()
        if r["handle"] == account["handle"]
    )
    assert row["public_recipes"] == 1
    assert row["bakes"] == 1


async def test_suspending_takes_effect_immediately(client: AsyncClient, outbox: Outbox) -> None:
    """Suspension is checked per request, so the existing token stops working."""
    admin, _ = await register_admin(client, outbox)
    victim, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=victim)).json()

    assert (await client.get("/api/v1/starters", headers=victim)).status_code == 200

    resp = await client.post(
        f"/api/v1/admin/users/{me['id']}/suspend",
        json={"reason": "spam"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_suspended"] is True

    blocked = await client.get("/api/v1/starters", headers=victim)
    assert blocked.status_code == 403
    assert "suspended" in blocked.json()["detail"].lower()


async def test_suspension_also_kills_refresh_tokens(client: AsyncClient, outbox: Outbox) -> None:
    """Otherwise a refresh would mint a fresh access token straight after."""
    admin, _ = await register_admin(client, outbox)
    victim, account = await register_user(client, outbox)
    tokens = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
    ).json()
    me = (await client.get("/api/v1/auth/me", headers=victim)).json()

    await client.post(
        f"/api/v1/admin/users/{me['id']}/suspend", json={"reason": "abuse"}, headers=admin
    )

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 401


async def test_unsuspending_restores_access(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    victim, account = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=victim)).json()

    await client.post(
        f"/api/v1/admin/users/{me['id']}/suspend", json={"reason": "mistake"}, headers=admin
    )
    resp = await client.post(f"/api/v1/admin/users/{me['id']}/unsuspend", headers=admin)
    assert resp.json()["is_suspended"] is False
    assert resp.json()["suspended_reason"] is None

    # A fresh login works again; the old tokens stay revoked.
    again = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert again.status_code == 200


async def test_an_admin_cannot_suspend_themselves(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=admin)).json()
    resp = await client.post(
        f"/api/v1/admin/users/{me['id']}/suspend", json={"reason": "oops"}, headers=admin
    )
    assert resp.status_code == 409


async def test_administrators_cannot_be_suspended(client: AsyncClient, outbox: Outbox) -> None:
    """One compromised moderator must not be able to lock out the operators."""
    moderator, _ = await register_admin(client, outbox, UserRole.moderator)
    _, admin_account = await register_admin(client, outbox, UserRole.admin)

    async with get_session_factory()() as session:
        row = await session.execute(
            select(User.id).where(User.email == admin_account["email"].lower())
        )
        admin_id = row.scalar_one()

    resp = await client.post(
        f"/api/v1/admin/users/{admin_id}/suspend", json={"reason": "coup"}, headers=moderator
    )
    assert resp.status_code == 403


async def test_suspension_needs_a_reason(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    victim, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=victim)).json()
    resp = await client.post(
        f"/api/v1/admin/users/{me['id']}/suspend", json={"reason": ""}, headers=admin
    )
    assert resp.status_code == 422


# --- content moderation -------------------------------------------------------


async def test_moderation_queue_shows_published_recipes_only(
    client: AsyncClient, outbox: Outbox
) -> None:
    admin, _ = await register_admin(client, outbox)
    author, account = await register_user(client, outbox)

    await client.post(
        "/api/v1/recipes",
        json={"name": "Published", "is_public": True, "ingredients": INGREDIENTS},
        headers=author,
    )
    await client.post(
        "/api/v1/recipes",
        json={"name": "Private", "ingredients": INGREDIENTS},
        headers=author,
    )

    queue = (await client.get("/api/v1/admin/moderation/queue", headers=admin)).json()
    assert [item["name"] for item in queue] == ["Published"]
    assert queue[0]["owner_handle"] == account["handle"]
    assert queue[0]["owner_suspended"] is False


async def test_unpublishing_hides_a_recipe_without_destroying_it(
    client: AsyncClient, outbox: Outbox
) -> None:
    """Moderation should be reversible; deleting the author's work is not."""
    admin, _ = await register_admin(client, outbox)
    author, _ = await register_user(client, outbox)
    reader, _ = await register_user(client, outbox)

    recipe = (
        await client.post(
            "/api/v1/recipes",
            json={"name": "Borderline", "is_public": True, "ingredients": INGREDIENTS},
            headers=author,
        )
    ).json()

    assert (await client.get("/api/v1/recipes/public", headers=reader)).json() != []

    resp = await client.post(f"/api/v1/admin/recipes/{recipe['id']}/unpublish", headers=admin)
    assert resp.status_code == 204

    assert (await client.get("/api/v1/recipes/public", headers=reader)).json() == []
    assert (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=reader)).status_code == 404
    # The author keeps it.
    still_theirs = await client.get(f"/api/v1/recipes/{recipe['id']}", headers=author)
    assert still_theirs.status_code == 200
    assert still_theirs.json()["is_public"] is False


async def test_stats_report_the_instance(client: AsyncClient, outbox: Outbox) -> None:
    admin, _ = await register_admin(client, outbox)
    baker, _ = await register_user(client, outbox)
    await client.post("/api/v1/starters", json={"name": "Gerald"}, headers=baker)

    stats = (await client.get("/api/v1/admin/stats", headers=admin)).json()
    assert stats["users_total"] == 2
    assert stats["users_verified"] == 2
    assert stats["users_suspended"] == 0
    assert stats["starters"] == 1
    assert stats["database_bytes"] > 0


# --- data export --------------------------------------------------------------


async def build_a_history(client: AsyncClient, headers: Headers) -> None:
    starter = (
        await client.post("/api/v1/starters", json={"name": "Gerald"}, headers=headers)
    ).json()
    await client.post(
        f"/api/v1/starters/{starter['id']}/feedings",
        json={"starter_g": 20, "flour_g": 100, "water_g": 100},
        headers=headers,
    )
    proof = (
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/complete", json={}, headers=headers)
    await client.post(
        "/api/v1/recipes",
        json={"name": "Mine", "ingredients": INGREDIENTS},
        headers=headers,
    )
    bake = (await client.post("/api/v1/bakes", json={"title": "A loaf"}, headers=headers)).json()
    await client.post(
        f"/api/v1/bakes/{bake['id']}/complete", json={"consume_inventory": False}, headers=headers
    )
    await client.put(f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 5}, headers=headers)


async def test_export_contains_the_whole_account(client: AsyncClient, outbox: Outbox) -> None:
    headers, account = await register_user(client, outbox)
    await build_a_history(client, headers)

    resp = await client.get("/api/v1/account/export", headers=headers)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert account["handle"] in resp.headers["content-disposition"]

    data: dict[str, Any] = resp.json()
    assert data["account"]["email"] == account["email"]
    assert data["profile"]["handle"] == account["handle"]
    assert len(data["starters"]) == 1
    assert len(data["feedings"]) == 1
    assert len(data["proof_sessions"]) == 1
    assert len(data["recipes"]) == 1
    assert data["recipes"][0]["ingredients"], "ingredients are nested inside the recipe"
    assert len(data["bakes"]) == 1
    assert len(data["ratings"]) == 1
    assert data["xp_events"], "the XP ledger is the user's own history"
    assert data["achievements"]


async def test_export_never_leaks_credentials(client: AsyncClient, outbox: Outbox) -> None:
    """An export is personal data, not a way to hand back secrets."""
    headers, _ = await register_user(client, outbox)
    await build_a_history(client, headers)

    body = (await client.get("/api/v1/account/export", headers=headers)).text
    assert "password_hash" not in body
    assert "token_hash" not in body
    assert "argon2" not in body


async def test_export_is_scoped_to_the_caller(client: AsyncClient, outbox: Outbox) -> None:
    mine, my_account = await register_user(client, outbox)
    theirs, their_account = await register_user(client, outbox)
    await build_a_history(client, theirs)

    data = (await client.get("/api/v1/account/export", headers=mine)).json()
    assert data["account"]["email"] == my_account["email"]
    assert data["starters"] == []
    assert their_account["email"] not in str(data)


async def test_export_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/account/export")).status_code == 401


# --- erasure ------------------------------------------------------------------


async def test_erasure_removes_everything(client: AsyncClient, outbox: Outbox) -> None:
    headers, account = await register_user(client, outbox)
    await build_a_history(client, headers)

    resp = await client.post(
        "/api/v1/account/delete",
        json={"password": account["password"], "confirm": "DELETE MY ACCOUNT"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is True
    assert body["rows_removed"]["account"] == 1
    assert body["rows_removed"]["starters"] == 1

    # The session is gone with the account.
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    # And so is the ability to log back in.
    again = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert again.status_code == 401


async def test_erasure_leaves_nothing_behind_in_any_table(
    client: AsyncClient, outbox: Outbox
) -> None:
    """A soft delete would be the wrong tool here — this must really be gone."""
    headers, account = await register_user(client, outbox)
    await build_a_history(client, headers)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])

    await client.post(
        "/api/v1/account/delete",
        json={"password": account["password"], "confirm": "DELETE MY ACCOUNT"},
        headers=headers,
    )

    async with get_session_factory()() as session:
        tables = await session.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'user_id' AND table_schema = 'public'"
            )
        )
        leftovers = {}
        for (table,) in tables.all():
            count = await session.execute(
                text(f'SELECT count(*) FROM "{table}" WHERE user_id = :uid'), {"uid": user_id}
            )
            remaining = count.scalar_one()
            if remaining:
                leftovers[table] = remaining
        users = await session.execute(
            text('SELECT count(*) FROM "user" WHERE id = :uid'), {"uid": user_id}
        )

    assert leftovers == {}, f"rows survived erasure: {leftovers}"
    assert users.scalar_one() == 0


async def test_erasure_keeps_other_peoples_forks(client: AsyncClient, outbox: Outbox) -> None:
    """Someone else's copy is their data, not the deleting user's."""
    author, author_account = await register_user(client, outbox)
    forker, _ = await register_user(client, outbox)

    original = (
        await client.post(
            "/api/v1/recipes",
            json={"name": "Shared", "is_public": True, "ingredients": INGREDIENTS},
            headers=author,
        )
    ).json()
    fork = (await client.post(f"/api/v1/recipes/{original['id']}/fork", headers=forker)).json()
    assert fork["forked_from_id"] == original["id"]

    await client.post(
        "/api/v1/account/delete",
        json={"password": author_account["password"], "confirm": "DELETE MY ACCOUNT"},
        headers=author,
    )

    survivor = await client.get(f"/api/v1/recipes/{fork['id']}", headers=forker)
    assert survivor.status_code == 200
    assert survivor.json()["forked_from_id"] is None, "the parent link is cleared, not dangling"
    assert len(survivor.json()["ingredients"]) == 2


async def test_erasure_corrects_star_counts_it_had_inflated(
    client: AsyncClient, outbox: Outbox
) -> None:
    author, _ = await register_user(client, outbox)
    fan, fan_account = await register_user(client, outbox)

    recipe = (
        await client.post(
            "/api/v1/recipes",
            json={"name": "Popular", "is_public": True, "ingredients": INGREDIENTS},
            headers=author,
        )
    ).json()
    await client.post(f"/api/v1/recipes/{recipe['id']}/star", headers=fan)
    assert (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=author)).json()[
        "star_count"
    ] == 1

    await client.post(
        "/api/v1/account/delete",
        json={"password": fan_account["password"], "confirm": "DELETE MY ACCOUNT"},
        headers=fan,
    )

    after = (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=author)).json()
    assert after["star_count"] == 0, "the counter must not stay overstated"


async def test_erasure_needs_the_password(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/account/delete",
        json={"password": "not-the-password", "confirm": "DELETE MY ACCOUNT"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


async def test_erasure_needs_the_exact_confirmation_phrase(
    client: AsyncClient, outbox: Outbox
) -> None:
    """It is irreversible and has no grace period, so it must be deliberate."""
    headers, account = await register_user(client, outbox)
    for phrase in ["", "delete my account", "DELETE MY ACCOUNT ", "yes"]:
        resp = await client.post(
            "/api/v1/account/delete",
            json={"password": account["password"], "confirm": phrase},
            headers=headers,
        )
        assert resp.status_code == 422, phrase
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
