"""Reminder scheduling and multi-channel delivery."""

from app.services.notifications.catalogue import SPECS, EventSpec, Urgency, spec_for
from app.services.notifications.channels import (
    NOTIFIERS,
    DeliveryError,
    target_hash,
    webpush_available,
)
from app.services.notifications.quiet_hours import is_quiet, is_stale, next_wake_time
from app.services.notifications.scheduler import (
    DrainResult,
    cancel,
    cancel_prefix,
    drain,
    ensure_settings,
    notify_now,
    schedule,
    unread_count,
)

__all__ = [
    "NOTIFIERS",
    "SPECS",
    "DeliveryError",
    "DrainResult",
    "EventSpec",
    "Urgency",
    "cancel",
    "cancel_prefix",
    "drain",
    "ensure_settings",
    "is_quiet",
    "is_stale",
    "next_wake_time",
    "notify_now",
    "schedule",
    "spec_for",
    "target_hash",
    "unread_count",
    "webpush_available",
]
