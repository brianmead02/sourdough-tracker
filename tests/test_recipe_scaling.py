"""Baker's percentage arithmetic. Pure functions — no database."""

import pytest

from app.models.recipe import IngredientKind as K
from app.services.recipes import Ingredient, RecipeError, scale, validate_percentages

# A plain country loaf: 100% flour, 70% water, 2% salt, 20% starter.
COUNTRY = [
    Ingredient("bread flour", K.flour, 90),
    Ingredient("whole wheat", K.flour, 10),
    Ingredient("water", K.liquid, 70),
    Ingredient("salt", K.salt, 2),
    Ingredient("levain", K.starter, 20),
]


# --- the sums-to-100 invariant ------------------------------------------------


def test_valid_formula_passes() -> None:
    validate_percentages(COUNTRY)


def test_flour_must_sum_to_100() -> None:
    broken = [Ingredient("bread flour", K.flour, 80), Ingredient("water", K.liquid, 70)]
    with pytest.raises(RecipeError, match="sum to 100"):
        validate_percentages(broken)


def test_small_rounding_in_a_blend_is_forgiven() -> None:
    """33.3 + 33.3 + 33.4 is how people actually write a three-flour blend."""
    validate_percentages(
        [
            Ingredient("a", K.flour, 33.3),
            Ingredient("b", K.flour, 33.3),
            Ingredient("c", K.flour, 33.4),
            Ingredient("water", K.liquid, 70),
        ]
    )


def test_a_recipe_needs_flour() -> None:
    with pytest.raises(RecipeError, match="at least one flour"):
        validate_percentages([Ingredient("water", K.liquid, 70)])


def test_empty_recipe_is_rejected() -> None:
    with pytest.raises(RecipeError, match="at least one ingredient"):
        validate_percentages([])


def test_negative_percentages_are_rejected() -> None:
    with pytest.raises(RecipeError, match="positive"):
        validate_percentages(
            [Ingredient("bread flour", K.flour, 100), Ingredient("x", K.liquid, -5)]
        )


# --- scaling ------------------------------------------------------------------


def test_scaling_by_flour_weight_is_the_identity_case() -> None:
    result = scale(COUNTRY, flour_g=1000)
    grams = {i.name: i.grams for i in result.ingredients}
    assert grams == {
        "bread flour": 900.0,
        "whole wheat": 100.0,
        "water": 700.0,
        "salt": 20.0,
        "levain": 200.0,
    }
    assert result.added_flour_g == 1000.0
    assert result.total_dough_g == 1920.0


def test_scaling_by_dough_weight_hits_the_target() -> None:
    result = scale(COUNTRY, dough_weight_g=1920)
    assert result.added_flour_g == pytest.approx(1000.0, abs=0.5)
    assert result.total_dough_g == pytest.approx(1920.0, abs=0.5)


def test_scaling_is_proportional() -> None:
    small = scale(COUNTRY, flour_g=500)
    large = scale(COUNTRY, flour_g=1000)
    assert large.total_dough_g == pytest.approx(small.total_dough_g * 2)


def test_loaf_division_splits_the_dough() -> None:
    result = scale(COUNTRY, dough_weight_g=1800, loaf_count=2)
    assert result.loaf_weight_g == pytest.approx(900.0, abs=0.5)
    assert result.loaf_count == 2


def test_exactly_one_basis_is_required() -> None:
    with pytest.raises(RecipeError, match="exactly one"):
        scale(COUNTRY)
    with pytest.raises(RecipeError, match="exactly one"):
        scale(COUNTRY, flour_g=500, dough_weight_g=1000)


def test_loaf_count_must_be_positive() -> None:
    with pytest.raises(RecipeError, match="at least 1"):
        scale(COUNTRY, flour_g=500, loaf_count=0)


def test_scaling_validates_the_formula() -> None:
    with pytest.raises(RecipeError, match="sum to 100"):
        scale([Ingredient("f", K.flour, 50), Ingredient("w", K.liquid, 70)], flour_g=500)


# --- stated vs true hydration -------------------------------------------------


def test_stated_hydration_is_the_written_water_percentage() -> None:
    assert scale(COUNTRY, flour_g=1000).stated_hydration_pct == 70.0


def test_true_hydration_accounts_for_the_starter() -> None:
    """The levain is flour and water too, so the dough is not really at 70%.

    200 g of 100%-hydration levain is 100 g flour + 100 g water:
        water = 700 + 100 = 800,  flour = 1000 + 100 = 1100  ->  72.7%
    """
    result = scale(COUNTRY, flour_g=1000, starter_hydration_pct=100)
    assert result.total_flour_g == pytest.approx(1100.0)
    assert result.total_water_g == pytest.approx(800.0)
    assert result.true_hydration_pct == pytest.approx(72.7, abs=0.1)


def test_a_stiff_starter_lowers_true_hydration() -> None:
    """A 50%-hydration levain brings proportionally more flour than water."""
    loose = scale(COUNTRY, flour_g=1000, starter_hydration_pct=100)
    stiff = scale(COUNTRY, flour_g=1000, starter_hydration_pct=50)
    assert stiff.true_hydration_pct < loose.true_hydration_pct


def test_without_starter_the_two_hydrations_agree() -> None:
    yeasted = [
        Ingredient("bread flour", K.flour, 100),
        Ingredient("water", K.liquid, 65),
        Ingredient("salt", K.salt, 2),
    ]
    result = scale(yeasted, flour_g=1000)
    assert result.stated_hydration_pct == pytest.approx(result.true_hydration_pct)


def test_derived_percentages_are_reported() -> None:
    result = scale(COUNTRY, flour_g=1000)
    assert result.salt_pct == 2.0
    assert result.starter_pct == 20.0


def test_inclusions_add_weight_without_changing_hydration() -> None:
    with_olives = [*COUNTRY, Ingredient("olives", K.inclusion, 15)]
    plain = scale(COUNTRY, flour_g=1000)
    olived = scale(with_olives, flour_g=1000)
    assert olived.total_dough_g == pytest.approx(plain.total_dough_g + 150)
    assert olived.true_hydration_pct == pytest.approx(plain.true_hydration_pct)
