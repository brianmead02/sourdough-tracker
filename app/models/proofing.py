"""Proof sessions and the checks logged against them."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, SmallInteger, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class ProofStage(enum.StrEnum):
    levain = "levain"
    autolyse = "autolyse"
    bulk = "bulk"
    shaped = "shaped"
    retard = "retard"


class ProofStatus(enum.StrEnum):
    running = "running"
    done = "done"
    aborted = "aborted"


class PokeTest(enum.StrEnum):
    springs_back = "springs_back"  # under-proofed
    slow_spring = "slow_spring"  # ready
    no_spring = "no_spring"  # over-proofed


# Default rise target per stage, as a percentage increase in volume. `autolyse`
# is a rest, not a ferment: it is time-based and has no rise target.
DEFAULT_TARGET_RISE_PCT: dict[ProofStage, float] = {
    ProofStage.levain: 100.0,
    ProofStage.autolyse: 0.0,
    ProofStage.bulk: 75.0,
    ProofStage.shaped: 50.0,
    ProofStage.retard: 30.0,
}

DEFAULT_AUTOLYSE_MINUTES = 45


def _enum_column(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        name=name,
    )


class ProofSession(Base, UUIDPrimaryKey, Timestamped):
    """One fermentation stage, from start to done/aborted.

    `predicted_end_at` is re-fitted on every check. Phase 7 schedules the
    "your dough is ready" reminder from this column and reschedules whenever it
    moves — which is why the re-fit updates the session in place rather than
    appending a new prediction row.
    """

    __tablename__ = "proof_session"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional: a plain yeasted dough has no starter, and the levain build for a
    # bake may not be tied to one either.
    starter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("starter.id", ondelete="SET NULL")
    )
    # bake_id is added in Phase 4, once there is a bake table to point at.

    stage: Mapped[ProofStage] = mapped_column(
        _enum_column(ProofStage, "proof_stage"), nullable=False
    )
    status: Mapped[ProofStatus] = mapped_column(
        _enum_column(ProofStatus, "proof_status"), default=ProofStatus.running, nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dough_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    ambient_temp_c: Mapped[float | None] = mapped_column(Float)
    starter_pct: Mapped[float] = mapped_column(Float, nullable=False)
    hydration_pct: Mapped[float | None] = mapped_column(Float)

    target_rise_pct: Mapped[float] = mapped_column(Float, nullable=False)
    # Only used by time-based stages (target_rise_pct == 0), e.g. autolyse.
    planned_duration_minutes: Mapped[int | None] = mapped_column(SmallInteger)

    # The prediction, refreshed on every check.
    predicted_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Snapshot of the vigour used, so a past prediction stays explicable even
    # after the starter's observations have moved on.
    vigour_used: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    notes: Mapped[str | None] = mapped_column(String(500))

    checks: Mapped[list["ProofCheck"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProofCheck.checked_at",
    )

    __table_args__ = (Index("ix_proof_session_user_status", "user_id", "status"),)

    @property
    def is_time_based(self) -> bool:
        return self.target_rise_pct <= 0


class ProofCheck(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "proof_check"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proof_session.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rise_pct: Mapped[float] = mapped_column(Float, nullable=False)
    dough_temp_c: Mapped[float | None] = mapped_column(Float)
    poke_test: Mapped[PokeTest | None] = mapped_column(_enum_column(PokeTest, "poke_test"))
    photo_object_key: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(500))

    session: Mapped[ProofSession] = relationship(back_populates="checks")

    __table_args__ = (Index("ix_proof_check_session_checked_at", "session_id", "checked_at"),)
