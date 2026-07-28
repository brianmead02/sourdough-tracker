"""Identity: users, public profiles, and the single-use token tables."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey


class UserRole(enum.StrEnum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


# native_enum=False -> VARCHAR + CHECK constraint. Adding a role later is an
# ALTER CHECK rather than a Postgres ENUM migration dance.
_role_column = SAEnum(
    UserRole,
    native_enum=False,
    length=16,
    values_callable=lambda e: [m.value for m in e],
    name="user_role",
)


class User(Base, UUIDPrimaryKey, Timestamped, SoftDeletable):
    __tablename__ = "user"

    # Stored lower-cased; uniqueness is therefore case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(_role_column, default=UserRole.user, nullable=False)

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suspended_reason: Mapped[str | None] = mapped_column(Text)

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None


class UserProfile(Base, Timestamped):
    __tablename__ = "user_profile"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # Stored lower-cased. Public identifier used in URLs and on the leaderboard.
    handle: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    bio: Mapped[str | None] = mapped_column(String(500))
    avatar_object_key: Mapped[str | None] = mapped_column(String(255))
    # Opt-in visibility: a profile is private until the user publishes it.
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")


class RefreshToken(Base, UUIDPrimaryKey):
    """One row per issued refresh token. Only the SHA-256 hash is stored.

    Rotation: refreshing revokes the presented token and issues a successor in the
    same `family_id`. Presenting an already-revoked token means the token leaked,
    so the whole family is revoked (see services/auth.py).
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_agent: Mapped[str | None] = mapped_column(String(255))
    client_ip: Mapped[str | None] = mapped_column(String(45))


class EmailVerification(Base, UUIDPrimaryKey):
    __tablename__ = "email_verification"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordReset(Base, UUIDPrimaryKey):
    __tablename__ = "password_reset"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
