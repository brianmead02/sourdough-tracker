"""Baker's percentage arithmetic.

Convention: every ingredient is a percentage of the *added flour*, and the added
flour sums to exactly 100%. A recipe at 70% hydration, 2% salt and 20% starter
therefore totals 192% of the flour weight.

The subtlety worth getting right is that the starter is itself flour and water.
"Hydration 70%" as written on the recipe is not the hydration of the dough you
actually end up with, so both numbers are reported:

    stated hydration = liquid / added flour
    true hydration   = (liquid + water in starter) / (added flour + flour in starter)

Grams are never stored — they are a function of batch size (docs/PLAN.md §3).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.recipe import IngredientKind

# Flour percentages must sum to 100, within a tolerance that forgives a blend
# written as 33.3/33.3/33.4.
FLOUR_SUM_TOLERANCE = 0.5


@dataclass(frozen=True, slots=True)
class Ingredient:
    name: str
    kind: IngredientKind
    percentage: float


@dataclass(slots=True)
class ScaledIngredient:
    name: str
    kind: IngredientKind
    percentage: float
    grams: float


@dataclass(slots=True)
class ScaledRecipe:
    added_flour_g: float
    total_dough_g: float
    ingredients: list[ScaledIngredient]
    stated_hydration_pct: float
    true_hydration_pct: float
    total_flour_g: float
    total_water_g: float
    salt_pct: float
    starter_pct: float
    loaf_count: int
    loaf_weight_g: float


class RecipeError(ValueError):
    """The formula does not describe a bakeable dough."""


def validate_percentages(ingredients: Sequence[Ingredient]) -> None:
    if not ingredients:
        raise RecipeError("a recipe needs at least one ingredient")

    if any(i.percentage <= 0 for i in ingredients):
        raise RecipeError("every ingredient percentage must be positive")

    flour_total = sum(i.percentage for i in ingredients if i.kind is IngredientKind.flour)
    if flour_total == 0:
        raise RecipeError("a recipe needs at least one flour")
    if abs(flour_total - 100) > FLOUR_SUM_TOLERANCE:
        raise RecipeError(
            f"flour percentages must sum to 100%, got {flour_total:g}% — "
            "every other ingredient is a percentage of the flour"
        )


def total_percentage(ingredients: Sequence[Ingredient]) -> float:
    return sum(i.percentage for i in ingredients)


def _sum_of(ingredients: Sequence[Ingredient], kind: IngredientKind) -> float:
    return sum(i.percentage for i in ingredients if i.kind is kind)


def scale(
    ingredients: Sequence[Ingredient],
    *,
    starter_hydration_pct: float = 100.0,
    dough_weight_g: float | None = None,
    flour_g: float | None = None,
    loaf_count: int = 1,
) -> ScaledRecipe:
    """Resolve percentages into grams for a chosen batch size.

    Provide exactly one of `dough_weight_g` (total dough) or `flour_g` (added
    flour); `loaf_count` divides the result for display but does not change it.
    """
    if (dough_weight_g is None) == (flour_g is None):
        raise RecipeError("provide exactly one of dough_weight_g or flour_g")
    if loaf_count < 1:
        raise RecipeError("loaf_count must be at least 1")

    validate_percentages(ingredients)

    total_pct = total_percentage(ingredients)
    if flour_g is None:
        assert dough_weight_g is not None
        flour_g = dough_weight_g * 100 / total_pct

    scaled = [
        ScaledIngredient(
            name=i.name,
            kind=i.kind,
            percentage=i.percentage,
            grams=round(flour_g * i.percentage / 100, 1),
        )
        for i in ingredients
    ]
    total_dough = round(sum(i.grams for i in scaled), 1)

    liquid_pct = _sum_of(ingredients, IngredientKind.liquid)
    salt_pct = _sum_of(ingredients, IngredientKind.salt)
    starter_pct = _sum_of(ingredients, IngredientKind.starter)

    # Split the starter into its flour and water halves.
    starter_g = flour_g * starter_pct / 100
    starter_flour_g = starter_g / (1 + starter_hydration_pct / 100)
    starter_water_g = starter_g - starter_flour_g

    total_flour_g = flour_g + starter_flour_g
    total_water_g = flour_g * liquid_pct / 100 + starter_water_g

    return ScaledRecipe(
        added_flour_g=round(flour_g, 1),
        total_dough_g=total_dough,
        ingredients=scaled,
        stated_hydration_pct=round(liquid_pct, 1),
        true_hydration_pct=round(total_water_g / total_flour_g * 100, 1) if total_flour_g else 0.0,
        total_flour_g=round(total_flour_g, 1),
        total_water_g=round(total_water_g, 1),
        salt_pct=round(salt_pct, 1),
        starter_pct=round(starter_pct, 1),
        loaf_count=loaf_count,
        loaf_weight_g=round(total_dough / loaf_count, 1),
    )
