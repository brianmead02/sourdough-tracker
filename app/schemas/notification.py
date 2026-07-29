"""Request/response models for notifications."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.notification import ChannelKind, DeliveryStatus, NotificationEvent

Hour = Annotated[int, Field(ge=0, le=23)]


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quiet_hours_start: int | None
    quiet_hours_end: int | None
    preferences: dict[str, list[str]]
    digest_enabled: bool
    digest_weekday: int
    digest_hour: int
    timezone: str
    webpush_available: bool


class SettingsUpdate(BaseModel):
    quiet_hours_start: Hour | None = None
    quiet_hours_end: Hour | None = None
    # {event: [channel kinds]}. An event left unset uses its default.
    preferences: dict[str, list[ChannelKind]] | None = None
    digest_enabled: bool | None = None
    digest_weekday: Annotated[int, Field(ge=0, le=6)] | None = None
    digest_hour: Hour | None = None

    @model_validator(mode="after")
    def _known_events_only(self) -> "SettingsUpdate":
        if self.preferences is not None:
            known = {e.value for e in NotificationEvent}
            unknown = set(self.preferences) - known
            if unknown:
                raise ValueError(f"unknown notification events: {sorted(unknown)}")
        return self


class WebPushSubscription(BaseModel):
    """The shape a browser's PushSubscription serialises to."""

    endpoint: str = Field(min_length=1, max_length=1000)
    keys: dict[str, str]
    label: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _has_required_keys(self) -> "WebPushSubscription":
        missing = {"p256dh", "auth"} - set(self.keys)
        if missing:
            raise ValueError(f"subscription keys missing: {sorted(missing)}")
        return self


class NtfyChannelCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    token: str | None = Field(default=None, max_length=200)
    label: str | None = Field(default=None, max_length=60)


class EmailChannelCreate(BaseModel):
    address: EmailStr
    label: str | None = Field(default=None, max_length=60)


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ChannelKind
    label: str | None
    is_enabled: bool
    consecutive_failures: int
    last_used_at: datetime | None
    created_at: datetime
    # Enough to recognise the destination, never enough to impersonate it.
    target: str


class InboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: NotificationEvent
    title: str
    body: str
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class InboxPage(BaseModel):
    items: list[InboxItem]
    unread_count: int


class MarkReadRequest(BaseModel):
    ids: list[uuid.UUID] | None = None
    all: bool = False

    @model_validator(mode="after")
    def _something_to_do(self) -> "MarkReadRequest":
        if not self.all and not self.ids:
            raise ValueError("provide ids, or all=true")
        return self


class ScheduledResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: NotificationEvent
    due_at: datetime
    status: DeliveryStatus
    attempts: int
    dedupe_key: str
    last_error: str | None


class TestNotificationRequest(BaseModel):
    kind: ChannelKind | None = None


class EventCatalogueItem(BaseModel):
    event: NotificationEvent
    title: str
    urgency: str
    icon: str
    default_channels: list[ChannelKind]
    ignores_quiet_hours: bool
