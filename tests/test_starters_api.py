"""Starter, feeding and observation endpoints against live Postgres and Redis."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]

STARTER = {"name": "Bubbles", "flour_type": "rye", "feed_interval_hours": 24}


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ago(**kwargs: float) -> datetime:
    return datetime.now(UTC) - timedelta(**kwargs)


async def create_starter(client: AsyncClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/starters", json=STARTER | overrides, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def feed(client: AsyncClient, headers: Headers, starter_id: str, **overrides: Any) -> Any:
    body = {"starter_g": 20, "flour_g": 100, "water_g": 100} | overrides
    return await client.post(f"/api/v1/starters/{starter_id}/feedings", json=body, headers=headers)


# --- starter CRUD -------------------------------------------------------------


async def test_create_starter_derives_hydration_from_ratio(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers, ratio_starter=1, ratio_flour=2, ratio_water=1)
    assert starter["hydration_pct"] == 50.0
    assert starter["name"] == "Bubbles"


async def test_unverified_user_cannot_create_a_starter(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox, verify=False)
    resp = await client.post("/api/v1/starters", json=STARTER, headers=headers)
    assert resp.status_code == 403


async def test_starters_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/starters")).status_code == 401
    assert (await client.post("/api/v1/starters", json=STARTER)).status_code == 401


async def test_duplicate_name_is_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await create_starter(client, headers)
    dupe = await client.post("/api/v1/starters", json=STARTER, headers=headers)
    assert dupe.status_code == 409


async def test_two_users_may_share_a_starter_name(client: AsyncClient, outbox: Outbox) -> None:
    """Uniqueness is per user, not global."""
    first, _ = await register_user(client, outbox)
    second, _ = await register_user(client, outbox)
    await create_starter(client, first)
    await create_starter(client, second)


async def test_deleting_frees_the_name(client: AsyncClient, outbox: Outbox) -> None:
    """The partial unique index only covers live starters."""
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)

    deleted = await client.delete(f"/api/v1/starters/{starter['id']}", headers=headers)
    assert deleted.status_code == 204

    await create_starter(client, headers)  # same name, no conflict


async def test_deleted_starter_is_gone_from_reads(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    await client.delete(f"/api/v1/starters/{starter['id']}", headers=headers)

    assert (
        await client.get(f"/api/v1/starters/{starter['id']}", headers=headers)
    ).status_code == 404
    listed = await client.get("/api/v1/starters", headers=headers)
    assert listed.json() == []


async def test_update_starter(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    resp = await client.patch(
        f"/api/v1/starters/{starter['id']}",
        json={"state": "fridge", "feed_interval_hours": 168},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "fridge"
    assert resp.json()["feed_interval_hours"] == 168


async def test_retired_starters_are_hidden_unless_requested(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    await client.patch(
        f"/api/v1/starters/{starter['id']}", json={"state": "retired"}, headers=headers
    )

    assert (await client.get("/api/v1/starters", headers=headers)).json() == []
    included = await client.get("/api/v1/starters?include_retired=true", headers=headers)
    assert len(included.json()) == 1


# --- tenant isolation ---------------------------------------------------------


async def test_another_user_cannot_read_or_change_your_starter(
    client: AsyncClient, outbox: Outbox
) -> None:
    """Someone else's starter must 404, not 403 — existence is not disclosed."""
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    starter = await create_starter(client, owner)
    sid = starter["id"]

    assert (await client.get(f"/api/v1/starters/{sid}", headers=intruder)).status_code == 404
    assert (
        await client.patch(f"/api/v1/starters/{sid}", json={"name": "Mine"}, headers=intruder)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/starters/{sid}", headers=intruder)).status_code == 404
    assert (await feed(client, intruder, sid)).status_code == 404
    assert (
        await client.get(f"/api/v1/starters/{sid}/feedings", headers=intruder)
    ).status_code == 404


# --- feedings -----------------------------------------------------------------


async def test_log_feeding_computes_hydration(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    resp = await feed(client, headers, starter["id"], flour_g=100, water_g=80)
    assert resp.status_code == 201, resp.text
    assert resp.json()["hydration_pct"] == 80.0


async def test_duplicate_feeding_within_the_window_is_rejected(
    client: AsyncClient, outbox: Outbox
) -> None:
    """The double-tap guard from the anti-cheat rules."""
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)

    assert (await feed(client, headers, starter["id"])).status_code == 201
    clash = await feed(client, headers, starter["id"], fed_at=iso(ago(minutes=5)))
    assert clash.status_code == 409

    spaced = await feed(client, headers, starter["id"], fed_at=iso(ago(hours=24)))
    assert spaced.status_code == 201


async def test_future_and_ancient_feedings_are_rejected(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)

    future = await feed(
        client, headers, starter["id"], fed_at=iso(datetime.now(UTC) + timedelta(hours=2))
    )
    assert future.status_code == 422

    ancient = await feed(client, headers, starter["id"], fed_at=iso(ago(days=45)))
    assert ancient.status_code == 422


async def test_flour_blend_must_sum_to_100(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)

    bad = await feed(client, headers, starter["id"], flour_blend={"rye": 50, "bread": 30})
    assert bad.status_code == 422

    good = await feed(
        client,
        headers,
        starter["id"],
        flour_blend={"rye": 20, "bread": 80},
        fed_at=iso(ago(hours=30)),
    )
    assert good.status_code == 201
    assert good.json()["flour_blend"] == {"rye": 20, "bread": 80}


async def test_feedings_are_listed_newest_first_and_paginate(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    for hours in (72, 48, 24):
        assert (
            await feed(client, headers, starter["id"], fed_at=iso(ago(hours=hours)))
        ).status_code == 201

    listed = await client.get(f"/api/v1/starters/{starter['id']}/feedings", headers=headers)
    times = [item["fed_at"] for item in listed.json()]
    assert times == sorted(times, reverse=True)

    page = await client.get(
        f"/api/v1/starters/{starter['id']}/feedings?limit=2&offset=2", headers=headers
    )
    assert len(page.json()) == 1


# --- streaks and schedule -----------------------------------------------------


async def test_streak_reflects_logged_feedings(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    for hours in (48, 24, 0):
        await feed(client, headers, starter["id"], fed_at=iso(ago(hours=hours)))

    streak = await client.get(f"/api/v1/starters/{starter['id']}/streak", headers=headers)
    body = streak.json()
    assert body["current"] == 3
    assert body["longest"] == 3
    assert body["total_feedings"] == 3
    assert body["is_alive"] is True


async def test_streak_is_empty_before_any_feeding(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    body = (await client.get(f"/api/v1/starters/{starter['id']}/streak", headers=headers)).json()
    assert body["current"] == 0
    assert body["last_fed_at"] is None


async def test_schedule_route_is_not_shadowed_by_the_id_route(
    client: AsyncClient, outbox: Outbox
) -> None:
    """`/starters/schedule` must resolve to the schedule, not a UUID lookup."""
    headers, _ = await register_user(client, outbox)
    resp = await client.get("/api/v1/starters/schedule", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_schedule_reports_status_and_orders_by_urgency(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)

    fresh = await create_starter(client, headers, name="Fresh")
    await feed(client, headers, fresh["id"])

    neglected = await create_starter(client, headers, name="Neglected")
    await feed(client, headers, neglected["id"], fed_at=iso(ago(hours=40)))

    never = await create_starter(client, headers, name="Never")

    schedule = (await client.get("/api/v1/starters/schedule", headers=headers)).json()
    by_name = {item["name"]: item for item in schedule}

    assert by_name["Fresh"]["status"] == "ok"
    assert by_name["Neglected"]["status"] == "overdue"
    assert by_name["Never"]["status"] == "never_fed"
    assert never["id"] == by_name["Never"]["starter_id"]

    # Never-fed first, then the most overdue.
    assert [item["name"] for item in schedule] == ["Never", "Neglected", "Fresh"]


async def test_paused_starters_are_absent_from_the_schedule(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    await client.patch(
        f"/api/v1/starters/{starter['id']}", json={"state": "dormant"}, headers=headers
    )
    assert (await client.get("/api/v1/starters/schedule", headers=headers)).json() == []


async def test_list_view_carries_schedule_context(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    await feed(client, headers, starter["id"])

    item = (await client.get("/api/v1/starters", headers=headers)).json()[0]
    assert item["status"] == "ok"
    assert item["last_fed_at"] is not None
    assert item["hours_until_due"] == pytest.approx(24, abs=0.1)


# --- observations -------------------------------------------------------------


async def test_log_observation(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    feeding = (await feed(client, headers, starter["id"])).json()

    resp = await client.post(
        f"/api/v1/starters/{starter['id']}/observations",
        json={
            "feeding_id": feeding["id"],
            "rise_multiple": 2.5,
            "peaked": True,
            "float_test_passed": True,
            "aroma": "tangy",
            "dough_temp_c": 24.5,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["aroma"] == "tangy"
    assert resp.json()["feeding_id"] == feeding["id"]


async def test_observation_cannot_reference_another_starters_feeding(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    first = await create_starter(client, headers, name="First")
    second = await create_starter(client, headers, name="Second")
    feeding = (await feed(client, headers, first["id"])).json()

    resp = await client.post(
        f"/api/v1/starters/{second['id']}/observations",
        json={"feeding_id": feeding["id"], "peaked": True},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_observation_rejects_implausible_values(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    resp = await client.post(
        f"/api/v1/starters/{starter['id']}/observations",
        json={"rise_multiple": 50, "dough_temp_c": 200},
        headers=headers,
    )
    assert resp.status_code == 422


# --- suggested feed -----------------------------------------------------------


async def test_suggested_feed_scales_the_ratio(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers, ratio_starter=1, ratio_flour=5, ratio_water=5)

    resp = await client.post(
        f"/api/v1/starters/{starter['id']}/suggested-feed",
        json={"starter_g": 20},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "starter_g": 20.0,
        "flour_g": 100.0,
        "water_g": 100.0,
        "total_g": 220.0,
        "hydration_pct": 100.0,
    }


async def test_suggested_feed_requires_exactly_one_basis(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = await create_starter(client, headers)
    resp = await client.post(
        f"/api/v1/starters/{starter['id']}/suggested-feed",
        json={"starter_g": 20, "total_g": 220},
        headers=headers,
    )
    assert resp.status_code == 422
