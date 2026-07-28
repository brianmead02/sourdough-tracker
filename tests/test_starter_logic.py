"""Streak, schedule and ratio maths. Pure functions — no database."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.starters import (
    GRACE_FACTOR,
    ScheduleStatus,
    compute_schedule,
    compute_streak,
    suggest_feed,
    validate_fed_at,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def ago(**kwargs: float) -> datetime:
    return NOW - timedelta(**kwargs)


# --- streaks ------------------------------------------------------------------


def test_no_feedings_is_an_empty_streak() -> None:
    stats = compute_streak([], 24, NOW)
    assert stats.current == 0
    assert stats.longest == 0
    assert stats.total_feedings == 0
    assert stats.last_fed_at is None
    assert stats.is_alive is False


def test_single_feeding_is_a_streak_of_one() -> None:
    stats = compute_streak([ago(hours=1)], 24, NOW)
    assert stats.current == 1
    assert stats.longest == 1
    assert stats.is_alive is True


def test_consecutive_daily_feedings_build_a_streak() -> None:
    feedings = [ago(hours=24 * n) for n in range(5)]
    stats = compute_streak(feedings, 24, NOW)
    assert stats.current == 5
    assert stats.longest == 5
    assert stats.total_feedings == 5


def test_input_order_does_not_matter() -> None:
    feedings = [ago(hours=24 * n) for n in range(5)]
    assert (
        compute_streak(feedings, 24, NOW).current
        == compute_streak(list(reversed(feedings)), 24, NOW).current
    )


def test_a_gap_breaks_the_streak_but_not_the_record() -> None:
    feedings = [
        ago(hours=200),
        ago(hours=176),
        ago(hours=152),  # 3 in a row, then a long gap
        ago(hours=48),
        ago(hours=24),
        ago(hours=2),  # current run of 3
    ]
    stats = compute_streak(feedings, 24, NOW)
    assert stats.current == 3
    assert stats.longest == 3
    assert stats.total_feedings == 6


def test_late_but_within_grace_continues_the_streak() -> None:
    """A 24h starter fed at hour 30 has not been neglected."""
    late = 24 * GRACE_FACTOR - 1
    feedings = [ago(hours=late * 2), ago(hours=late), NOW]
    assert compute_streak(feedings, 24, NOW).current == 3


def test_beyond_grace_breaks_the_streak() -> None:
    too_late = 24 * GRACE_FACTOR + 1
    feedings = [ago(hours=too_late), NOW]
    assert compute_streak(feedings, 24, NOW).current == 1


def test_lapsed_streak_is_zero_but_longest_is_remembered() -> None:
    """Fed daily for a week, then abandoned: the record stands, the streak does not."""
    feedings = [ago(hours=100 + 24 * n) for n in range(7)]
    stats = compute_streak(feedings, 24, NOW)
    assert stats.current == 0
    assert stats.longest == 7
    assert stats.is_alive is False


def test_long_interval_suits_a_fridge_starter() -> None:
    """Weekly feeding keeps a 168h starter's streak alive; a daily one would lapse."""
    weekly = [ago(hours=168 * n) for n in range(4)]
    assert compute_streak(weekly, 168, NOW).current == 4
    assert compute_streak(weekly, 24, NOW).current == 1


# --- schedule -----------------------------------------------------------------


def test_never_fed_starter() -> None:
    entry = compute_schedule(None, 24, NOW)
    assert entry.status is ScheduleStatus.never_fed
    assert entry.next_due_at is None


def test_recently_fed_is_ok_with_hours_remaining() -> None:
    entry = compute_schedule(ago(hours=6), 24, NOW)
    assert entry.status is ScheduleStatus.ok
    assert entry.hours_until_due == pytest.approx(18.0)


def test_past_due_but_within_grace_is_due() -> None:
    entry = compute_schedule(ago(hours=30), 24, NOW)
    assert entry.status is ScheduleStatus.due
    assert entry.hours_until_due is not None and entry.hours_until_due < 0


def test_past_grace_is_overdue() -> None:
    assert compute_schedule(ago(hours=40), 24, NOW).status is ScheduleStatus.overdue


def test_paused_starter_has_no_due_date() -> None:
    entry = compute_schedule(ago(hours=500), 24, NOW, on_schedule=False)
    assert entry.status is ScheduleStatus.paused
    assert entry.next_due_at is None


def test_schedule_and_streak_agree_on_neglect() -> None:
    """`overdue` and a broken streak must be the same instant, or the UI contradicts itself."""
    for hours in (23, 25, 35, 37):
        last = ago(hours=hours)
        overdue = compute_schedule(last, 24, NOW).status is ScheduleStatus.overdue
        broken = compute_streak([last], 24, NOW).current == 0
        assert overdue == broken, f"disagreement at {hours}h"


# --- feed ratios --------------------------------------------------------------


def test_suggest_feed_from_starter_weight() -> None:
    feed = suggest_feed(1, 5, 5, starter_g=20)
    assert (feed.starter_g, feed.flour_g, feed.water_g) == (20.0, 100.0, 100.0)
    assert feed.total_g == 220.0
    assert feed.hydration_pct == 100.0


def test_suggest_feed_from_target_total() -> None:
    feed = suggest_feed(1, 5, 5, total_g=220)
    assert (feed.starter_g, feed.flour_g, feed.water_g) == (20.0, 100.0, 100.0)


def test_stiff_ratio_yields_sub_100_hydration() -> None:
    feed = suggest_feed(1, 2, 1, starter_g=50)
    assert feed.flour_g == 100.0
    assert feed.water_g == 50.0
    assert feed.hydration_pct == 50.0


def test_suggest_feed_requires_exactly_one_basis() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        suggest_feed(1, 5, 5)
    with pytest.raises(ValueError, match="exactly one"):
        suggest_feed(1, 5, 5, starter_g=10, total_g=100)


# --- backdating guards --------------------------------------------------------


def test_fed_at_may_not_be_in_the_future() -> None:
    with pytest.raises(ValueError, match="future"):
        validate_fed_at(NOW + timedelta(hours=1), NOW)


def test_small_clock_skew_is_tolerated() -> None:
    validate_fed_at(NOW + timedelta(minutes=2), NOW)


def test_fed_at_may_not_be_ancient() -> None:
    with pytest.raises(ValueError, match="days in the past"):
        validate_fed_at(NOW - timedelta(days=31), NOW)


def test_recent_backdating_is_allowed() -> None:
    validate_fed_at(NOW - timedelta(days=2), NOW)
