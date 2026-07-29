"""Stock valuation arithmetic. Pure functions — no database."""

import pytest

from app.services.inventory import cost_of, split_blend, weighted_average_cost_per_kg


def test_average_cost_of_a_single_purchase() -> None:
    """2 kg for £4 is £2/kg."""
    assert weighted_average_cost_per_kg(2000, 4.0) == 2.0


def test_average_is_weighted_by_quantity_not_by_purchase_count() -> None:
    """9 kg at £1 and 1 kg at £11 averages £2/kg, not £6."""
    assert weighted_average_cost_per_kg(10_000, 9 * 1.0 + 1 * 11.0) == 2.0


def test_no_purchases_means_no_valuation() -> None:
    assert weighted_average_cost_per_kg(0, 0.0) is None


def test_cost_of_a_quantity() -> None:
    assert cost_of(500, 2.0) == 1.0
    assert cost_of(1000, 2.0) == 2.0


def test_cost_is_unknown_without_a_price() -> None:
    """Unpriced stock must yield None, never a confident zero."""
    assert cost_of(500, None) is None


def test_blend_splits_by_percentage() -> None:
    assert split_blend({"bread flour": 80, "rye": 20}, 1000) == {
        "bread flour": 800.0,
        "rye": 200.0,
    }


def test_blend_split_conserves_total_weight() -> None:
    parts = split_blend({"a": 33.3, "b": 33.3, "c": 33.4}, 900)
    assert sum(parts.values()) == pytest.approx(900.0)
