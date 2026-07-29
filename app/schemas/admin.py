"""Request/response models for administration and account self-service."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    handle: str
    display_name: str
    role: UserRole
    is_verified: bool
    is_suspended: bool
    suspended_reason: str | None
    created_at: datetime
    last_login_at: datetime | None
    public_recipes: int
    bakes: int


class SuspendRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ModerationItem(BaseModel):
    """A published recipe awaiting a look."""

    recipe_id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    owner_handle: str
    owner_suspended: bool
    tags: list[str]
    star_count: int
    fork_count: int
    created_at: datetime


class InstanceStats(BaseModel):
    users_total: int
    users_verified: int
    users_suspended: int
    starters: int
    feedings: int
    proof_sessions: int
    bakes: int
    recipes: int
    recipes_public: int
    photos: int
    notifications_pending: int
    notifications_failed: int
    xp_awarded: int
    achievements_earned: int
    database_bytes: int


class ExportManifest(BaseModel):
    """Everything the service holds about one account."""

    exported_at: datetime
    account: dict[str, Any]
    profile: dict[str, Any]
    starters: list[dict[str, Any]]
    feedings: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    proof_sessions: list[dict[str, Any]]
    proof_checks: list[dict[str, Any]]
    recipes: list[dict[str, Any]]
    bakes: list[dict[str, Any]]
    ratings: list[dict[str, Any]]
    photos: list[dict[str, Any]]
    inventory_items: list[dict[str, Any]]
    inventory_transactions: list[dict[str, Any]]
    achievements: list[dict[str, Any]]
    xp_events: list[dict[str, Any]]
    notification_settings: dict[str, Any] | None
    notification_channels: list[dict[str, Any]]
    inbox: list[dict[str, Any]]


class DeleteAccountRequest(BaseModel):
    """Erasure is irreversible, so it takes both a password and a typed phrase."""

    password: str = Field(max_length=128)
    confirm: str = Field(description='Must be exactly "DELETE MY ACCOUNT"')


class DeleteAccountResponse(BaseModel):
    deleted: bool
    rows_removed: dict[str, int]
    photos_removed: int
