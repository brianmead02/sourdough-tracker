"""Contracts for units, densities and conversions.

The shape that matters is `MeasureDisplay`. It is attached as a **sibling** of
every gram field rather than replacing it, so existing clients keep working and
nothing has to be versioned — and it always carries `basis` and `approximate`,
because a ±20% fallback rendered as though it were measured is the failure this
whole feature is built to avoid.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.recipe import IngredientKind
from app.services.measurements import Basis, Method, System, Unit, UnitFamily

GramsPerCup = Annotated[float, Field(gt=0, le=2000)]
"""Wide bounds on purpose: this rejects typos and nothing else. The tightest
real value is ~84 (cocoa) and the loosest ~340 (molasses)."""


class UnitInfo(BaseModel):
    """One unit and its exact relationship to the base of its family."""

    unit: Unit
    label: str
    family: UnitFamily
    grams: float | None = None
    """Grams in one of this unit. Mass only; exact."""
    millilitres: float | None = None
    """Millilitres in one of this unit. Volume only; exact."""


class UnitCatalogueResponse(BaseModel):
    units: list[UnitInfo]
    note: str
    """Why volume units have no gram figure here."""


class IngredientMeasureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    kind: IngredientKind
    grams_per_cup: float
    method: Method
    source: str
    aliases: list[str]
    volume_allowed: bool
    reason: str | None = None
    overridden: bool = False
    """True when this is the caller's own measurement, not the published value."""


class OverrideRequest(BaseModel):
    grams_per_cup: GramsPerCup
    note: Annotated[str | None, Field(default=None, max_length=200)] = None


class ConvertItem(BaseModel):
    value: Annotated[float, Field(ge=-100, le=1_000_000)]
    """Lower bound allows Fahrenheit and Celsius below zero."""
    from_unit: Annotated[Unit, Field(alias="from")]
    to_unit: Annotated[Unit, Field(alias="to")]
    ingredient: Annotated[str | None, Field(default=None, max_length=80)] = None
    kind: IngredientKind | None = None

    model_config = ConfigDict(populate_by_name=True)


class ConvertRequest(BaseModel):
    items: Annotated[list[ConvertItem], Field(min_length=1, max_length=50)]
    """A batch, because a client rendering a recipe needs every line at once and
    eight round-trips to convert eight ingredients is the wrong shape."""


class ConversionResult(BaseModel):
    value: float | None
    unit: Unit
    basis: Basis | None = None
    approximate: bool = False
    source_slug: str | None = None
    error: str | None = None
    """Set instead of `value` when the conversion was refused — salt without a
    named variety, or any starter. Per-item so one refusal does not fail a batch."""


class ConvertResponse(BaseModel):
    results: list[ConversionResult]


class MeasureDisplay(BaseModel):
    """A quantity rendered for a baker, carrying its own inaccuracy."""

    text: str
    system: System
    basis: Basis
    approximate: bool
    grams: float
    """What `text` weighs if measured exactly as written."""
    drift_pct: float
    advise_weighing: bool
    """True when the quantity is too small for a spoon to express honestly."""
