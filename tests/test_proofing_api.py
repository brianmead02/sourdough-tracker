"""Proof session endpoints against live Postgres and Redis."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ago(**kwargs: float) -> datetime:
    return datetime.now(UTC) - timedelta(**kwargs)


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def start_proof(client: AsyncClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    body = {"stage": "bulk", "dough_temp_c": 24, "starter_pct": 20} | overrides
    resp = await client.post("/api/v1/proofing/sessions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# --- estimate -----------------------------------------------------------------


async def test_estimate_needs_no_session(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/proofing/estimate",
        json={"stage": "bulk", "dough_temp_c": 24, "starter_pct": 20},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hours"] > 0
    assert body["earliest_hours"] < body["hours"] < body["latest_hours"]


async def test_estimate_reflects_temperature(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)

    async def hours(temp: float) -> float:
        resp = await client.post(
            "/api/v1/proofing/estimate",
            json={"stage": "bulk", "dough_temp_c": temp},
            headers=headers,
        )
        return float(resp.json()["hours"])

    assert await hours(28) < await hours(24) < await hours(18) < await hours(4)


async def test_estimate_rejects_a_time_based_stage(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/proofing/estimate",
        json={"stage": "autolyse", "dough_temp_c": 24},
        headers=headers,
    )
    assert resp.status_code == 422


# --- starting sessions --------------------------------------------------------


async def test_start_session_predicts_a_window(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers)

    started = parse(proof["started_at"])
    predicted = parse(proof["predicted_end_at"])
    assert predicted > started
    assert parse(proof["window_start_at"]) < predicted < parse(proof["window_end_at"])
    assert proof["status"] == "running"
    assert proof["target_rise_pct"] == 75.0  # the stage default for bulk


async def test_stage_defaults_differ(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bulk = await start_proof(client, headers, stage="bulk")
    shaped = await start_proof(client, headers, stage="shaped")
    assert bulk["target_rise_pct"] > shaped["target_rise_pct"]


async def test_autolyse_is_time_based_with_no_spread(client: AsyncClient, outbox: Outbox) -> None:
    """A rest is a fixed length; pretending to predict it would be dishonest."""
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, stage="autolyse")

    assert proof["target_rise_pct"] == 0.0
    assert proof["planned_duration_minutes"] == 45
    started, predicted = parse(proof["started_at"]), parse(proof["predicted_end_at"])
    assert predicted - started == timedelta(minutes=45)
    assert proof["window_start_at"] == proof["window_end_at"] == proof["predicted_end_at"]


async def test_retard_predicts_much_longer_than_room_temperature(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    warm = await start_proof(client, headers, stage="bulk", dough_temp_c=24)
    cold = await start_proof(client, headers, stage="bulk", dough_temp_c=4)

    warm_hours = parse(warm["predicted_end_at"]) - parse(warm["started_at"])
    cold_hours = parse(cold["predicted_end_at"]) - parse(cold["started_at"])
    assert cold_hours > warm_hours * 4


async def test_unverified_user_cannot_start_a_session(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox, verify=False)
    resp = await client.post(
        "/api/v1/proofing/sessions",
        json={"stage": "bulk", "dough_temp_c": 24},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_cannot_attach_someone_elses_starter(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    starter = (await client.post("/api/v1/starters", json={"name": "Theirs"}, headers=owner)).json()

    resp = await client.post(
        "/api/v1/proofing/sessions",
        json={"stage": "bulk", "dough_temp_c": 24, "starter_id": starter["id"]},
        headers=intruder,
    )
    assert resp.status_code == 404


async def test_future_start_is_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/proofing/sessions",
        json={
            "stage": "bulk",
            "dough_temp_c": 24,
            "started_at": iso(datetime.now(UTC) + timedelta(hours=3)),
        },
        headers=headers,
    )
    assert resp.status_code == 422


# --- starter vigour -----------------------------------------------------------


async def test_a_fast_starter_shortens_the_prediction(client: AsyncClient, outbox: Outbox) -> None:
    """Vigour is measured from real peak observations, not asserted by the user."""
    headers, _ = await register_user(client, outbox)
    starter = (
        await client.post("/api/v1/starters", json={"name": "Rocket"}, headers=headers)
    ).json()

    # Fed 6h ago, peaked 4h later than reference would suggest is fast.
    feeding = (
        await client.post(
            f"/api/v1/starters/{starter['id']}/feedings",
            json={
                "fed_at": iso(ago(hours=8)),
                "starter_g": 20,
                "flour_g": 100,
                "water_g": 100,
                "ambient_temp_c": 24,
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/starters/{starter['id']}/observations",
        json={
            "feeding_id": feeding["id"],
            "observed_at": iso(ago(hours=5)),  # peaked in 3 hours
            "peaked": True,
            "rise_multiple": 2.5,
            "dough_temp_c": 24,
        },
        headers=headers,
    )

    with_starter = await start_proof(client, headers, starter_id=starter["id"])
    without = await start_proof(client, headers)

    assert with_starter["vigour_used"] > 1.0
    assert without["vigour_used"] == 1.0
    fast = parse(with_starter["predicted_end_at"]) - parse(with_starter["started_at"])
    baseline = parse(without["predicted_end_at"]) - parse(without["started_at"])
    assert fast < baseline


# --- checks re-fit the prediction ---------------------------------------------


async def test_check_returns_the_updated_session(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=2)))

    resp = await client.post(
        f"/api/v1/proofing/sessions/{proof['id']}/checks",
        json={"rise_pct": 30, "poke_test": "springs_back"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["id"] == proof["id"]


async def test_fast_rising_dough_pulls_the_eta_in(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=2)))
    original = parse(proof["predicted_end_at"])

    # 60% of a 75% target after only 2 hours: well ahead of the model.
    updated = (
        await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": 60},
            headers=headers,
        )
    ).json()
    assert parse(updated["predicted_end_at"]) < original


async def test_sluggish_dough_pushes_the_eta_out(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=3)))
    original = parse(proof["predicted_end_at"])

    updated = (
        await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": 5},
            headers=headers,
        )
    ).json()
    assert parse(updated["predicted_end_at"]) > original


async def test_window_narrows_with_each_check(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=4)))

    widths = []
    # Steady 15%/hour, checked hourly.
    for hours_ago, rise in ((3, 15), (2, 30), (1, 45)):
        resp = await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": rise, "checked_at": iso(ago(hours=hours_ago))},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        widths.append(parse(body["window_end_at"]) - parse(body["window_start_at"]))

    # Relative to the remaining time, confidence improves.
    assert widths == sorted(widths, reverse=True)


async def test_check_can_correct_the_dough_temperature(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, dough_temp_c=24)
    updated = (
        await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": 10, "dough_temp_c": 27},
            headers=headers,
        )
    ).json()
    assert updated["dough_temp_c"] == 27.0


async def test_check_before_the_start_is_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers)
    resp = await client.post(
        f"/api/v1/proofing/sessions/{proof['id']}/checks",
        json={"rise_pct": 10, "checked_at": iso(ago(hours=5))},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_checks_are_listed_in_order(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=4)))
    for hours, rise in ((3, 10), (2, 25), (1, 40)):
        await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": rise, "checked_at": iso(ago(hours=hours))},
            headers=headers,
        )

    checks = (
        await client.get(f"/api/v1/proofing/sessions/{proof['id']}/checks", headers=headers)
    ).json()
    assert [c["rise_pct"] for c in checks] == [10, 25, 40]


# --- lifecycle ----------------------------------------------------------------


async def test_complete_records_the_end_and_a_final_reading(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=5)))

    resp = await client.post(
        f"/api/v1/proofing/sessions/{proof['id']}/complete",
        json={"final_rise_pct": 78},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"
    assert resp.json()["actual_end_at"] is not None

    checks = (
        await client.get(f"/api/v1/proofing/sessions/{proof['id']}/checks", headers=headers)
    ).json()
    assert checks[-1]["rise_pct"] == 78


async def test_abort_marks_the_session_aborted(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers)
    resp = await client.post(f"/api/v1/proofing/sessions/{proof['id']}/abort", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "aborted"


async def test_a_finished_session_accepts_no_more_activity(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers)
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/complete", json={}, headers=headers)

    for path, body in (
        ("checks", {"rise_pct": 10}),
        ("complete", {}),
        ("abort", None),
    ):
        resp = await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/{path}", json=body, headers=headers
        )
        assert resp.status_code == 409, path


# --- listing and active view --------------------------------------------------


async def test_active_route_is_not_shadowed_by_the_id_route(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.get("/api/v1/proofing/sessions/active", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_active_view_carries_countdown_data(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers, started_at=iso(ago(hours=2)))
    await client.post(
        f"/api/v1/proofing/sessions/{proof['id']}/checks",
        json={"rise_pct": 30},
        headers=headers,
    )

    active = (await client.get("/api/v1/proofing/sessions/active", headers=headers)).json()
    assert len(active) == 1
    entry = active[0]
    assert entry["check_count"] == 1
    assert entry["latest_rise_pct"] == 30.0
    assert entry["progress_pct"] == pytest.approx(40.0)  # 30 of a 75 target
    assert entry["hours_remaining"] > 0


async def test_completed_sessions_leave_the_active_view(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    proof = await start_proof(client, headers)
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/complete", json={}, headers=headers)

    assert (await client.get("/api/v1/proofing/sessions/active", headers=headers)).json() == []
    done = await client.get("/api/v1/proofing/sessions?status=done", headers=headers)
    assert len(done.json()) == 1


async def test_sessions_are_isolated_between_users(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    proof = await start_proof(client, owner)
    sid = proof["id"]

    assert (
        await client.get(f"/api/v1/proofing/sessions/{sid}", headers=intruder)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/proofing/sessions/{sid}/checks", json={"rise_pct": 10}, headers=intruder
        )
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/proofing/sessions/{sid}/abort", headers=intruder)
    ).status_code == 404
    assert (await client.get("/api/v1/proofing/sessions", headers=intruder)).json() == []
