"""Feeding schedule, streak and ratio maths.

Deliberately pure: these take plain values, not ORM objects or sessions, so the
rules can be tested exhaustively without a database.
"""

import enum
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

# A feeding may be this late and still continue the streak. Bakers are not
# machines; a 24h starter fed at hour 30 has not been neglected.
GRACE_FACTOR = 1.5

# Two feedings closer together than this are treated as a duplicate entry rather
# than two events (docs/PLAN.md §7 anti-cheat).
MIN_FEEDING_GAP = timedelta(minutes=30)

# Bounds on `fed_at`, so streaks cannot be manufactured by backdating.
MAX_BACKDATE = timedelta(days=30)
CLOCK_SKEW_ALLOWANCE = timedelta(minutes=5)


class ScheduleStatus(enum.StrEnum):
    never_fed = "never_fed"
    ok = "ok"
    due = "due"
    overdue = "overdue"
    paused = "paused"  # dormant or retired: not on a schedule


@dataclass(slots=True)
class StreakStats:
    current: int
    longest: int
    total_feedings: int
    last_fed_at: datetime | None
    next_due_at: datetime | None
    deadline_at: datetime | None
    is_alive: bool


@dataclass(slots=True)
class ScheduleEntry:
    status: ScheduleStatus
    last_fed_at: datetime | None
    next_due_at: datetime | None
    hours_until_due: float | None


def _interval(interval_hours: int) -> timedelta:
    return timedelta(hours=interval_hours)


def compute_streak(
    fed_times: Sequence[datetime], interval_hours: int, now: datetime
) -> StreakStats:
    """Consecutive on-time feedings, counted in scheduled intervals, not calendar days.

    Counting intervals rather than days is what makes a fridge-kept starter work:
    set its interval to a week and a weekly feed keeps the streak, while a daily
    starter still has to be fed daily.
    """
    if not fed_times:
        return StreakStats(
            current=0,
            longest=0,
            total_feedings=0,
            last_fed_at=None,
            next_due_at=None,
            deadline_at=None,
            is_alive=False,
        )

    times = sorted(fed_times)
    limit = _interval(interval_hours) * GRACE_FACTOR

    longest = run = 1
    for previous, current_time in itertools.pairwise(times):
        run = run + 1 if current_time - previous <= limit else 1
        longest = max(longest, run)

    last = times[-1]
    next_due = last + _interval(interval_hours)
    deadline = last + limit
    is_alive = now <= deadline

    # After the loop `run` is the length of the run ending at the most recent
    # feeding — which is the current streak, provided it has not lapsed.
    current = run if is_alive else 0

    return StreakStats(
        current=current,
        longest=longest,
        total_feedings=len(times),
        last_fed_at=last,
        next_due_at=next_due,
        deadline_at=deadline,
        is_alive=is_alive,
    )


def compute_schedule(
    last_fed_at: datetime | None,
    interval_hours: int,
    now: datetime,
    *,
    on_schedule: bool = True,
) -> ScheduleEntry:
    """Where a single starter stands right now.

    `overdue` is aligned with the streak-breaking deadline, so the schedule and
    the streak can never disagree about whether a starter was neglected.
    """
    if not on_schedule:
        return ScheduleEntry(
            status=ScheduleStatus.paused,
            last_fed_at=last_fed_at,
            next_due_at=None,
            hours_until_due=None,
        )

    if last_fed_at is None:
        return ScheduleEntry(
            status=ScheduleStatus.never_fed,
            last_fed_at=None,
            next_due_at=None,
            hours_until_due=None,
        )

    next_due = last_fed_at + _interval(interval_hours)
    deadline = last_fed_at + _interval(interval_hours) * GRACE_FACTOR
    hours_until_due = (next_due - now).total_seconds() / 3600

    if now < next_due:
        status = ScheduleStatus.ok
    elif now < deadline:
        status = ScheduleStatus.due
    else:
        status = ScheduleStatus.overdue

    return ScheduleEntry(
        status=status,
        last_fed_at=last_fed_at,
        next_due_at=next_due,
        hours_until_due=round(hours_until_due, 2),
    )


@dataclass(slots=True)
class SuggestedFeed:
    starter_g: float
    flour_g: float
    water_g: float
    total_g: float
    hydration_pct: float


def suggest_feed(
    ratio_starter: int,
    ratio_flour: int,
    ratio_water: int,
    *,
    starter_g: float | None = None,
    total_g: float | None = None,
) -> SuggestedFeed:
    """Scale the feed ratio to either a starter weight or a target total weight."""
    if (starter_g is None) == (total_g is None):
        raise ValueError("provide exactly one of starter_g or total_g")

    parts = ratio_starter + ratio_flour + ratio_water
    if starter_g is None:
        assert total_g is not None
        starter_g = total_g * ratio_starter / parts

    flour_g = starter_g * ratio_flour / ratio_starter
    water_g = starter_g * ratio_water / ratio_starter

    return SuggestedFeed(
        starter_g=round(starter_g, 1),
        flour_g=round(flour_g, 1),
        water_g=round(water_g, 1),
        total_g=round(starter_g + flour_g + water_g, 1),
        hydration_pct=round(ratio_water / ratio_flour * 100, 1),
    )


def validate_fed_at(fed_at: datetime, now: datetime) -> None:
    """Reject timestamps that would let a user manufacture a streak."""
    if fed_at > now + CLOCK_SKEW_ALLOWANCE:
        raise ValueError("fed_at cannot be in the future")
    if fed_at < now - MAX_BACKDATE:
        raise ValueError(f"fed_at cannot be more than {MAX_BACKDATE.days} days in the past")
