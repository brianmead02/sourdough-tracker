"""Request/response models for bakes, ratings and photos."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.bake import BakeStatus, PhotoKind
from app.schemas.inventory import ConsumptionResponse

Score = Annotated[int, Field(ge=1, le=5)]
OptionalScore = Annotated[int | None, Field(ge=1, le=5)]


class BakeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    recipe_id: uuid.UUID | None = None
    started_at: datetime | None = None
    total_flour_g: float | None = Field(default=None, gt=0, le=1_000_000)
    hydration_pct: float | None = Field(default=None, ge=30, le=200)
    salt_pct: float | None = Field(default=None, ge=0, le=10)
    starter_pct: float | None = Field(default=None, ge=0, le=100)
    flour_blend: dict[str, float] | None = None
    loaf_count: int = Field(default=1, ge=1, le=100)
    oven_temp_c: float | None = Field(default=None, ge=50, le=400)
    bake_time_minutes: int | None = Field(default=None, ge=1, le=600)
    vessel: str | None = Field(default=None, max_length=60)
    scoring_pattern: str | None = Field(default=None, max_length=60)
    steps: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("flour_blend")
    @classmethod
    def _blend_sums_to_100(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("flour_blend cannot be empty")
        total = sum(value.values())
        if abs(total - 100) > 0.5:
            raise ValueError(f"flour_blend must sum to 100%, got {total:g}%")
        return value


class BakeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    total_flour_g: float | None = Field(default=None, gt=0, le=1_000_000)
    hydration_pct: float | None = Field(default=None, ge=30, le=200)
    salt_pct: float | None = Field(default=None, ge=0, le=10)
    starter_pct: float | None = Field(default=None, ge=0, le=100)
    flour_blend: dict[str, float] | None = None
    loaf_count: int | None = Field(default=None, ge=1, le=100)
    oven_temp_c: float | None = Field(default=None, ge=50, le=400)
    bake_time_minutes: int | None = Field(default=None, ge=1, le=600)
    vessel: str | None = Field(default=None, max_length=60)
    scoring_pattern: str | None = Field(default=None, max_length=60)
    steps: list[dict[str, object]] | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)


class BakeCompleteRequest(BaseModel):
    finished_at: datetime | None = None
    oven_temp_c: float | None = Field(default=None, ge=50, le=400)
    bake_time_minutes: int | None = Field(default=None, ge=1, le=600)
    notes: str | None = Field(default=None, max_length=5000)
    # Draw this bake's flour from inventory and cost it. Opt-out, because not
    # every baker tracks stock, and consuming silently would be a surprise.
    consume_inventory: bool = True


class RatingInput(BaseModel):
    overall: Score
    crumb: OptionalScore = None
    oven_spring: OptionalScore = None
    crust: OptionalScore = None
    sourness: OptionalScore = None
    notes: str | None = Field(default=None, max_length=1000)


class RatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall: int
    crumb: int | None
    oven_spring: int | None
    crust: int | None
    sourness: int | None
    notes: str | None


class PhotoAttach(BaseModel):
    object_key: str = Field(min_length=1, max_length=255)
    kind: PhotoKind = PhotoKind.other
    caption: str | None = Field(default=None, max_length=200)
    sort_order: int = Field(default=0, ge=0, le=999)


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    object_key: str
    kind: PhotoKind
    caption: str | None
    sort_order: int
    size_bytes: int | None
    # Time-limited read URL; objects are private in the bucket.
    url: str


class BakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipe_id: uuid.UUID | None
    title: str
    status: BakeStatus
    started_at: datetime
    finished_at: datetime | None
    total_flour_g: float | None
    hydration_pct: float | None
    salt_pct: float | None
    starter_pct: float | None
    flour_blend: dict[str, float] | None
    loaf_count: int
    oven_temp_c: float | None
    bake_time_minutes: int | None
    vessel: str | None
    scoring_pattern: str | None
    steps: list[dict[str, object]]
    notes: str | None
    flour_cost: float | None
    flour_cost_per_loaf: float | None
    rating: RatingResponse | None
    photo_count: int


class BakeCompleteResponse(BakeResponse):
    """Completion also reports what it drew from stock, if anything."""

    inventory: "ConsumptionResponse | None" = None
