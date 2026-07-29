"""Quiet hours, staleness and the reminder catalogue. Pure — no database."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.notification import ChannelKind, NotificationEvent
from app.services.notifications.catalogue import SPECS, Urgency, spec_for
from app.services.notifications.channels import ascii_header, target_hash
from app.services.notifications.quiet_hours import (
    is_quiet,
    is_stale,
    next_wake_time,
    resolve_timezone,
)


def utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 28, hour, minute, tzinfo=UTC)


# --- quiet hours --------------------------------------------------------------


def test_no_window_configured_is_never_quiet() -> None:
    assert is_quiet(utc(3), None, None, "UTC") is False
    assert is_quiet(utc(3), 22, None, "UTC") is False


def test_identical_bounds_are_not_a_24_hour_window() -> None:
    """22-22 means "unset", not "silence me forever"."""
    assert is_quiet(utc(3), 22, 22, "UTC") is False


@pytest.mark.parametrize("hour", [22, 23, 0, 3, 6])
def test_overnight_window_covers_the_night(hour: int) -> None:
    assert is_quiet(utc(hour), 22, 7, "UTC") is True


@pytest.mark.parametrize("hour", [7, 12, 18, 21])
def test_overnight_window_excludes_the_day(hour: int) -> None:
    assert is_quiet(utc(hour), 22, 7, "UTC") is False


def test_daytime_window_does_not_wrap() -> None:
    assert is_quiet(utc(14), 13, 15, "UTC") is True
    assert is_quiet(utc(16), 13, 15, "UTC") is False
    assert is_quiet(utc(3), 13, 15, "UTC") is False


def test_boundaries_are_inclusive_start_exclusive_end() -> None:
    assert is_quiet(utc(22), 22, 7, "UTC") is True
    assert is_quiet(utc(7), 22, 7, "UTC") is False


def test_quiet_hours_are_judged_in_the_users_timezone() -> None:
    """The same instant is quiet for one baker and not for another.

    02:00 UTC on this date is 21:00 in Chicago (CDT, still awake) and 03:00 in
    London (BST, firmly asleep).
    """
    moment = utc(2)
    assert is_quiet(moment, 22, 7, "America/Chicago") is False
    assert is_quiet(moment, 22, 7, "Europe/London") is True


def test_an_unknown_timezone_falls_back_to_utc() -> None:
    """A bad timezone must not stop a reminder."""
    assert resolve_timezone("Mars/Olympus").key == "UTC"
    assert resolve_timezone(None).key == "UTC"
    assert is_quiet(utc(3), 22, 7, "Mars/Olympus") is True


# --- waking up ----------------------------------------------------------------


def test_wake_time_is_the_end_of_the_window() -> None:
    woken = next_wake_time(utc(3), 22, 7, "UTC")
    assert woken == utc(7)


def test_wake_time_crosses_midnight_when_needed() -> None:
    """Queued at 23:00, the window ends at 07:00 *tomorrow*."""
    woken = next_wake_time(utc(23), 22, 7, "UTC")
    assert woken == utc(7) + timedelta(days=1)


def test_wake_time_is_a_no_op_outside_quiet_hours() -> None:
    moment = utc(12)
    assert next_wake_time(moment, 22, 7, "UTC") == moment


def test_wake_time_respects_the_users_timezone() -> None:
    woken = next_wake_time(utc(3), 22, 7, "America/Chicago")
    assert woken > utc(3)
    assert woken.astimezone(resolve_timezone("America/Chicago")).hour == 7


# --- staleness ----------------------------------------------------------------


def test_a_reminder_with_no_expiry_never_goes_stale() -> None:
    assert is_stale(utc(0), utc(0) + timedelta(days=30), None) is False


def test_a_fresh_reminder_is_not_stale() -> None:
    assert is_stale(utc(0), utc(2), 6) is False


def test_a_long_overdue_reminder_is_stale() -> None:
    """Telling someone their dough is ready eight hours late is worse than silence."""
    assert is_stale(utc(0), utc(8), 6) is True


# --- catalogue ----------------------------------------------------------------


def test_every_event_has_a_spec() -> None:
    """A scheduled reminder with no spec cannot be rendered."""
    for event in NotificationEvent:
        assert event in SPECS, event


def test_specs_are_self_consistent() -> None:
    for event, spec in SPECS.items():
        assert spec.event is event
        assert spec.default_channels, f"{event} would go nowhere by default"
        assert spec.title and spec.body


def test_dough_reminders_ignore_quiet_hours() -> None:
    """The dough does not observe quiet hours; deferring these makes them wrong."""
    assert spec_for(NotificationEvent.proof_ready).urgency is Urgency.time_critical
    assert spec_for(NotificationEvent.proof_retard_remove).urgency is Urgency.time_critical


def test_housekeeping_reminders_defer() -> None:
    """Nobody should be woken at 3am to hear that flour is low."""
    for event in (
        NotificationEvent.inventory_low,
        NotificationEvent.starter_feed_due,
        NotificationEvent.weekly_digest,
    ):
        assert spec_for(event).urgency is Urgency.routine


def test_urgent_reminders_reach_a_push_channel_by_default() -> None:
    """A time-critical reminder that only lands in the inbox is useless."""
    for event, spec in SPECS.items():
        if spec.urgency is Urgency.time_critical:
            pushy = {ChannelKind.webpush, ChannelKind.ntfy} & set(spec.default_channels)
            assert pushy, f"{event} is urgent but has no push channel"


def test_rendering_fills_the_templates() -> None:
    spec = spec_for(NotificationEvent.starter_feed_due)
    title, body = spec.render({"starter_name": "Gerald"})
    assert "Gerald" in title
    assert "Gerald" in body


def test_rendering_survives_a_missing_field() -> None:
    """A payload written before a template changed must not lose the message."""
    title, body = spec_for(NotificationEvent.starter_feed_due).render({})
    assert title and body
    assert "{" not in title


# --- channel identity ---------------------------------------------------------


def test_target_hash_is_stable_per_destination() -> None:
    subscription = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}
    assert target_hash(ChannelKind.webpush, subscription) == target_hash(
        ChannelKind.webpush, subscription
    )


def test_target_hash_distinguishes_destinations() -> None:
    a = target_hash(ChannelKind.webpush, {"endpoint": "https://push.example/a"})
    b = target_hash(ChannelKind.webpush, {"endpoint": "https://push.example/b"})
    assert a != b


def test_target_hash_is_case_insensitive_for_email() -> None:
    assert target_hash(ChannelKind.email, {"address": "Me@Example.com"}) == target_hash(
        ChannelKind.email, {"address": "me@example.com"}
    )


def test_target_hash_separates_kinds() -> None:
    assert target_hash(ChannelKind.ntfy, {"topic": "x"}) != target_hash(
        ChannelKind.webpush, {"endpoint": "x"}
    )


# --- header safety ------------------------------------------------------------
#
# ntfy carries the title in an HTTP header, and header values must be ASCII.
# Titles contain user text, so this is not an edge case.


def test_emoji_are_stripped_from_headers() -> None:
    """A raw emoji in a header raises UnicodeEncodeError and loses the whole send."""
    assert ascii_header("⏰ bulk proof is ready").isascii()


def test_accented_names_survive_as_ascii() -> None:
    """A starter called "Gérald" must still produce a readable title."""
    assert ascii_header("Gérald needs feeding") == "Gerald needs feeding"


def test_non_latin_titles_do_not_produce_an_empty_header() -> None:
    """Stripping everything would leave a blank header, so fall back to a name."""
    assert ascii_header("パン") == "Sourdough Tracker"
    assert ascii_header("") == "Sourdough Tracker"


def test_every_spec_has_an_ascii_ntfy_tag() -> None:
    """ntfy takes emoji as names; a raw emoji tag is an un-sendable header."""
    for event, spec in SPECS.items():
        assert spec.ntfy_tag.isascii(), event
        assert spec.ntfy_tag.replace("_", "").isalnum(), event


def test_rendered_titles_are_always_header_safe() -> None:
    """Every template, filled with realistic user text, must survive encoding."""
    payload = {
        "starter_name": "Gérald",
        "item_name": "Röggelchen flour",
        "stage": "bulk",
        "target_rise_pct": 75,
        "streak": 12,
        "on_hand_g": 400,
        "icon": "🏅",
        "name": "Café Baker",
        "description": "Ünicode",
        "xp_award": 50,
        "bakes": 3,
        "feedings": 7,
        "xp": 120,
        "rank": 4,
    }
    for event, spec in SPECS.items():
        title, _ = spec.render(payload)
        assert ascii_header(title).isascii(), event
        assert ascii_header(title), event


# --- dependencies -------------------------------------------------------------


def test_the_web_push_library_is_installed() -> None:
    """Web Push imports lazily, inside the send path.

    That keeps the import cost off every request, but it also means a missing
    dependency stays invisible until the first real push — on an instance that
    has just configured VAPID keys, i.e. exactly when it matters. This test is
    the thing that notices.
    """
    from pywebpush import WebPushException, webpush  # noqa: F401


def test_the_vapid_keygen_dependency_is_installed() -> None:
    """`sdt vapid-keys` is the documented way to configure Web Push."""
    from cryptography.hazmat.primitives.serialization import Encoding  # noqa: F401
    from py_vapid import Vapid01  # noqa: F401
