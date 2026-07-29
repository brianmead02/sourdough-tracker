"""Scheduling, claiming and delivering reminders."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.notification import (
    ChannelKind,
    DeliveryStatus,
    InAppNotification,
    NotificationChannel,
    NotificationEvent,
    NotificationLog,
    NotificationSettings,
    ScheduledNotification,
)
from app.models.user import User, UserProfile
from app.services.notifications import quiet_hours
from app.services.notifications.catalogue import Urgency, default_channels, spec_for
from app.services.notifications.channels import NOTIFIERS, DeliveryError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DrainResult:
    claimed: int = 0
    sent: int = 0
    deferred: int = 0
    expired: int = 0
    failed: int = 0


# --- scheduling -------------------------------------------------------------


async def schedule(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event: NotificationEvent,
    due_at: datetime,
    dedupe_key: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Queue a reminder, or move an existing one.

    Upsert on `dedupe_key`: a proof checked five times must end with **one**
    pending "ready" reminder at the latest ETA, not five. A reminder that has
    already been sent is left alone — moving it would re-send it.
    """
    values = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "event": event,
        "payload": payload or {},
        "due_at": due_at,
        "dedupe_key": dedupe_key,
        "status": DeliveryStatus.pending,
        "attempts": 0,
    }
    await db.execute(
        insert(ScheduledNotification)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["dedupe_key"],
            set_={
                "due_at": due_at,
                "payload": values["payload"],
                "status": DeliveryStatus.pending,
                "attempts": 0,
                "claimed_at": None,
            },
            where=ScheduledNotification.status.in_(
                [DeliveryStatus.pending, DeliveryStatus.claimed, DeliveryStatus.cancelled]
            ),
        )
    )


async def cancel(db: AsyncSession, dedupe_key: str) -> None:
    """Withdraw a pending reminder — the proof finished, the starter was fed."""
    await db.execute(
        update(ScheduledNotification)
        .where(
            ScheduledNotification.dedupe_key == dedupe_key,
            ScheduledNotification.status.in_([DeliveryStatus.pending, DeliveryStatus.claimed]),
        )
        .values(status=DeliveryStatus.cancelled)
    )


async def cancel_prefix(db: AsyncSession, prefix: str) -> None:
    """Withdraw every pending reminder for a subject, e.g. all of one proof's."""
    await db.execute(
        update(ScheduledNotification)
        .where(
            ScheduledNotification.dedupe_key.startswith(prefix),
            ScheduledNotification.status.in_([DeliveryStatus.pending, DeliveryStatus.claimed]),
        )
        .values(status=DeliveryStatus.cancelled)
    )


# --- draining ---------------------------------------------------------------


async def claim_due(db: AsyncSession, limit: int, now: datetime) -> list[ScheduledNotification]:
    """Take a batch of due reminders.

    `FOR UPDATE SKIP LOCKED` is what makes multiple drainers safe: each claims a
    disjoint set instead of blocking on, or duplicating, the others.
    """
    rows = await db.execute(
        select(ScheduledNotification)
        .where(
            ScheduledNotification.status == DeliveryStatus.pending,
            ScheduledNotification.due_at <= now,
        )
        .order_by(ScheduledNotification.due_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    claimed = list(rows.scalars().all())
    for row in claimed:
        row.status = DeliveryStatus.claimed
        row.claimed_at = now
    await db.flush()
    return claimed


async def _resolve_channels(
    db: AsyncSession, user_id: uuid.UUID, event: NotificationEvent
) -> tuple[list[ChannelKind], NotificationSettings | None, str | None]:
    """Which channel kinds this user wants for this event, plus their timezone."""
    settings_row = await db.get(NotificationSettings, user_id)
    profile = await db.get(UserProfile, user_id)
    timezone = profile.timezone if profile else "UTC"

    if settings_row is not None and event.value in settings_row.preferences:
        wanted = settings_row.preferences[event.value]
        kinds = [ChannelKind(k) for k in wanted if k in set(ChannelKind)]
    else:
        kinds = list(default_channels(event))

    return kinds, settings_row, timezone


async def deliver(db: AsyncSession, notification: ScheduledNotification) -> DrainResult:
    """Send one claimed reminder to every channel the user wants it on."""
    result = DrainResult(claimed=1)
    now = datetime.now(UTC)
    config = get_settings()
    spec = spec_for(notification.event)

    # A reminder nobody can act on any more is worse than silence: it is wrong,
    # and it teaches the baker to distrust the next one.
    if quiet_hours.is_stale(notification.due_at, now, spec.expires_after_hours):
        notification.status = DeliveryStatus.cancelled
        notification.last_error = "expired before delivery"
        result.expired = 1
        return result

    kinds, settings_row, timezone = await _resolve_channels(
        db, notification.user_id, notification.event
    )

    # Routine reminders wait for a civilised hour. Time-critical ones do not —
    # dough does not observe quiet hours.
    if spec.urgency is Urgency.routine and settings_row is not None:
        quiet = quiet_hours.is_quiet(
            now, settings_row.quiet_hours_start, settings_row.quiet_hours_end, timezone
        )
        if quiet:
            notification.due_at = quiet_hours.next_wake_time(
                now, settings_row.quiet_hours_start, settings_row.quiet_hours_end, timezone
            )
            notification.status = DeliveryStatus.pending
            notification.claimed_at = None
            result.deferred = 1
            return result

    title, body = spec.render(notification.payload)
    channels = await _channels_for(db, notification.user_id, kinds)

    any_success = False
    last_error: str | None = None

    for kind, channel in channels:
        notifier = NOTIFIERS[kind]
        try:
            await notifier.send(
                db,
                user_id=notification.user_id,
                channel=channel,
                spec=spec,
                title=title,
                body=body,
                payload=notification.payload,
            )
        except DeliveryError as exc:
            last_error = str(exc)
            logger.warning(
                "delivery failed user=%s event=%s channel=%s: %s",
                notification.user_id,
                notification.event.value,
                kind.value,
                exc,
            )
            db.add(
                NotificationLog(
                    user_id=notification.user_id,
                    scheduled_id=notification.id,
                    event=notification.event,
                    channel_kind=kind,
                    succeeded=False,
                    error=str(exc)[:500],
                    created_at=now,
                )
            )
            if channel is not None:
                channel.consecutive_failures += 1
                # A browser that discarded the subscription is never coming
                # back. Disable rather than retry it forever.
                if exc.permanent or channel.consecutive_failures >= 5:
                    channel.is_enabled = False
        else:
            any_success = True
            if channel is not None:
                channel.consecutive_failures = 0
                channel.last_used_at = now
            db.add(
                NotificationLog(
                    user_id=notification.user_id,
                    scheduled_id=notification.id,
                    event=notification.event,
                    channel_kind=kind,
                    succeeded=True,
                    created_at=now,
                )
            )

    if any_success or not channels:
        notification.status = DeliveryStatus.sent
        notification.sent_at = now
        result.sent = 1
        return result

    notification.attempts += 1
    notification.last_error = (last_error or "no channel succeeded")[:500]
    if notification.attempts >= config.notification_max_attempts:
        notification.status = DeliveryStatus.failed
        result.failed = 1
    else:
        # Exponential backoff: 1, 2, 4 minutes.
        delay = config.notification_retry_base_seconds * (2 ** (notification.attempts - 1))
        notification.status = DeliveryStatus.pending
        notification.claimed_at = None
        notification.due_at = now + timedelta(seconds=delay)
        result.deferred = 1
    return result


async def _channels_for(
    db: AsyncSession, user_id: uuid.UUID, kinds: list[ChannelKind]
) -> list[tuple[ChannelKind, NotificationChannel | None]]:
    """Pair each wanted kind with the user's configured destinations.

    `inapp` needs no configuration — everyone has an inbox.
    """
    if not kinds:
        return []

    rows = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user_id,
            NotificationChannel.kind.in_(kinds),
            NotificationChannel.is_enabled.is_(True),
        )
    )
    configured = list(rows.scalars().all())

    pairs: list[tuple[ChannelKind, NotificationChannel | None]] = []
    for kind in kinds:
        if kind is ChannelKind.inapp:
            pairs.append((kind, None))
            continue
        pairs.extend((kind, channel) for channel in configured if channel.kind is kind)
    return pairs


async def drain(
    db: AsyncSession, limit: int | None = None, now: datetime | None = None
) -> DrainResult:
    """One pass of the beat tick."""
    config = get_settings()
    moment = now or datetime.now(UTC)
    batch = limit or config.notification_batch_size

    total = DrainResult()
    for notification in await claim_due(db, batch, moment):
        outcome = await deliver(db, notification)
        total.claimed += outcome.claimed
        total.sent += outcome.sent
        total.deferred += outcome.deferred
        total.expired += outcome.expired
        total.failed += outcome.failed

    await db.flush()
    if total.claimed:
        logger.info(
            "drained %d: sent=%d deferred=%d expired=%d failed=%d",
            total.claimed,
            total.sent,
            total.deferred,
            total.expired,
            total.failed,
        )
    return total


# --- immediate delivery -----------------------------------------------------


async def notify_now(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event: NotificationEvent,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> None:
    """Queue something for the very next tick rather than delivering inline.

    Even "immediate" notifications go through the table: it keeps one delivery
    path, one audit trail and one retry policy, and it means a flaky push
    service cannot slow down an API request.
    """
    await schedule(
        db,
        user_id=user_id,
        event=event,
        due_at=datetime.now(UTC),
        dedupe_key=dedupe_key or f"{event.value}:{user_id}:{uuid.uuid4()}",
        payload=payload,
    )


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    rows = await db.execute(
        select(InAppNotification.id).where(
            InAppNotification.user_id == user_id, InAppNotification.read_at.is_(None)
        )
    )
    return len(rows.all())


async def ensure_settings(db: AsyncSession, user: User) -> NotificationSettings:
    """Settings row on demand, so a user never has to opt in to existing."""
    existing = await db.get(NotificationSettings, user.id)
    if existing is not None:
        return existing
    created = NotificationSettings(user_id=user.id, preferences={})
    db.add(created)
    await db.flush()
    return created
