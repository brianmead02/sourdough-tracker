"""What each reminder is, how urgent it is, and how it reads.

Urgency is the interesting field. **Time-critical reminders ignore quiet
hours**, because a dough that is ready at 3am is ready at 3am — deferring that
notification to a civilised hour delivers a useless message about a loaf that
over-proofed four hours ago. Routine reminders defer.

Getting this wrong in either direction is bad: defer everything and the product
is useless; defer nothing and it wakes people up to tell them flour is low.
"""

import enum
from dataclasses import dataclass
from typing import Any

from app.models.notification import ChannelKind, NotificationEvent


class Urgency(enum.StrEnum):
    # Send now, whatever the hour. The dough does not observe quiet hours.
    time_critical = "time_critical"
    # Hold until quiet hours are over.
    routine = "routine"


@dataclass(frozen=True, slots=True)
class EventSpec:
    event: NotificationEvent
    urgency: Urgency
    title: str
    body: str
    default_channels: tuple[ChannelKind, ...]
    icon: str = "🍞"
    # ntfy renders emoji from *names*, and HTTP headers are ASCII anyway.
    ntfy_tag: str = "bread"
    # Some reminders stop being worth sending once they are stale.
    expires_after_hours: int | None = None

    def render(self, payload: dict[str, Any]) -> tuple[str, str]:
        """Fill the templates, tolerating a payload missing a key."""
        safe = _Forgiving(payload)
        return (
            self.title.format_map(safe),
            self.body.format_map(safe),
        )


class _Forgiving(dict[str, Any]):
    """A missing placeholder should not lose the whole notification."""

    def __missing__(self, key: str) -> str:
        return "—"


SPECS: dict[NotificationEvent, EventSpec] = {
    NotificationEvent.proof_ready: EventSpec(
        event=NotificationEvent.proof_ready,
        urgency=Urgency.time_critical,
        title="{stage} proof is ready",
        body="Your {stage} looks ready — predicted {target_rise_pct}% rise reached.",
        default_channels=(ChannelKind.inapp, ChannelKind.webpush, ChannelKind.ntfy),
        icon="⏰",
        ntfy_tag="alarm_clock",
        expires_after_hours=6,
    ),
    NotificationEvent.proof_retard_remove: EventSpec(
        event=NotificationEvent.proof_retard_remove,
        urgency=Urgency.time_critical,
        title="Time to take the dough out",
        body="Your retard has run its course. Take it out of the fridge when you're ready.",
        default_channels=(ChannelKind.inapp, ChannelKind.webpush, ChannelKind.ntfy),
        icon="❄️",
        ntfy_tag="ice_cube",
        expires_after_hours=12,
    ),
    NotificationEvent.starter_feed_due: EventSpec(
        event=NotificationEvent.starter_feed_due,
        urgency=Urgency.routine,
        title="{starter_name} needs feeding",
        body="{starter_name} is due for a feed.",
        default_channels=(ChannelKind.inapp, ChannelKind.webpush),
        icon="🥄",
        ntfy_tag="spoon",
        expires_after_hours=24,
    ),
    NotificationEvent.starter_streak_at_risk: EventSpec(
        event=NotificationEvent.starter_streak_at_risk,
        urgency=Urgency.routine,
        title="{starter_name}: {streak}-feed streak at risk",
        body="Feed {starter_name} soon to keep a streak of {streak} going.",
        default_channels=(ChannelKind.inapp, ChannelKind.webpush),
        icon="📈",
        ntfy_tag="chart_with_upwards_trend",
        expires_after_hours=12,
    ),
    NotificationEvent.inventory_low: EventSpec(
        event=NotificationEvent.inventory_low,
        urgency=Urgency.routine,
        title="Low stock: {item_name}",
        body="{item_name} is down to {on_hand_g}g.",
        default_channels=(ChannelKind.inapp,),
        icon="📦",
        ntfy_tag="package",
    ),
    NotificationEvent.achievement_earned: EventSpec(
        event=NotificationEvent.achievement_earned,
        urgency=Urgency.routine,
        title="{icon} {name}",
        body="{description} (+{xp_award} XP)",
        default_channels=(ChannelKind.inapp,),
        icon="🏅",
        ntfy_tag="medal_sports",
    ),
    NotificationEvent.weekly_digest: EventSpec(
        event=NotificationEvent.weekly_digest,
        urgency=Urgency.routine,
        title="Your baking week",
        body=(
            "{bakes} bakes, {feedings} feedings, {xp} XP this week. "
            "You're ranked #{rank} this season."
        ),
        default_channels=(ChannelKind.inapp, ChannelKind.email),
        icon="📊",
        ntfy_tag="bar_chart",
    ),
}


def spec_for(event: NotificationEvent) -> EventSpec:
    return SPECS[event]


def default_channels(event: NotificationEvent) -> tuple[ChannelKind, ...]:
    return SPECS[event].default_channels


# Every event must be catalogued — a scheduled reminder with no spec cannot be
# rendered. A unit test asserts this rather than leaving it to production.
