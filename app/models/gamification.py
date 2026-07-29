"""XP ledger, achievements, seasons and the leaderboard rollup.

The XP ledger is append-only and every row is keyed to what caused it, which
buys two things that a stored `total_xp` counter cannot:

* **Idempotence.** The unique key means an event can be published twice — a
  retry, a replay, a double-tap — and award once.
* **Recomputability.** Rebalancing a rule does not require inventing history:
  `sdt recompute-xp` throws the ledger away and derives it again from the
  underlying bakes, feedings and proofs.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class Rarity(enum.StrEnum):
    common = "common"
    uncommon = "uncommon"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"


class AchievementCategory(enum.StrEnum):
    starter = "starter"
    proofing = "proofing"
    baking = "baking"
    recipes = "recipes"
    community = "community"
    inventory = "inventory"
    dedication = "dedication"


class Achievement(Base, Timestamped):
    """Catalogue row. The code definitions are authoritative; this table is a
    projection of them, refreshed by `sdt seed-achievements`, so the UI and the
    foreign key have something to point at."""

    __tablename__ = "achievement"

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[AchievementCategory] = mapped_column(
        SAEnum(
            AchievementCategory,
            native_enum=False,
            length=16,
            values_callable=lambda e: [m.value for m in e],
            name="achievement_category",
        ),
        nullable=False,
    )
    rarity: Mapped[Rarity] = mapped_column(
        SAEnum(
            Rarity,
            native_enum=False,
            length=16,
            values_callable=lambda e: [m.value for m in e],
            name="rarity",
        ),
        nullable=False,
    )
    xp_award: Mapped[int] = mapped_column(Integer, nullable=False)
    icon: Mapped[str] = mapped_column(String(8), default="🥖", nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    criteria: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    # High-value badges require photographic evidence (docs/PLAN.md §7 anti-cheat).
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserAchievement(Base, Timestamped):
    __tablename__ = "user_achievement"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    achievement_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("achievement.code", ondelete="CASCADE"), primary_key=True
    )
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Snapshot of the value that earned it, so a badge stays explicable after
    # the underlying data moves on.
    earned_value: Mapped[float | None] = mapped_column(Float)


class Season(Base, UUIDPrimaryKey, Timestamped):
    """A quarter. Season XP resets; lifetime XP does not, so a newcomer can win
    a board without competing against three years of accumulated total."""

    __tablename__ = "season"

    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_season_window", "starts_at", "ends_at"),)


class XPEvent(Base, UUIDPrimaryKey):
    __tablename__ = "xp_event"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("season.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # The property the whole design rests on: one award per cause.
        UniqueConstraint(
            "user_id", "rule_code", "source_type", "source_id", name="uq_xp_event_source"
        ),
        Index("ix_xp_event_user_created", "user_id", "created_at"),
        Index("ix_xp_event_season_user", "season_id", "user_id"),
    )


class LeaderboardEntry(Base, Timestamped):
    """Periodically refreshed rollup, one row per user per season.

    Every board — XP, bakes, streaks, crumb — reads from this one table, so a
    leaderboard page is a single indexed scan rather than an aggregate over the
    whole history of the service.
    """

    __tablename__ = "leaderboard_entry"

    season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("season.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    season_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bake_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_crumb: Mapped[float | None] = mapped_column(Float)
    achievement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_leaderboard_season_rank", "season_id", "rank"),)
