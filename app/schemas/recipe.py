"""Request/response models for recipes."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.recipe import IngredientKind
from app.schemas.measurement import MeasureDisplay
from app.services.measurements import Unit, UnitFamily, family
from app.services.recipes import Ingredient, RecipeError, validate_percentages

Percentage = Annotated[float, Field(gt=0, le=1000)]


def uses_amounts(ingredients: "Sequence[IngredientInput]") -> bool:
    return any(i.amount is not None for i in ingredients)


def _require_consistent_form(model: "RecipeCreate | RecipeUpdate") -> None:
    """Every line must use the same form.

    Mixing "100%" with "3 cups" in one recipe has no single sensible reading —
    is the percentage relative to the converted flour, or was it meant as an
    amount? Rejecting is the only honest answer.
    """
    ingredients = model.ingredients or []
    amounts = sum(1 for i in ingredients if i.amount is not None)
    if amounts not in (0, len(ingredients)):
        raise ValueError(
            "give every ingredient as a percentage, or every one as an amount - not a mix"
        )


class IngredientInput(BaseModel):
    """One recipe line, as a percentage *or* as an amount.

    Recipes are stored as baker's percentages, so a percentage is the native
    form. But a baker with measuring cups thinks in quantities, and making them
    work out 70% hydration by hand before they can save a recipe is backwards.
    `amount` + `unit` is accepted instead and converted by the route, which is
    where densities can be loaded.
    """

    name: str = Field(min_length=1, max_length=80)
    kind: IngredientKind
    percentage: Percentage | None = None
    amount: Annotated[float | None, Field(gt=0, le=1_000_000)] = None
    unit: Unit | None = None

    @model_validator(mode="after")
    def _exactly_one_form(self) -> "IngredientInput":
        has_amount = self.amount is not None
        if has_amount != (self.unit is not None):
            raise ValueError("amount and unit must be given together")
        if has_amount == (self.percentage is not None):
            raise ValueError("give either percentage, or amount with unit")
        if self.unit is not None and family(self.unit) is UnitFamily.temperature:
            raise ValueError("an ingredient cannot be measured in degrees")
        return self


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
    def _one_form_for_the_whole_recipe(self) -> "RecipeCreate":
        _require_consistent_form(self)
        return self

    @model_validator(mode="after")
    def _percentages_are_bakeable(self) -> "RecipeCreate":
        # Skipped in amount mode: the percentages do not exist yet, because
        # converting cups to grams needs densities from the database. The route
        # fills them in and validates then.
        if uses_amounts(self.ingredients):
            return self
        try:
            validate_percentages(
                [Ingredient(i.name, i.kind, i.percentage or 0.0) for i in self.ingredients]
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
        if self.ingredients is None:
            return self
        _require_consistent_form(self)
        if uses_amounts(self.ingredients):
            return self
        try:
            validate_percentages(
                [Ingredient(i.name, i.kind, i.percentage or 0.0) for i in self.ingredients]
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
    display: MeasureDisplay | None = None
    """How to measure `grams` in the caller's units. Sibling, never a replacement:
    `grams` stays the number every calculation uses."""


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
