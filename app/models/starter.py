"""Starters, their feeding log, and observations of how they behaved."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey


class StarterState(enum.StrEnum):
    active = "active"
    fridge = "fridge"
    dormant = "dormant"
    retired = "retired"


class Aroma(enum.StrEnum):
    sweet = "sweet"
    yeasty = "yeasty"
    tangy = "tangy"
    sour = "sour"
    vinegar = "vinegar"
    acetone = "acetone"
    alcohol = "alcohol"
    musty = "musty"


def _enum_column(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        name=name,
    )


class Starter(Base, UUIDPrimaryKey, Timestamped, SoftDeletable):
    __tablename__ = "starter"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    flour_type: Mapped[str] = mapped_column(String(60), default="bread", nullable=False)
    birthday: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(1000))
    avatar_object_key: Mapped[str | None] = mapped_column(String(255))

    # Feed ratio as starter:flour:water, e.g. 1:5:5. This is the single source of
    # truth for hydration — storing hydration_pct separately would let the two
    # disagree. See the `hydration_pct` property.
    ratio_starter: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    ratio_flour: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)
    ratio_water: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)

    feed_interval_hours: Mapped[int] = mapped_column(SmallInteger, default=24, nullable=False)
    state: Mapped[StarterState] = mapped_column(
        _enum_column(StarterState, "starter_state"), default=StarterState.active, nullable=False
    )

    feedings: Mapped[list["Feeding"]] = relationship(
        back_populates="starter", cascade="all, delete-orphan", passive_deletes=True
    )
    observations: Mapped[list["StarterObservation"]] = relationship(
        back_populates="starter", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # Names are unique per user, but only among live starters — retiring
        # "Bubbles" must not block naming a new one "Bubbles".
        Index(
            "uq_starter_user_name_live",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    @property
    def hydration_pct(self) -> float:
        """Water as a percentage of flour, derived from the feed ratio."""
        return round(self.ratio_water / self.ratio_flour * 100, 1)


class Feeding(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "feeding"

    starter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("starter.id", ondelete="CASCADE"), nullable=False
    )
    fed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    starter_g: Mapped[float] = mapped_column(Float, nullable=False)
    flour_g: Mapped[float] = mapped_column(Float, nullable=False)
    water_g: Mapped[float] = mapped_column(Float, nullable=False)
    # {"bread": 80, "rye": 20} — percentages of the flour component.
    flour_blend: Mapped[dict[str, float] | None] = mapped_column(JSONB)

    ambient_temp_c: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(500))

    starter: Mapped[Starter] = relationship(back_populates="feedings")

    __table_args__ = (Index("ix_feeding_starter_fed_at", "starter_id", "fed_at"),)

    @property
    def hydration_pct(self) -> float:
        return round(self.water_g / self.flour_g * 100, 1) if self.flour_g else 0.0


class StarterObservation(Base, UUIDPrimaryKey, Timestamped):
    """How the starter actually behaved — the input to vigour estimates in Phase 3."""

    __tablename__ = "starter_observation"

    starter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("starter.id", ondelete="CASCADE"), nullable=False
    )
    feeding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feeding.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rise_multiple: Mapped[float | None] = mapped_column(Float)
    peaked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    float_test_passed: Mapped[bool | None] = mapped_column(Boolean)
    aroma: Mapped[Aroma | None] = mapped_column(_enum_column(Aroma, "aroma"))
    dough_temp_c: Mapped[float | None] = mapped_column(Float)
    photo_object_key: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(500))

    starter: Mapped[Starter] = relationship(back_populates="observations")

    __table_args__ = (
        Index("ix_starter_observation_starter_observed_at", "starter_id", "observed_at"),
    )
