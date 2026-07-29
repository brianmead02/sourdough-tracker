"""Bakes, their ratings, and their photos."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey


class BakeStatus(enum.StrEnum):
    in_progress = "in_progress"
    done = "done"
    abandoned = "abandoned"


class PhotoKind(enum.StrEnum):
    crumb = "crumb"
    crust = "crust"
    shaped = "shaped"
    proof = "proof"
    other = "other"


def _enum_column(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        name=name,
    )


class Bake(Base, UUIDPrimaryKey, Timestamped, SoftDeletable):
    __tablename__ = "bake"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A bake outlives the recipe it came from: deleting the recipe must not erase
    # the record of what was baked.
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[BakeStatus] = mapped_column(
        _enum_column(BakeStatus, "bake_status"), default=BakeStatus.in_progress, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Formula as baked, snapshotted rather than referenced: editing the recipe
    # later must not rewrite history.
    total_flour_g: Mapped[float | None] = mapped_column(Float)
    hydration_pct: Mapped[float | None] = mapped_column(Float)
    salt_pct: Mapped[float | None] = mapped_column(Float)
    starter_pct: Mapped[float | None] = mapped_column(Float)
    flour_blend: Mapped[dict[str, float] | None] = mapped_column(JSONB)

    loaf_count: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    oven_temp_c: Mapped[float | None] = mapped_column(Float)
    bake_time_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    vessel: Mapped[str | None] = mapped_column(String(60))
    scoring_pattern: Mapped[str | None] = mapped_column(String(60))

    steps: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Costed from inventory when the bake completes (Phase 5). Named for what is
    # actually counted: the flours drawn from stock, not every input.
    flour_cost: Mapped[float | None] = mapped_column(Float)
    flour_cost_per_loaf: Mapped[float | None] = mapped_column(Float)
    # Set once, so re-completing or replaying cannot double-consume stock.
    inventory_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rating: Mapped["BakeRating | None"] = relationship(
        back_populates="bake", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin"
    )
    photos: Mapped[list["BakePhoto"]] = relationship(
        back_populates="bake",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BakePhoto.sort_order",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_bake_user_started", "user_id", text("started_at DESC")),)


class BakeRating(Base, Timestamped):
    """At most one rating per bake — the bake id is the primary key."""

    __tablename__ = "bake_rating"

    bake_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bake.id", ondelete="CASCADE"), primary_key=True
    )
    crumb: Mapped[int | None] = mapped_column(SmallInteger)
    oven_spring: Mapped[int | None] = mapped_column(SmallInteger)
    crust: Mapped[int | None] = mapped_column(SmallInteger)
    sourness: Mapped[int | None] = mapped_column(SmallInteger)
    overall: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))

    bake: Mapped[Bake] = relationship(back_populates="rating")


class BakePhoto(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "bake_photo"

    bake_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bake.id", ondelete="CASCADE"), nullable=False
    )
    # Unique so the same upload cannot be attached twice, or to two bakes.
    object_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    kind: Mapped[PhotoKind] = mapped_column(
        _enum_column(PhotoKind, "photo_kind"), default=PhotoKind.other, nullable=False
    )
    caption: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    # Integer, not SmallInteger: a 10 MB upload does not fit in 32767.
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    bake: Mapped[Bake] = relationship(back_populates="photos")

    __table_args__ = (Index("ix_bake_photo_bake", "bake_id", "sort_order"),)
