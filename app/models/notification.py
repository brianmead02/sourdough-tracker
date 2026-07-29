"""Scheduled reminders, delivery channels, and the in-app inbox.

The scheduling design (docs/PLAN.md §6) is a **table drained by a beat tick**,
not an in-process scheduler, because per-user reminders:

* move — a proof check changes the ETA, so the pending reminder must be
  rescheduled rather than duplicated;
* must survive a restart;
* must not double-fire when several replicas are running;
* need an audit trail when a baker says "it never told me".

`dedupe_key` is what makes rescheduling possible: one row per real-world
reminder, updated in place.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class NotificationEvent(enum.StrEnum):
    starter_feed_due = "starter.feed_due"
    starter_streak_at_risk = "starter.streak_at_risk"
    proof_ready = "proof.ready"
    proof_retard_remove = "proof.retard_remove"
    inventory_low = "inventory.low"
    achievement_earned = "achievement.earned"
    weekly_digest = "digest.weekly"


class ChannelKind(enum.StrEnum):
    inapp = "inapp"
    email = "email"
    webpush = "webpush"
    ntfy = "ntfy"


class DeliveryStatus(enum.StrEnum):
    pending = "pending"
    claimed = "claimed"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


def _enum_column(enum_type: type[enum.StrEnum], name: str, length: int = 32) -> SAEnum:
    return SAEnum(
        enum_type,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        name=name,
    )


class NotificationSettings(Base, Timestamped):
    """One row per user: quiet hours and the per-event channel map.

    Preferences are a JSONB map (`{event: [channel kinds]}`) rather than a row
    per event, so adding a new reminder type needs no migration and an unset
    event simply falls back to its default.
    """

    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # Local clock hours in the user's own timezone (from their profile).
    quiet_hours_start: Mapped[int | None] = mapped_column(SmallInteger)
    quiet_hours_end: Mapped[int | None] = mapped_column(SmallInteger)
    preferences: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 0 = Monday, matching datetime.weekday().
    digest_weekday: Mapped[int] = mapped_column(SmallInteger, default=6, nullable=False)
    digest_hour: Mapped[int] = mapped_column(SmallInteger, default=9, nullable=False)


class NotificationChannel(Base, UUIDPrimaryKey, Timestamped):
    """A place to send to. A user may have several of a kind — one Web Push
    subscription per device is the normal case."""

    __tablename__ = "notification_channel"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ChannelKind] = mapped_column(
        _enum_column(ChannelKind, "channel_kind"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(60))
    # webpush: {endpoint, keys:{p256dh, auth}} · ntfy: {topic} · email: {address}
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    # Stable identity for the destination, so re-subscribing the same browser
    # updates the row instead of accumulating dead endpoints.
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_notification_channel_target", "user_id", "kind", "target_hash", unique=True),
    )


class ScheduledNotification(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "scheduled_notification"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[NotificationEvent] = mapped_column(
        _enum_column(NotificationEvent, "notification_event"), nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        _enum_column(DeliveryStatus, "delivery_status"),
        default=DeliveryStatus.pending,
        nullable=False,
    )
    # One row per real-world reminder. Rescheduling updates this row's due_at;
    # without it, every proof check would queue another "dough is ready".
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_scheduled_notification_due", "status", "due_at"),)


class NotificationLog(Base, UUIDPrimaryKey):
    """Per-channel delivery outcome. The answer to "it never told me"."""

    __tablename__ = "notification_log"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduled_notification.id", ondelete="SET NULL")
    )
    event: Mapped[NotificationEvent] = mapped_column(
        _enum_column(NotificationEvent, "notification_event"), nullable=False
    )
    channel_kind: Mapped[ChannelKind] = mapped_column(
        _enum_column(ChannelKind, "channel_kind"), nullable=False
    )
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_notification_log_user_time", "user_id", "created_at"),)


class InAppNotification(Base, UUIDPrimaryKey):
    """The in-app inbox — the delivery target of the `inapp` channel."""

    __tablename__ = "inapp_notification"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[NotificationEvent] = mapped_column(
        _enum_column(NotificationEvent, "notification_event"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_inapp_notification_user_time", "user_id", "created_at"),)
