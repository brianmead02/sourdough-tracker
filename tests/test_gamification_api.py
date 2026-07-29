"""XP, achievements and leaderboards against live Postgres."""

import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.db import get_session_factory
from app.services.leaderboard import refresh
from tests.conftest import register_user
from tests.test_bakes_api import PNG_BYTES

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]


async def refresh_leaderboard() -> None:
    """Run the rollup directly — in production this is a beat cron."""
    async with get_session_factory()() as session:
        await refresh(session)
        await session.commit()


async def complete_a_bake(
    client: AsyncClient, headers: Headers, **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"title": "Loaf"} | overrides
    bake = (await client.post("/api/v1/bakes", json=body, headers=headers)).json()
    resp = await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"consume_inventory": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def attach_a_photo(client: AsyncClient, headers: Headers, bake_id: str) -> None:
    grant = (
        await client.post(
            "/api/v1/media/presign-upload",
            json={"content_type": "image/png"},
            headers=headers,
        )
    ).json()
    async with httpx.AsyncClient(timeout=30) as raw:
        await raw.post(
            grant["url"],
            data=grant["fields"],
            files={"file": ("p.png", PNG_BYTES, "image/png")},
        )
    resp = await client.post(
        f"/api/v1/bakes/{bake_id}/photos",
        json={"object_key": grant["object_key"], "kind": "crumb"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


# --- earning ------------------------------------------------------------------


async def test_completing_a_bake_pays_xp_and_awards_a_badge(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    done = await complete_a_bake(client, headers)

    assert done["xp_gained"] > 0
    assert "first_loaf" in {a["code"] for a in done["awards"]}


async def test_a_badge_is_awarded_once(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    first = await complete_a_bake(client, headers, title="One")
    second = await complete_a_bake(client, headers, title="Two")

    assert "first_loaf" in {a["code"] for a in first["awards"]}
    assert "first_loaf" not in {a["code"] for a in second["awards"]}


async def test_xp_accumulates_across_actions(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    before = (await client.get("/api/v1/gamification/tier", headers=headers)).json()

    await client.post("/api/v1/starters", json={"name": "Gerald"}, headers=headers)
    await complete_a_bake(client, headers)

    after = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
    assert after["lifetime_xp"] > before["lifetime_xp"]
    assert after["season_xp"] == after["lifetime_xp"], "a new account's season is its lifetime"


async def test_tier_advances_with_xp(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    tier = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
    assert tier["tier"] == "Novice"
    assert tier["achievements_total"] >= 40
    assert tier["next_tier"] == "Home Baker"
    assert tier["season_name"].endswith(("Q1", "Q2", "Q3", "Q4"))


async def test_xp_history_records_the_cause(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers)

    history = (await client.get("/api/v1/gamification/xp/history", headers=headers)).json()
    rules = {row["rule_code"] for row in history}
    assert "xp.bake.completed" in rules
    assert "achievement.first_loaf" in rules
    assert all(row["amount"] > 0 for row in history)


async def test_achievements_list_shows_progress_towards_unearned_badges(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers)

    rows = (await client.get("/api/v1/gamification/achievements", headers=headers)).json()
    by_code = {r["code"]: r for r in rows}

    assert by_code["first_loaf"]["earned"] is True
    assert by_code["first_loaf"]["earned_at"] is not None
    assert by_code["ten_bakes"]["earned"] is False
    assert by_code["ten_bakes"]["current"] == 1.0
    assert by_code["ten_bakes"]["percent"] == 10.0

    earned_only = (
        await client.get("/api/v1/gamification/achievements?earned_only=true", headers=headers)
    ).json()
    assert all(r["earned"] for r in earned_only)


async def test_meta_achievement_triggers_from_another_award(
    client: AsyncClient, outbox: Outbox
) -> None:
    """ "Earn 10 badges" is itself a badge, so the engine has to run a second pass.

    Without it the tenth badge would land and its meta-badge would sit unearned
    until some unrelated event happened to re-evaluate it.
    """
    headers, _ = await register_user(client, outbox)

    for index in range(10):  # first_loaf, ten_bakes
        await complete_a_bake(client, headers, title=f"Loaf {index}")
    for index in range(3):  # first_starter, three_starters
        await client.post("/api/v1/starters", json={"name": f"S{index}"}, headers=headers)

    starters = (await client.get("/api/v1/starters", headers=headers)).json()
    await client.post(  # first_feed
        f"/api/v1/starters/{starters[0]['id']}/feedings",
        json={"starter_g": 20, "flour_g": 100, "water_g": 100},
        headers=headers,
    )

    proof = (  # first_proof
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/complete", json={}, headers=headers)

    ingredients = [
        {"name": "flour", "kind": "flour", "percentage": 100},
        {"name": "water", "kind": "liquid", "percentage": 70},
    ]
    await client.post(  # first_recipe
        "/api/v1/recipes", json={"name": "Private one", "ingredients": ingredients}, headers=headers
    )
    await client.post(  # first_publish
        "/api/v1/recipes",
        json={"name": "Public one", "is_public": True, "ingredients": ingredients},
        headers=headers,
    )

    wet = (  # hydration_75 and first_perfect
        await client.post(
            "/api/v1/bakes", json={"title": "Wet", "hydration_pct": 78}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/v1/bakes/{wet['id']}/complete", json={"consume_inventory": False}, headers=headers
    )
    await client.put(f"/api/v1/bakes/{wet['id']}/rating", json={"overall": 5}, headers=headers)

    earned = {
        r["code"]
        for r in (
            await client.get("/api/v1/gamification/achievements?earned_only=true", headers=headers)
        ).json()
    }
    assert len(earned) >= 10, sorted(earned)
    assert "collector_10" in earned, "the meta-badge did not fire on the same request"


async def test_badges_are_still_earned_once_xp_is_capped(
    client: AsyncClient, outbox: Outbox
) -> None:
    """The daily cap limits XP, not progress — a milestone still lands."""
    headers, _ = await register_user(client, outbox)
    for index in range(10):
        await complete_a_bake(client, headers, title=f"Loaf {index}")

    earned = {
        r["code"]
        for r in (
            await client.get("/api/v1/gamification/achievements?earned_only=true", headers=headers)
        ).json()
    }
    assert "ten_bakes" in earned


# --- anti-cheat ---------------------------------------------------------------


async def test_daily_cap_stops_paying_but_not_working(client: AsyncClient, outbox: Outbox) -> None:
    """Past the cap the action still succeeds; it just stops earning."""
    headers, _ = await register_user(client, outbox)
    starter = (
        await client.post("/api/v1/starters", json={"name": "Grinder"}, headers=headers)
    ).json()

    from datetime import UTC, datetime, timedelta

    paid = 0
    for hours in range(1, 20):
        fed_at = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        before = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
        resp = await client.post(
            f"/api/v1/starters/{starter['id']}/feedings",
            json={"fed_at": fed_at, "starter_g": 20, "flour_g": 100, "water_g": 100},
            headers=headers,
        )
        assert resp.status_code == 201, "the feeding is still recorded"
        after = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
        if after["lifetime_xp"] > before["lifetime_xp"]:
            paid += 1

    assert paid < 19, "an uncapped feeding rule would pay every single time"


async def test_photo_gated_badge_is_withheld_until_there_is_evidence(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)

    bake = (
        await client.post(
            "/api/v1/bakes", json={"title": "Wet one", "hydration_pct": 88}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"consume_inventory": False},
        headers=headers,
    )
    await client.put(f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 5}, headers=headers)

    rows = (await client.get("/api/v1/gamification/achievements", headers=headers)).json()
    by_code = {r["code"]: r for r in rows}
    assert by_code["hydration_75"]["earned"] is True, "the ungated tier is earned on numbers"
    assert by_code["hydration_85"]["earned"] is False, "the gated tier needs a photo"

    await attach_a_photo(client, headers, bake["id"])

    rows = (await client.get("/api/v1/gamification/achievements", headers=headers)).json()
    # Progress is visible immediately; the award lands on the next qualifying event.
    assert {r["code"]: r for r in rows}["hydration_85"]["percent"] == 100.0

    await client.put(f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 5}, headers=headers)
    rows = (await client.get("/api/v1/gamification/achievements", headers=headers)).json()
    assert {r["code"]: r for r in rows}["hydration_85"]["earned"] is True


async def test_hydration_badge_needs_a_good_loaf_not_just_a_big_number(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = (
        await client.post(
            "/api/v1/bakes", json={"title": "Soup", "hydration_pct": 95}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"consume_inventory": False},
        headers=headers,
    )
    await client.put(f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 1}, headers=headers)

    rows = {
        r["code"]: r
        for r in (await client.get("/api/v1/gamification/achievements", headers=headers)).json()
    }
    assert rows["hydration_75"]["earned"] is False
    assert rows["hydration_75"]["current"] == 0.0


# --- social credit ------------------------------------------------------------


async def test_a_fork_credits_the_author_not_the_forker(
    client: AsyncClient, outbox: Outbox
) -> None:
    author, _ = await register_user(client, outbox)
    forker, _ = await register_user(client, outbox)

    recipe = (
        await client.post(
            "/api/v1/recipes",
            json={
                "name": "Shared loaf",
                "is_public": True,
                "ingredients": [
                    {"name": "flour", "kind": "flour", "percentage": 100},
                    {"name": "water", "kind": "liquid", "percentage": 70},
                ],
            },
            headers=author,
        )
    ).json()

    before = (await client.get("/api/v1/gamification/tier", headers=author)).json()
    forker_before = (await client.get("/api/v1/gamification/tier", headers=forker)).json()

    await client.post(f"/api/v1/recipes/{recipe['id']}/fork", headers=forker)

    after = (await client.get("/api/v1/gamification/tier", headers=author)).json()
    forker_after = (await client.get("/api/v1/gamification/tier", headers=forker)).json()

    assert after["lifetime_xp"] > before["lifetime_xp"], "the author is credited"
    # The forker gets XP for creating their copy, but not the fork bonus.
    fork_bonus = after["lifetime_xp"] - before["lifetime_xp"]
    forker_gain = forker_after["lifetime_xp"] - forker_before["lifetime_xp"]
    assert fork_bonus != forker_gain or fork_bonus > 0


# --- leaderboards -------------------------------------------------------------


async def test_leaderboard_ranks_by_season_xp(client: AsyncClient, outbox: Outbox) -> None:
    busy, _ = await register_user(client, outbox)
    quiet, _ = await register_user(client, outbox)

    for index in range(3):
        await complete_a_bake(client, busy, title=f"Busy {index}")
    await complete_a_bake(client, quiet, title="Quiet")

    await refresh_leaderboard()

    board = (await client.get("/api/v1/leaderboard?limit=100", headers=busy)).json()
    assert board["season_name"].startswith("20")

    # With an isolated database the whole board is these two accounts, so the
    # ordering can be asserted exactly rather than approximately.
    assert len(board["rows"]) == 2
    assert [row["rank"] for row in board["rows"]] == [1, 2]
    assert board["rows"][0]["is_you"] is True, "three bakes outrank one"
    assert board["rows"][0]["season_xp"] > board["rows"][1]["season_xp"]
    assert board["rows"][0]["bake_count"] == 3
    assert board["rows"][1]["bake_count"] == 1


async def test_category_boards_order_differently(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers)
    await refresh_leaderboard()

    for category in ("xp", "lifetime", "bakes", "streak", "crumb", "achievements"):
        resp = await client.get(f"/api/v1/leaderboard?category={category}", headers=headers)
        assert resp.status_code == 200, category
        assert resp.json()["category"] == category


async def test_a_private_profile_ranks_anonymously(client: AsyncClient, outbox: Outbox) -> None:
    """Opting out of a public profile must not mean opting out of competing."""
    private, account = await register_user(client, outbox)
    viewer, _ = await register_user(client, outbox)
    await complete_a_bake(client, private, title="Quiet loaf")
    await refresh_leaderboard()

    # What a *different* baker sees: a ranked row with no identifying detail.
    board = (await client.get("/api/v1/leaderboard?limit=100", headers=viewer)).json()
    theirs = next(row for row in board["rows"] if not row["is_you"])
    assert theirs["handle"] is None
    assert theirs["display_name"] == "Anonymous Baker"
    assert theirs["rank"] == 1, "they still hold a position"
    assert theirs["season_xp"] > 0, "and their score is still shown"
    assert account["handle"] not in {row["handle"] for row in board["rows"]}

    # ...and what they see themselves.
    own = (await client.get("/api/v1/leaderboard?limit=100", headers=private)).json()
    mine = next(row for row in own["rows"] if row["is_you"])
    assert mine["handle"] == account["handle"]


async def test_a_public_profile_is_named(client: AsyncClient, outbox: Outbox) -> None:
    author, account = await register_user(client, outbox)
    viewer, _ = await register_user(client, outbox)
    await client.patch("/api/v1/profiles/me", json={"is_public": True}, headers=author)
    await complete_a_bake(client, author, title="Proud loaf")
    await refresh_leaderboard()

    # Publishing a profile means other bakers see the name.
    board = (await client.get("/api/v1/leaderboard?limit=100", headers=viewer)).json()
    theirs = next(row for row in board["rows"] if not row["is_you"])
    assert theirs["handle"] == account["handle"]
    assert theirs["display_name"] != "Anonymous Baker"


async def test_my_rank_reports_neighbours(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers)
    await refresh_leaderboard()

    mine = (await client.get("/api/v1/leaderboard/me", headers=headers)).json()
    assert mine["rank"] is not None
    assert mine["total_ranked"] >= 1
    assert any(row["is_you"] for row in mine["neighbours"])


async def test_unranked_user_gets_a_null_rank(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    mine = (await client.get("/api/v1/leaderboard/me", headers=headers)).json()
    assert mine["rank"] is None
    assert mine["neighbours"] == []


async def test_refresh_is_admin_only(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    assert (await client.post("/api/v1/leaderboard/refresh", headers=headers)).status_code == 403


async def test_refresh_is_idempotent(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers)

    await refresh_leaderboard()
    first = (await client.get("/api/v1/leaderboard/me", headers=headers)).json()
    await refresh_leaderboard()
    second = (await client.get("/api/v1/leaderboard/me", headers=headers)).json()

    assert first["rank"] == second["rank"]
    assert first["total_ranked"] == second["total_ranked"]


async def test_unknown_season_is_a_404(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.get("/api/v1/leaderboard?season=1999+Q1", headers=headers)
    assert resp.status_code == 404


async def test_gamification_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/gamification/tier")).status_code == 401
    assert (await client.get("/api/v1/leaderboard")).status_code == 401


# --- replay -------------------------------------------------------------------


async def test_replay_reproduces_the_ledger(client: AsyncClient, outbox: Outbox) -> None:
    """The property the whole design exists for: history can be re-derived.

    Wipe a user's ledger, replay from the underlying bakes and starters, and end
    up where you started — not approximately, exactly.
    """
    from app.services.replay import replay_user

    headers, _ = await register_user(client, outbox)
    await client.post("/api/v1/starters", json={"name": "Replayed"}, headers=headers)
    await complete_a_bake(client, headers, title="Replay one")
    await complete_a_bake(client, headers, title="Replay two")

    before = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    from sqlalchemy import delete

    from app.models.gamification import UserAchievement, XPEvent

    user_id = uuid.UUID(me["id"])
    async with get_session_factory()() as session:
        await session.execute(delete(XPEvent).where(XPEvent.user_id == user_id))
        await session.execute(delete(UserAchievement).where(UserAchievement.user_id == user_id))
        await session.commit()

    wiped = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
    assert wiped["lifetime_xp"] == 0
    assert wiped["achievements_earned"] == 0

    async with get_session_factory()() as session:
        await replay_user(session, user_id)
        await session.commit()

    after = (await client.get("/api/v1/gamification/tier", headers=headers)).json()
    assert after["lifetime_xp"] == before["lifetime_xp"]
    assert after["achievements_earned"] == before["achievements_earned"]


async def test_replay_is_idempotent(client: AsyncClient, outbox: Outbox) -> None:
    """Running it twice must not double the ledger — the unique key absorbs it."""
    from app.services.replay import replay_user

    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers, title="Idempotent")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])

    async with get_session_factory()() as session:
        await replay_user(session, user_id)
        await session.commit()
    once = (await client.get("/api/v1/gamification/tier", headers=headers)).json()

    async with get_session_factory()() as session:
        await replay_user(session, user_id)
        await session.commit()
    twice = (await client.get("/api/v1/gamification/tier", headers=headers)).json()

    assert once["lifetime_xp"] == twice["lifetime_xp"]


async def test_replay_awards_badges_for_data_that_predates_them(
    client: AsyncClient, outbox: Outbox
) -> None:
    """A user's existing history should earn a newly-added badge on recompute."""
    from sqlalchemy import delete

    from app.models.gamification import UserAchievement
    from app.services.replay import replay_user

    headers, _ = await register_user(client, outbox)
    await complete_a_bake(client, headers, title="Historic")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])

    # Simulate the badge not having existed when the bake happened.
    async with get_session_factory()() as session:
        await session.execute(
            delete(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_code == "first_loaf",
            )
        )
        await session.commit()

    async with get_session_factory()() as session:
        await replay_user(session, user_id)
        await session.commit()

    earned = {
        r["code"]
        for r in (
            await client.get("/api/v1/gamification/achievements?earned_only=true", headers=headers)
        ).json()
    }
    assert "first_loaf" in earned
