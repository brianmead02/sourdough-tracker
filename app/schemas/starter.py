"""Request/response models for starters, feedings and observations."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.starter import Aroma, StarterState
from app.services.starters import ScheduleStatus

# Shared bounds. Generous enough for a bakery, tight enough to reject nonsense
# that would poison streaks, averages and the fermentation model. Annotated
# aliases rather than shared Field() instances, which can be mutated during
# model construction.
Grams = Annotated[float, Field(gt=0, le=100_000)]
OptionalTemp = Annotated[float | None, Field(ge=-20, le=60)]


class StarterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    flour_type: str = Field(default="bread", min_length=1, max_length=60)
    birthday: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    ratio_starter: int = Field(default=1, ge=1, le=100)
    ratio_flour: int = Field(default=5, ge=1, le=100)
    ratio_water: int = Field(default=5, ge=1, le=100)
    feed_interval_hours: int = Field(default=24, ge=1, le=720)
    state: StarterState = StarterState.active

    @field_validator("birthday")
    @classmethod
    def _not_in_the_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("birthday cannot be in the future")
        return value


class StarterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    flour_type: str | None = Field(default=None, min_length=1, max_length=60)
    birthday: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    ratio_starter: int | None = Field(default=None, ge=1, le=100)
    ratio_flour: int | None = Field(default=None, ge=1, le=100)
    ratio_water: int | None = Field(default=None, ge=1, le=100)
    feed_interval_hours: int | None = Field(default=None, ge=1, le=720)
    state: StarterState | None = None


class StarterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    flour_type: str
    birthday: date | None
    notes: str | None
    avatar_object_key: str | None
    ratio_starter: int
    ratio_flour: int
    ratio_water: int
    hydration_pct: float
    feed_interval_hours: int
    state: StarterState
    created_at: datetime


class StarterListItem(StarterResponse):
    """List view carries just enough schedule context to render a dashboard."""

    status: ScheduleStatus
    last_fed_at: datetime | None
    next_due_at: datetime | None
    hours_until_due: float | None


class FeedingCreate(BaseModel):
    # Defaults to "now" server-side when omitted.
    fed_at: datetime | None = None
    starter_g: Grams
    flour_g: Grams
    water_g: Grams
    flour_blend: dict[str, float] | None = None
    ambient_temp_c: OptionalTemp = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("flour_blend")
    @classmethod
    def _blend_sums_to_100(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("flour_blend cannot be empty")
        if any(pct <= 0 for pct in value.values()):
            raise ValueError("flour_blend percentages must be positive")
        total = sum(value.values())
        if abs(total - 100) > 0.5:
            raise ValueError(f"flour_blend must sum to 100%, got {total:g}%")
        return value


class FeedingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starter_id: uuid.UUID
    fed_at: datetime
    starter_g: float
    flour_g: float
    water_g: float
    hydration_pct: float
    flour_blend: dict[str, float] | None
    ambient_temp_c: float | None
    notes: str | None


class ObservationCreate(BaseModel):
    observed_at: datetime | None = None
    feeding_id: uuid.UUID | None = None
    rise_multiple: float | None = Field(default=None, ge=1, le=20)
    peaked: bool = False
    float_test_passed: bool | None = None
    aroma: Aroma | None = None
    dough_temp_c: OptionalTemp = None
    notes: str | None = Field(default=None, max_length=500)


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starter_id: uuid.UUID
    feeding_id: uuid.UUID | None
    observed_at: datetime
    rise_multiple: float | None
    peaked: bool
    float_test_passed: bool | None
    aroma: Aroma | None
    dough_temp_c: float | None
    photo_object_key: str | None
    notes: str | None


class StreakResponse(BaseModel):
    starter_id: uuid.UUID
    current: int
    longest: int
    total_feedings: int
    last_fed_at: datetime | None
    next_due_at: datetime | None
    deadline_at: datetime | None
    is_alive: bool


class ScheduleItem(BaseModel):
    starter_id: uuid.UUID
    name: str
    state: StarterState
    status: ScheduleStatus
    feed_interval_hours: int
    last_fed_at: datetime | None
    next_due_at: datetime | None
    hours_until_due: float | None


class SuggestedFeedResponse(BaseModel):
    starter_g: float
    flour_g: float
    water_g: float
    total_g: float
    hydration_pct: float


class SuggestFeedRequest(BaseModel):
    starter_g: float | None = Field(default=None, gt=0, le=100_000)
    total_g: float | None = Field(default=None, gt=0, le=100_000)

    @model_validator(mode="after")
    def _exactly_one(self) -> "SuggestFeedRequest":
        if (self.starter_g is None) == (self.total_g is None):
            raise ValueError("provide exactly one of starter_g or total_g")
        return self
