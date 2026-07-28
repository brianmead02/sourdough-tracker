"""User and profile representations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole
from app.schemas.validators import validate_timezone


class PublicProfile(BaseModel):
    """What anyone may see. Never includes the email address."""

    model_config = ConfigDict(from_attributes=True)

    handle: str
    display_name: str
    bio: str | None = None
    avatar_object_key: str | None = None
    created_at: datetime


class OwnProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    handle: str
    display_name: str
    bio: str | None = None
    avatar_object_key: str | None = None
    is_public: bool
    timezone: str


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_verified: bool
    is_suspended: bool
    created_at: datetime
    last_login_at: datetime | None = None
    profile: OwnProfile


class ProfileUpdate(BaseModel):
    """All fields optional — only what is supplied is changed.

    `handle` is deliberately absent: it appears in public URLs and on the
    leaderboard, so renaming needs a redirect/history story it does not have yet.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    bio: str | None = Field(default=None, max_length=500)
    is_public: bool | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return None if value is None else validate_timezone(value)
