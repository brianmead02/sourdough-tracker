"""Reminder scheduling, draining and delivery against live Postgres."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.db import get_session_factory
from app.models.notification import DeliveryStatus, NotificationEvent
from app.services.notifications import drain, schedule
from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ago(**kwargs: float) -> datetime:
    return datetime.now(UTC) - timedelta(**kwargs)


async def run_drain(now: datetime | None = None) -> Any:
    """Run one beat tick — in production this is the 60-second cron."""
    async with get_session_factory()() as session:
        result = await drain(session, now=now)
        await session.commit()
    return result


async def scheduled_for(client: AsyncClient, headers: Headers) -> list[dict[str, Any]]:
    return list((await client.get("/api/v1/notifications/scheduled", headers=headers)).json())


async def inbox(client: AsyncClient, headers: Headers) -> dict[str, Any]:
    return dict((await client.get("/api/v1/notifications/inbox", headers=headers)).json())


# --- scheduling from the domain ----------------------------------------------


async def test_starting_a_proof_schedules_a_ready_reminder(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    proof = (
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24},
            headers=headers,
        )
    ).json()

    queued = await scheduled_for(client, headers)
    ready = [q for q in queued if q["event"] == "proof.ready"]
    assert len(ready) == 1
    assert ready[0]["due_at"] == proof["predicted_end_at"]


async def test_a_check_moves_the_reminder_rather_than_adding_one(
    client: AsyncClient, outbox: Outbox
) -> None:
    """The Phase 3 seam paying off: one pending reminder, at the latest ETA."""
    headers, _ = await register_user(client, outbox)
    proof = (
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24, "started_at": iso(ago(hours=2))},
            headers=headers,
        )
    ).json()
    original_due = (await scheduled_for(client, headers))[0]["due_at"]

    for rise in (20, 40, 60):
        await client.post(
            f"/api/v1/proofing/sessions/{proof['id']}/checks",
            json={"rise_pct": rise},
            headers=headers,
        )

    queued = [q for q in await scheduled_for(client, headers) if q["event"] == "proof.ready"]
    assert len(queued) == 1, "three checks must not queue three reminders"
    assert queued[0]["due_at"] != original_due, "the ETA moved, so the reminder moved"


async def test_retard_gets_its_own_reminder(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await client.post(
        "/api/v1/proofing/sessions",
        json={"stage": "retard", "dough_temp_c": 4},
        headers=headers,
    )
    events = {q["event"] for q in await scheduled_for(client, headers)}
    assert "proof.retard_remove" in events


async def test_finishing_a_proof_withdraws_the_reminder(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    proof = (
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/complete", json={}, headers=headers)

    ready = [q for q in await scheduled_for(client, headers) if q["event"] == "proof.ready"]
    assert ready and ready[0]["status"] == "cancelled"


async def test_aborting_a_proof_withdraws_the_reminder(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    proof = (
        await client.post(
            "/api/v1/proofing/sessions",
            json={"stage": "bulk", "dough_temp_c": 24},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/proofing/sessions/{proof['id']}/abort", headers=headers)

    ready = [q for q in await scheduled_for(client, headers) if q["event"] == "proof.ready"]
    assert ready and ready[0]["status"] == "cancelled"


async def test_feeding_schedules_the_next_feed_reminder(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    starter = (
        await client.post(
            "/api/v1/starters", json={"name": "Gerald", "feed_interval_hours": 24}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/v1/starters/{starter['id']}/feedings",
        json={"starter_g": 20, "flour_g": 100, "water_g": 100},
        headers=headers,
    )

    queued = [q for q in await scheduled_for(client, headers) if q["event"] == "starter.feed_due"]
    assert len(queued) == 1
    due = datetime.fromisoformat(queued[0]["due_at"])
    assert timedelta(hours=23) < due - datetime.now(UTC) < timedelta(hours=25)


async def test_feeding_again_moves_the_reminder(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    starter = (
        await client.post("/api/v1/starters", json={"name": "Gerald"}, headers=headers)
    ).json()
    for hours in (30, 5):
        await client.post(
            f"/api/v1/starters/{starter['id']}/feedings",
            json={"fed_at": iso(ago(hours=hours)), "starter_g": 20, "flour_g": 100, "water_g": 100},
            headers=headers,
        )

    queued = [q for q in await scheduled_for(client, headers) if q["event"] == "starter.feed_due"]
    assert len(queued) == 1, "one reminder per starter, moved not duplicated"


async def test_low_stock_after_a_bake_queues_a_warning(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    item = (
        await client.post(
            "/api/v1/inventory/items",
            json={"name": "bread flour", "kind": "flour", "low_threshold_g": 5000},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "purchase", "quantity_g": 5500, "unit_cost_per_kg": 2.0},
        headers=headers,
    )
    bake = (
        await client.post(
            "/api/v1/bakes",
            json={
                "title": "Drains stock",
                "total_flour_g": 1000,
                "flour_blend": {"bread flour": 100},
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)

    queued = [q for q in await scheduled_for(client, headers) if q["event"] == "inventory.low"]
    assert len(queued) == 1


async def test_earning_a_badge_queues_an_inbox_notification(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = (await client.post("/api/v1/bakes", json={"title": "First"}, headers=headers)).json()
    await client.post(
        f"/api/v1/bakes/{bake['id']}/complete", json={"consume_inventory": False}, headers=headers
    )

    queued = [q for q in await scheduled_for(client, headers) if q["event"] == "achievement.earned"]
    assert queued


# --- draining -----------------------------------------------------------------


async def test_draining_delivers_to_the_inbox(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:deliver",
            payload={"starter_name": "Gerald"},
        )
        await session.commit()

    result = await run_drain()
    assert result.sent >= 1

    page = await inbox(client, headers)
    assert page["unread_count"] == 1
    assert "Gerald" in page["items"][0]["title"]


async def test_a_future_reminder_is_left_alone(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=datetime.now(UTC) + timedelta(hours=5),
            dedupe_key=f"test:{me['id']}:future",
            payload={"starter_name": "Later"},
        )
        await session.commit()

    await run_drain()
    assert (await inbox(client, headers))["unread_count"] == 0


async def test_draining_twice_does_not_deliver_twice(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:once",
            payload={"starter_name": "Once"},
        )
        await session.commit()

    await run_drain()
    await run_drain()
    assert (await inbox(client, headers))["unread_count"] == 1


async def test_a_stale_reminder_is_dropped_rather_than_sent_late(
    client: AsyncClient, outbox: Outbox
) -> None:
    """A "your dough is ready" eight hours late is wrong, not merely late."""
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.proof_ready,
            due_at=ago(hours=10),  # spec expires after 6
            dedupe_key=f"test:{me['id']}:stale",
            payload={"stage": "bulk", "target_rise_pct": 75},
        )
        await session.commit()

    result = await run_drain()
    assert result.expired >= 1
    assert (await inbox(client, headers))["unread_count"] == 0

    queued = [q for q in await scheduled_for(client, headers) if "stale" in q["dedupe_key"]]
    assert queued[0]["status"] == "cancelled"


# --- quiet hours --------------------------------------------------------------


async def test_quiet_hours_defer_a_routine_reminder(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    # A window covering every hour of the day except one, so "now" is inside it.
    now = datetime.now(UTC)
    await client.put(
        "/api/v1/notifications/settings",
        json={"quiet_hours_start": now.hour, "quiet_hours_end": (now.hour + 23) % 24},
        headers=headers,
    )

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:quiet",
            payload={"starter_name": "Shhh"},
        )
        await session.commit()

    result = await run_drain()
    assert result.deferred >= 1
    assert (await inbox(client, headers))["unread_count"] == 0

    queued = [q for q in await scheduled_for(client, headers) if "quiet" in q["dedupe_key"]]
    assert queued[0]["status"] == "pending", "deferred, not dropped"
    assert datetime.fromisoformat(queued[0]["due_at"]) > datetime.now(UTC)


async def test_quiet_hours_do_not_hold_back_the_dough(client: AsyncClient, outbox: Outbox) -> None:
    """Time-critical reminders ignore quiet hours — dough does not sleep."""
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    now = datetime.now(UTC)
    await client.put(
        "/api/v1/notifications/settings",
        json={"quiet_hours_start": now.hour, "quiet_hours_end": (now.hour + 23) % 24},
        headers=headers,
    )

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.proof_ready,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:urgent",
            payload={"stage": "bulk", "target_rise_pct": 75},
        )
        await session.commit()

    await run_drain()
    assert (await inbox(client, headers))["unread_count"] == 1


# --- preferences and channels -------------------------------------------------


async def test_settings_round_trip(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.put(
        "/api/v1/notifications/settings",
        json={
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
            "preferences": {"starter.feed_due": ["inapp"]},
            "digest_enabled": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quiet_hours_start"] == 22
    assert body["preferences"]["starter.feed_due"] == ["inapp"]
    assert body["digest_enabled"] is False
    assert "timezone" in body


async def test_unknown_events_are_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.put(
        "/api/v1/notifications/settings",
        json={"preferences": {"bread.explodes": ["inapp"]}},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_opting_out_of_a_channel_is_honoured(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    await client.put(
        "/api/v1/notifications/settings",
        json={"preferences": {"starter.feed_due": []}},
        headers=headers,
    )

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:optout",
            payload={"starter_name": "Silent"},
        )
        await session.commit()

    await run_drain()
    assert (await inbox(client, headers))["unread_count"] == 0


async def test_event_catalogue_is_published(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    events = (await client.get("/api/v1/notifications/events", headers=headers)).json()
    by_event = {e["event"]: e for e in events}
    assert by_event["proof.ready"]["ignores_quiet_hours"] is True
    assert by_event["inventory.low"]["ignores_quiet_hours"] is False


async def test_ntfy_channel_can_be_registered_and_removed(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    created = await client.post(
        "/api/v1/notifications/channels/ntfy",
        json={"topic": "my-secret-topic", "label": "Phone"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["target"] == "my-secret-topic"

    listed = (await client.get("/api/v1/notifications/channels", headers=headers)).json()
    assert len(listed) == 1

    assert (
        await client.delete(
            f"/api/v1/notifications/channels/{created.json()['id']}", headers=headers
        )
    ).status_code == 204
    assert (await client.get("/api/v1/notifications/channels", headers=headers)).json() == []


async def test_resubscribing_updates_rather_than_duplicates(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    for label in ("Phone", "Phone again"):
        await client.post(
            "/api/v1/notifications/channels/ntfy",
            json={"topic": "same-topic", "label": label},
            headers=headers,
        )
    listed = (await client.get("/api/v1/notifications/channels", headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["label"] == "Phone again"


async def test_email_channel_must_be_your_own_address(client: AsyncClient, outbox: Outbox) -> None:
    """Otherwise this endpoint is a way to make the service mail strangers."""
    headers, account = await register_user(client, outbox)
    bad = await client.post(
        "/api/v1/notifications/channels/email",
        json={"address": "someone-else@example.com"},
        headers=headers,
    )
    assert bad.status_code == 422

    good = await client.post(
        "/api/v1/notifications/channels/email",
        json={"address": account["email"]},
        headers=headers,
    )
    assert good.status_code == 201


async def test_channels_are_isolated_between_users(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    channel = (
        await client.post(
            "/api/v1/notifications/channels/ntfy", json={"topic": "theirs"}, headers=owner
        )
    ).json()

    assert (
        await client.delete(f"/api/v1/notifications/channels/{channel['id']}", headers=intruder)
    ).status_code == 404
    assert (await client.get("/api/v1/notifications/channels", headers=intruder)).json() == []


async def test_webpush_availability_matches_the_configuration(
    client: AsyncClient, outbox: Outbox
) -> None:
    """Unconfigured Web Push means the channel is *absent*, not broken.

    Asserted against whatever this instance is configured with, rather than
    assuming keys are unset — otherwise the suite fails on any deployment that
    has actually turned Web Push on.
    """
    from app.config import get_settings

    headers, _ = await register_user(client, outbox)
    configured = bool(get_settings().vapid_public_key and get_settings().vapid_private_key)

    key = (await client.get("/api/v1/notifications/vapid-key", headers=headers)).json()
    assert key["available"] is configured
    assert bool(key["public_key"]) is configured

    resp = await client.post(
        "/api/v1/notifications/webpush/subscribe",
        json={"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}},
        headers=headers,
    )
    if configured:
        assert resp.status_code == 201
        assert resp.json()["kind"] == "webpush"
    else:
        # A clear 503 beats accepting a subscription that can never be delivered.
        assert resp.status_code == 503


async def test_webpush_subscription_needs_both_keys(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/notifications/webpush/subscribe",
        json={"endpoint": "https://push.example/abc", "keys": {"p256dh": "x"}},
        headers=headers,
    )
    assert resp.status_code == 422


# --- inbox --------------------------------------------------------------------


async def test_marking_read_clears_the_count(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        for index in range(3):
            await schedule(
                session,
                user_id=uuid.UUID(me["id"]),
                event=NotificationEvent.starter_feed_due,
                due_at=ago(minutes=1),
                dedupe_key=f"test:{me['id']}:read{index}",
                payload={"starter_name": f"S{index}"},
            )
        await session.commit()
    await run_drain()

    page = await inbox(client, headers)
    assert page["unread_count"] == 3

    one = await client.post(
        "/api/v1/notifications/inbox/read",
        json={"ids": [page["items"][0]["id"]]},
        headers=headers,
    )
    assert one.json()["unread_count"] == 2

    everything = await client.post(
        "/api/v1/notifications/inbox/read", json={"all": True}, headers=headers
    )
    assert everything.json()["unread_count"] == 0


async def test_mark_read_needs_something_to_do(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post("/api/v1/notifications/inbox/read", json={}, headers=headers)
    assert resp.status_code == 422


async def test_inbox_is_isolated_between_users(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    other, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=owner)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:private",
            payload={"starter_name": "Mine"},
        )
        await session.commit()
    await run_drain()

    assert (await inbox(client, owner))["unread_count"] == 1
    assert (await inbox(client, other))["unread_count"] == 0


async def test_test_notification_is_queued(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post("/api/v1/notifications/test", json={}, headers=headers)
    assert resp.status_code == 202

    await run_drain()
    page = await inbox(client, headers)
    assert page["unread_count"] == 1
    assert "Test notification" in page["items"][0]["title"]


async def test_notifications_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/notifications/inbox")).status_code == 401
    assert (await client.get("/api/v1/notifications/settings")).status_code == 401


async def test_delivery_is_logged(client: AsyncClient, outbox: Outbox) -> None:
    """The answer to "it never told me"."""
    from sqlalchemy import select

    from app.models.notification import NotificationLog

    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=f"test:{me['id']}:logged",
            payload={"starter_name": "Logged"},
        )
        await session.commit()
    await run_drain()

    async with get_session_factory()() as session:
        rows = await session.execute(
            select(NotificationLog).where(NotificationLog.user_id == uuid.UUID(me["id"]))
        )
        logs = list(rows.scalars().all())

    assert logs and all(log.succeeded for log in logs)


async def test_a_sent_reminder_is_not_rescheduled_by_a_later_schedule_call(
    client: AsyncClient, outbox: Outbox
) -> None:
    """Re-scheduling an already-delivered reminder would re-send it."""
    headers, _ = await register_user(client, outbox)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    key = f"test:{me['id']}:sent-once"

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=key,
            payload={"starter_name": "Gerald"},
        )
        await session.commit()
    await run_drain()

    async with get_session_factory()() as session:
        await schedule(
            session,
            user_id=uuid.UUID(me["id"]),
            event=NotificationEvent.starter_feed_due,
            due_at=ago(minutes=1),
            dedupe_key=key,
            payload={"starter_name": "Gerald"},
        )
        await session.commit()
    await run_drain()

    assert (await inbox(client, headers))["unread_count"] == 1
    queued = [q for q in await scheduled_for(client, headers) if q["dedupe_key"] == key]
    assert queued[0]["status"] == DeliveryStatus.sent.value
