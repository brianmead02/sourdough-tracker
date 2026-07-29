"""Notification settings, channels and the in-app inbox."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RateLimiter, VerifiedUser
from app.config import get_settings
from app.db import get_session
from app.models.notification import (
    ChannelKind,
    InAppNotification,
    NotificationChannel,
    NotificationEvent,
    ScheduledNotification,
)
from app.schemas.notification import (
    ChannelResponse,
    EmailChannelCreate,
    EventCatalogueItem,
    InboxItem,
    InboxPage,
    MarkReadRequest,
    NtfyChannelCreate,
    ScheduledResponse,
    SettingsResponse,
    SettingsUpdate,
    TestNotificationRequest,
    WebPushSubscription,
)
from app.services.notifications import (
    SPECS,
    Urgency,
    ensure_settings,
    notify_now,
    target_hash,
    unread_count,
    webpush_available,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _target_summary(channel: NotificationChannel) -> str:
    """Recognisable, not reusable — a push endpoint is a bearer capability."""
    config = channel.config
    if channel.kind is ChannelKind.ntfy:
        return str(config.get("topic", ""))
    if channel.kind is ChannelKind.email:
        return str(config.get("address", ""))
    if channel.kind is ChannelKind.webpush:
        endpoint = str(config.get("endpoint", ""))
        return f"…{endpoint[-12:]}" if endpoint else ""
    return "inbox"


def _to_channel_response(channel: NotificationChannel) -> ChannelResponse:
    return ChannelResponse(
        id=channel.id,
        kind=channel.kind,
        label=channel.label,
        is_enabled=channel.is_enabled,
        consecutive_failures=channel.consecutive_failures,
        last_used_at=channel.last_used_at,
        created_at=channel.created_at,
        target=_target_summary(channel),
    )


async def _upsert_channel(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: ChannelKind,
    config: dict[str, object],
    label: str | None,
) -> NotificationChannel:
    """Re-subscribing the same destination updates it rather than duplicating."""
    digest = target_hash(kind, config)
    existing = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user_id,
            NotificationChannel.kind == kind,
            NotificationChannel.target_hash == digest,
        )
    )
    channel = existing.scalar_one_or_none()
    if channel is None:
        channel = NotificationChannel(
            user_id=user_id, kind=kind, config=config, target_hash=digest, label=label
        )
        db.add(channel)
    else:
        channel.config = config
        channel.label = label or channel.label
        # A re-subscription is a fresh start for a channel we had disabled.
        channel.is_enabled = True
        channel.consecutive_failures = 0
    await db.flush()
    return channel


# --- settings ---------------------------------------------------------------


@router.get("/settings", response_model=SettingsResponse)
async def read_settings(user: CurrentUser, db: SessionDep) -> SettingsResponse:
    row = await ensure_settings(db, user)
    return SettingsResponse(
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
        preferences=row.preferences,
        digest_enabled=row.digest_enabled,
        digest_weekday=row.digest_weekday,
        digest_hour=row.digest_hour,
        timezone=user.profile.timezone,
        webpush_available=webpush_available(),
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate, user: CurrentUser, db: SessionDep
) -> SettingsResponse:
    row = await ensure_settings(db, user)
    changes = payload.model_dump(exclude_unset=True)
    if "preferences" in changes and changes["preferences"] is not None:
        changes["preferences"] = {
            event: [ChannelKind(k).value for k in kinds]
            for event, kinds in changes["preferences"].items()
        }
    for field, value in changes.items():
        setattr(row, field, value)
    await db.flush()
    return await read_settings(user, db)


@router.get("/events", response_model=list[EventCatalogueItem])
async def list_events(user: CurrentUser) -> list[EventCatalogueItem]:
    """Every reminder the service can send, and how it behaves."""
    return [
        EventCatalogueItem(
            event=spec.event,
            title=spec.title,
            urgency=spec.urgency.value,
            icon=spec.icon,
            default_channels=list(spec.default_channels),
            ignores_quiet_hours=spec.urgency is Urgency.time_critical,
        )
        for spec in SPECS.values()
    ]


# --- channels ---------------------------------------------------------------


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(user: CurrentUser, db: SessionDep) -> list[ChannelResponse]:
    rows = await db.execute(
        select(NotificationChannel)
        .where(NotificationChannel.user_id == user.id)
        .order_by(NotificationChannel.created_at)
    )
    return [_to_channel_response(c) for c in rows.scalars().all()]


@router.get("/vapid-key")
async def vapid_key(user: CurrentUser) -> dict[str, str | bool]:
    """The public key a browser needs to subscribe. Safe to hand out."""
    settings = get_settings()
    return {"public_key": settings.vapid_public_key, "available": webpush_available()}


@router.post(
    "/webpush/subscribe",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=20, seconds=3600, scope="webpush-subscribe"))],
)
async def subscribe_webpush(
    payload: WebPushSubscription, user: VerifiedUser, db: SessionDep
) -> ChannelResponse:
    if not webpush_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web Push is not configured on this server",
        )
    channel = await _upsert_channel(
        db,
        user.id,
        ChannelKind.webpush,
        {"endpoint": payload.endpoint, "keys": payload.keys},
        payload.label,
    )
    return _to_channel_response(channel)


@router.post("/channels/ntfy", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_ntfy(
    payload: NtfyChannelCreate, user: VerifiedUser, db: SessionDep
) -> ChannelResponse:
    config: dict[str, object] = {"topic": payload.topic}
    if payload.token:
        config["token"] = payload.token
    channel = await _upsert_channel(db, user.id, ChannelKind.ntfy, config, payload.label)
    return _to_channel_response(channel)


@router.post("/channels/email", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_email(
    payload: EmailChannelCreate, user: VerifiedUser, db: SessionDep
) -> ChannelResponse:
    if payload.address.lower() != user.email.lower():
        # Otherwise this endpoint is a way to have the service mail strangers.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Notifications can only be sent to your own verified address",
        )
    channel = await _upsert_channel(
        db, user.id, ChannelKind.email, {"address": payload.address.lower()}, payload.label
    )
    return _to_channel_response(channel)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id, NotificationChannel.user_id == user.id
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    await db.delete(channel)


@router.post(
    "/test",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=10, seconds=3600, scope="notification-test"))],
)
async def send_test(
    payload: TestNotificationRequest, user: VerifiedUser, db: SessionDep
) -> dict[str, str]:
    """Queue a test reminder so a baker can prove their setup works."""
    await notify_now(
        db,
        user_id=user.id,
        event=NotificationEvent.achievement_earned,
        payload={
            "icon": "🔔",
            "name": "Test notification",
            "description": "If you can read this, notifications are working",
            "xp_award": 0,
        },
        dedupe_key=f"test:{user.id}:{uuid.uuid4()}",
    )
    return {"message": "Queued — it should arrive within a minute."}


# --- inbox ------------------------------------------------------------------


@router.get("/inbox", response_model=InboxPage)
async def read_inbox(
    user: CurrentUser,
    db: SessionDep,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InboxPage:
    conditions = [InAppNotification.user_id == user.id]
    if unread_only:
        conditions.append(InAppNotification.read_at.is_(None))

    rows = await db.execute(
        select(InAppNotification)
        .where(*conditions)
        .order_by(InAppNotification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return InboxPage(
        items=[InboxItem.model_validate(row) for row in rows.scalars().all()],
        unread_count=await unread_count(db, user.id),
    )


@router.post("/inbox/read", response_model=InboxPage)
async def mark_read(payload: MarkReadRequest, user: CurrentUser, db: SessionDep) -> InboxPage:
    conditions = [
        InAppNotification.user_id == user.id,
        InAppNotification.read_at.is_(None),
    ]
    if not payload.all:
        conditions.append(InAppNotification.id.in_(payload.ids or []))

    await db.execute(update(InAppNotification).where(*conditions).values(read_at=datetime.now(UTC)))
    return await read_inbox(user, db)


# --- scheduled (visibility) -------------------------------------------------


@router.get("/scheduled", response_model=list[ScheduledResponse])
async def list_scheduled(
    user: CurrentUser,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ScheduledResponse]:
    """What is queued for you. Useful for a client, essential for debugging."""
    rows = await db.execute(
        select(ScheduledNotification)
        .where(ScheduledNotification.user_id == user.id)
        .order_by(ScheduledNotification.due_at.desc())
        .limit(limit)
    )
    return [ScheduledResponse.model_validate(row) for row in rows.scalars().all()]
