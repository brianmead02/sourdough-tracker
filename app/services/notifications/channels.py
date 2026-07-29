"""Delivery channels.

One `Notifier` protocol, four implementations. Each returns normally on success
and raises `DeliveryError` on failure; the dispatcher decides what a failure
means (retry, disable the channel, give up).

Channels are attempted **independently**: a dead Web Push subscription must not
stop the same reminder reaching the inbox and the phone.
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.models.notification import ChannelKind, InAppNotification, NotificationChannel
from app.services.notifications.catalogue import EventSpec, Urgency

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """Delivery failed. `permanent` means retrying will not help."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class Notifier(Protocol):
    kind: ChannelKind

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: NotificationChannel | None,
        spec: EventSpec,
        title: str,
        body: str,
        payload: dict[str, Any],
    ) -> None: ...


def ascii_header(value: str) -> str:
    """Make a string safe to put in an HTTP header.

    Header values must be ASCII. Titles contain user text — a starter called
    "Gérald", or a display name in any non-Latin script — so this is not an
    edge case, it is Tuesday. Accents are folded where possible and anything
    else is dropped; the full text always survives in the message body.
    """
    import unicodedata

    folded = unicodedata.normalize("NFKD", value)
    stripped = folded.encode("ascii", "ignore").decode("ascii").strip()
    return stripped or "Sourdough Tracker"


def target_hash(kind: ChannelKind, config: dict[str, Any]) -> str:
    """Stable identity for a destination, so re-subscribing updates in place."""
    if kind is ChannelKind.webpush:
        material = str(config.get("endpoint", ""))
    elif kind is ChannelKind.ntfy:
        material = str(config.get("topic", ""))
    elif kind is ChannelKind.email:
        material = str(config.get("address", "")).lower()
    else:
        material = "inbox"
    return hashlib.sha256(f"{kind.value}:{material}".encode()).hexdigest()


class InAppNotifier:
    """Writes to the inbox. The one channel that cannot fail to be delivered."""

    kind = ChannelKind.inapp

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: NotificationChannel | None,
        spec: EventSpec,
        title: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        db.add(
            InAppNotification(
                user_id=user_id,
                event=spec.event,
                title=title,
                body=body,
                data=payload,
                created_at=datetime.now(UTC),
            )
        )
        await db.flush()


class EmailNotifier:
    kind = ChannelKind.email

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: NotificationChannel | None,
        spec: EventSpec,
        title: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        from app.services.email import send_email

        address = str((channel.config if channel else {}).get("address", "")) if channel else ""
        if not address:
            raise DeliveryError("no address configured", permanent=True)

        try:
            await send_email(address, f"{spec.icon} {title}", f"{body}\n")
        except Exception as exc:  # any SMTP failure is a delivery failure
            raise DeliveryError(f"smtp: {exc}") from exc


class NtfyNotifier:
    """Self-hosted push. The Android path that avoids a Firebase dependency."""

    kind = ChannelKind.ntfy

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: NotificationChannel | None,
        spec: EventSpec,
        title: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        settings = get_settings()
        config = channel.config if channel else {}
        topic = str(config.get("topic", ""))
        if not topic:
            raise DeliveryError("no ntfy topic configured", permanent=True)

        # HTTP headers are ASCII. The icon is an emoji and titles carry user
        # text ("Gérald needs feeding"), so both must be sanitised — ntfy takes
        # emoji as *names* in Tags, not as characters.
        headers = {
            "Title": ascii_header(title),
            "Tags": spec.ntfy_tag,
            "Priority": "high" if spec.urgency is not Urgency.routine else "default",
        }
        token = config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{settings.ntfy_base_url.rstrip('/')}/{topic}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, content=body.encode(), headers=headers)
        except httpx.HTTPError as exc:
            raise DeliveryError(f"ntfy unreachable: {exc}") from exc

        if response.status_code >= 400:
            # 4xx means the topic or auth is wrong; retrying will not fix it.
            raise DeliveryError(
                f"ntfy {response.status_code}", permanent=400 <= response.status_code < 500
            )


class WebPushNotifier:
    kind = ChannelKind.webpush

    async def send(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: NotificationChannel | None,
        spec: EventSpec,
        title: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        settings = get_settings()
        if not settings.vapid_private_key:
            raise DeliveryError("web push is not configured on this server", permanent=True)
        if channel is None:
            raise DeliveryError("no subscription", permanent=True)

        message = json.dumps(
            {
                "title": f"{spec.icon} {title}",
                "body": body,
                "event": spec.event.value,
                "data": payload,
            }
        )
        subscription = dict(channel.config)

        def _push() -> None:
            from pywebpush import WebPushException, webpush

            try:
                webpush(
                    subscription_info=subscription,
                    data=message,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_subject},
                    timeout=15,
                )
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                # 404/410 mean the browser threw the subscription away. It is
                # never coming back — the channel should be disabled, not retried.
                permanent = status in (400, 401, 403, 404, 410)
                raise DeliveryError(f"webpush {status}: {exc}", permanent=permanent) from exc

        await run_in_threadpool(_push)


NOTIFIERS: dict[ChannelKind, Notifier] = {
    ChannelKind.inapp: InAppNotifier(),
    ChannelKind.email: EmailNotifier(),
    ChannelKind.ntfy: NtfyNotifier(),
    ChannelKind.webpush: WebPushNotifier(),
}


def webpush_available(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)
