"""Request/response models for proof sessions and checks."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.proofing import (
    DEFAULT_AUTOLYSE_MINUTES,
    DEFAULT_TARGET_RISE_PCT,
    PokeTest,
    ProofStage,
    ProofStatus,
)

# Annotated aliases rather than shared Field() instances: a FieldInfo object
# reused across models can be mutated during model construction.
DoughTemp = Annotated[float, Field(ge=0, le=45)]
OptionalDoughTemp = Annotated[float | None, Field(ge=0, le=45)]
RisePct = Annotated[float, Field(ge=0, le=500)]
OptionalRisePct = Annotated[float | None, Field(ge=0, le=500)]
AmbientTemp = Annotated[float | None, Field(ge=-20, le=60)]


class ProofSessionCreate(BaseModel):
    stage: ProofStage
    starter_id: uuid.UUID | None = None
    bake_id: uuid.UUID | None = None
    started_at: datetime | None = None
    dough_temp_c: DoughTemp
    ambient_temp_c: AmbientTemp = None
    starter_pct: float = Field(default=20.0, gt=0, le=100)
    hydration_pct: float | None = Field(default=None, ge=30, le=200)
    # Defaults to the stage's conventional target when omitted.
    target_rise_pct: OptionalRisePct = None
    planned_duration_minutes: int | None = Field(default=None, ge=1, le=10080)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _apply_stage_defaults(self) -> "ProofSessionCreate":
        if self.target_rise_pct is None:
            self.target_rise_pct = DEFAULT_TARGET_RISE_PCT[self.stage]
        if self.target_rise_pct <= 0 and self.planned_duration_minutes is None:
            # A stage with no rise target is time-based and needs a length.
            self.planned_duration_minutes = DEFAULT_AUTOLYSE_MINUTES
        return self


class ProofCheckCreate(BaseModel):
    checked_at: datetime | None = None
    rise_pct: RisePct
    dough_temp_c: OptionalDoughTemp = None
    poke_test: PokeTest | None = None
    notes: str | None = Field(default=None, max_length=500)


class ProofCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    checked_at: datetime
    rise_pct: float
    dough_temp_c: float | None
    poke_test: PokeTest | None
    photo_object_key: str | None
    notes: str | None


class ProofSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starter_id: uuid.UUID | None
    bake_id: uuid.UUID | None
    stage: ProofStage
    status: ProofStatus
    started_at: datetime
    actual_end_at: datetime | None
    dough_temp_c: float
    ambient_temp_c: float | None
    starter_pct: float
    hydration_pct: float | None
    target_rise_pct: float
    planned_duration_minutes: int | None
    predicted_end_at: datetime
    window_start_at: datetime
    window_end_at: datetime
    vigour_used: float
    notes: str | None


class ActiveProofSession(ProofSessionResponse):
    """A running session with everything a countdown needs."""

    check_count: int
    latest_rise_pct: float | None
    progress_pct: float
    hours_remaining: float


class ProofCompleteRequest(BaseModel):
    actual_end_at: datetime | None = None
    final_rise_pct: OptionalRisePct = None
    notes: str | None = Field(default=None, max_length=500)


class EstimateRequest(BaseModel):
    """Preview an ETA without starting anything."""

    stage: ProofStage = ProofStage.bulk
    dough_temp_c: DoughTemp
    starter_pct: float = Field(default=20.0, gt=0, le=100)
    target_rise_pct: OptionalRisePct = None
    vigour: float = Field(default=1.0, ge=0.25, le=4.0)

    @model_validator(mode="after")
    def _apply_stage_default(self) -> "EstimateRequest":
        if self.target_rise_pct is None:
            self.target_rise_pct = DEFAULT_TARGET_RISE_PCT[self.stage]
        return self


class EstimateResponse(BaseModel):
    hours: float
    earliest_hours: float
    latest_hours: float
    rise_per_hour_pct: float
