"""Request/response models for recipes."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.recipe import IngredientKind
from app.services.recipes import Ingredient, RecipeError, validate_percentages

Percentage = Annotated[float, Field(gt=0, le=1000)]


class IngredientInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: IngredientKind
    percentage: Percentage


class IngredientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: IngredientKind
    percentage: float
    sort_order: int


class RecipeBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    is_public: bool = False
    default_dough_weight_g: float = Field(default=1000.0, gt=0, le=100_000)
    starter_hydration_pct: float = Field(default=100.0, ge=30, le=300)
    tags: list[str] = Field(default_factory=list, max_length=10)
    steps: list[dict[str, object]] = Field(default_factory=list, max_length=50)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned = []
        for tag in value:
            slug = tag.strip().lower()
            if not slug:
                continue
            if len(slug) > 30:
                raise ValueError("tags must be 30 characters or fewer")
            if slug not in cleaned:
                cleaned.append(slug)
        return cleaned


class RecipeCreate(RecipeBase):
    ingredients: list[IngredientInput] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _percentages_are_bakeable(self) -> "RecipeCreate":
        try:
            validate_percentages(
                [Ingredient(i.name, i.kind, i.percentage) for i in self.ingredients]
            )
        except RecipeError as exc:
            raise ValueError(str(exc)) from exc
        return self


class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    is_public: bool | None = None
    default_dough_weight_g: float | None = Field(default=None, gt=0, le=100_000)
    starter_hydration_pct: float | None = Field(default=None, ge=30, le=300)
    tags: list[str] | None = Field(default=None, max_length=10)
    steps: list[dict[str, object]] | None = Field(default=None, max_length=50)
    # Supplying ingredients replaces the whole set — a partial merge of a
    # percentage list would silently break the sums-to-100 invariant.
    ingredients: list[IngredientInput] | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def _percentages_are_bakeable(self) -> "RecipeUpdate":
        if self.ingredients is not None:
            try:
                validate_percentages(
                    [Ingredient(i.name, i.kind, i.percentage) for i in self.ingredients]
                )
            except RecipeError as exc:
                raise ValueError(str(exc)) from exc
        return self


class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    is_public: bool
    forked_from_id: uuid.UUID | None
    version: int
    default_dough_weight_g: float
    starter_hydration_pct: float
    tags: list[str]
    steps: list[dict[str, object]]
    star_count: int
    fork_count: int
    created_at: datetime
    ingredients: list[IngredientResponse]


class PublicRecipeSummary(BaseModel):
    """Listing shape for the public browse view — no step-by-step method."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_handle: str
    tags: list[str]
    star_count: int
    fork_count: int
    created_at: datetime


class ScaledIngredientResponse(BaseModel):
    name: str
    kind: IngredientKind
    percentage: float
    grams: float


class ScaledRecipeResponse(BaseModel):
    added_flour_g: float
    total_dough_g: float
    ingredients: list[ScaledIngredientResponse]
    stated_hydration_pct: float
    true_hydration_pct: float
    total_flour_g: float
    total_water_g: float
    salt_pct: float
    starter_pct: float
    loaf_count: int
    loaf_weight_g: float


class ForkResponse(RecipeResponse):
    pass
