"""The fermentation model. Pure functions — no database.

These tests pin down *behaviour a baker would recognise* rather than exact
numbers, because the coefficients are expected to move during calibration. Where
a specific number is asserted it is one the model defines by construction (e.g.
the reference conditions), not an empirical claim about real dough.
"""

import pytest

from app.services.fermentation import (
    MAX_MODEL_TEMP_C,
    Coefficients,
    coefficients,
    confidence_window,
    estimate_vigour,
    inoculation_factor,
    predict_duration_hours,
    predict_rate,
    refit_remaining_hours,
    spread_fraction,
    temperature_factor,
)

C = coefficients()


def hours_at(
    temp: float, starter_pct: float = 20.0, vigour: float = 1.0, rise: float = 75.0
) -> float:
    return predict_duration_hours(rise, temp, starter_pct, vigour, C)


# --- temperature --------------------------------------------------------------


def test_reference_temperature_is_the_unit_point() -> None:
    assert temperature_factor(C.ref_temp_c, C) == pytest.approx(1.0)


def test_warmer_dough_ferments_faster() -> None:
    assert temperature_factor(30, C) > temperature_factor(24, C) > temperature_factor(20, C)


def test_warm_q10_holds_over_ten_degrees() -> None:
    ratio = temperature_factor(C.ref_temp_c + 10, C) / temperature_factor(C.ref_temp_c, C)
    assert ratio == pytest.approx(C.q10_warm)


def test_cold_curve_is_steeper_than_the_warm_one() -> None:
    """Retard must slow disproportionately, or overnight fridge proofs come out absurd."""
    warm_decade = temperature_factor(C.cold_threshold_c, C) / temperature_factor(
        C.cold_threshold_c + 10, C
    )
    cold_decade = temperature_factor(C.cold_threshold_c - 10, C) / temperature_factor(
        C.cold_threshold_c, C
    )
    assert (1 / cold_decade) > warm_decade


def test_temperature_curve_is_continuous_at_the_threshold() -> None:
    """A dough cooling through the threshold must not jump."""
    just_above = temperature_factor(C.cold_threshold_c + 0.001, C)
    just_below = temperature_factor(C.cold_threshold_c - 0.001, C)
    assert just_above == pytest.approx(just_below, rel=1e-3)


def test_temperature_is_clamped_to_a_survivable_range() -> None:
    """Nobody proofs at 200C; the model must not return a fantasy number."""
    assert temperature_factor(500, C) == temperature_factor(MAX_MODEL_TEMP_C, C)
    assert temperature_factor(-40, C) == temperature_factor(1.0, C)


def test_fridge_retard_takes_far_longer_than_room_temperature() -> None:
    assert hours_at(4) > hours_at(24) * 4


# --- inoculation --------------------------------------------------------------


def test_reference_inoculation_is_the_unit_point() -> None:
    assert inoculation_factor(C.ref_starter_pct, C) == pytest.approx(1.0)


def test_more_starter_ferments_faster() -> None:
    assert (
        hours_at(24, starter_pct=40) < hours_at(24, starter_pct=20) < hours_at(24, starter_pct=10)
    )


def test_doubling_the_starter_does_not_halve_the_time() -> None:
    """Sub-linear by design — the exponent is below 1."""
    assert hours_at(24, starter_pct=40) > hours_at(24, starter_pct=20) / 2


def test_zero_starter_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        inoculation_factor(0, C)


# --- duration -----------------------------------------------------------------


def test_reference_conditions_match_the_configured_base_rate() -> None:
    """75% rise at 0.15/hour is 5 hours — the definition of the base rate."""
    expected = (75 / 100) / C.base_rise_per_hour
    assert hours_at(C.ref_temp_c) == pytest.approx(expected)


def test_a_bigger_target_takes_longer() -> None:
    assert hours_at(24, rise=100) > hours_at(24, rise=50)


def test_vigorous_starter_is_faster() -> None:
    assert hours_at(24, vigour=1.5) < hours_at(24, vigour=1.0) < hours_at(24, vigour=0.6)


def test_non_positive_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        predict_duration_hours(0, 24, 20, 1.0, C)


def test_rate_is_the_inverse_of_duration() -> None:
    rate = predict_rate(26, 25, 1.1, C)
    hours = predict_duration_hours(75, 26, 25, 1.1, C)
    assert rate * hours == pytest.approx(0.75)


# --- confidence ---------------------------------------------------------------


def test_window_starts_wide_and_narrows_with_checks() -> None:
    widths = [spread_fraction(n, C) for n in range(5)]
    assert widths == sorted(widths, reverse=True)
    assert widths[0] == pytest.approx(C.base_spread)


def test_window_never_collapses_to_certainty() -> None:
    """Looking at the dough a hundred times does not make the model exact."""
    assert spread_fraction(100, C) >= C.min_spread


def test_window_brackets_the_estimate() -> None:
    low, high = confidence_window(6.0, 0, C)
    assert low < 6.0 < high


# --- re-fitting against observation -------------------------------------------


def test_target_already_reached_means_no_time_left() -> None:
    assert (
        refit_remaining_hours(
            target_rise_pct=75,
            observed_rise_pct=80,
            elapsed_hours=4,
            model_rate=0.15,
            check_count=1,
        )
        == 0.0
    )


def test_dough_rising_faster_than_predicted_shortens_the_estimate() -> None:
    """50% in 2 hours against a 0.15/h model: the dough is ahead, so finish sooner."""
    remaining = refit_remaining_hours(
        target_rise_pct=75,
        observed_rise_pct=50,
        elapsed_hours=2,
        model_rate=0.15,
        check_count=3,
    )
    model_only = (75 - 50) / 100 / 0.15
    assert remaining < model_only


def test_sluggish_dough_lengthens_the_estimate() -> None:
    remaining = refit_remaining_hours(
        target_rise_pct=75,
        observed_rise_pct=10,
        elapsed_hours=3,
        model_rate=0.15,
        check_count=3,
    )
    model_only = (75 - 10) / 100 / 0.15
    assert remaining > model_only


def test_observation_carries_more_weight_as_checks_accumulate() -> None:
    kwargs = {
        "target_rise_pct": 75.0,
        "observed_rise_pct": 10.0,
        "elapsed_hours": 3.0,
        "model_rate": 0.15,
    }
    one = refit_remaining_hours(**kwargs, check_count=1)  # type: ignore[arg-type]
    five = refit_remaining_hours(**kwargs, check_count=5)  # type: ignore[arg-type]
    assert five > one  # sluggish dough: more checks means trusting the dough more


def test_very_early_check_falls_back_to_the_model() -> None:
    """Dough barely moves in the first minutes; an inferred rate would be garbage."""
    remaining = refit_remaining_hours(
        target_rise_pct=75,
        observed_rise_pct=1,
        elapsed_hours=0.05,
        model_rate=0.15,
        check_count=1,
    )
    assert remaining == pytest.approx((75 - 1) / 100 / 0.15)


def test_no_rise_at_all_does_not_divide_by_zero() -> None:
    remaining = refit_remaining_hours(
        target_rise_pct=75,
        observed_rise_pct=0,
        elapsed_hours=2,
        model_rate=0.15,
        check_count=2,
    )
    assert remaining == pytest.approx(75 / 100 / 0.15)


# --- vigour -------------------------------------------------------------------


def test_no_observations_means_a_reference_starter() -> None:
    assert estimate_vigour([], C) == 1.0


def test_peaking_at_the_reference_time_is_reference_vigour() -> None:
    assert estimate_vigour([(C.ref_peak_hours, C.ref_temp_c)], C) == pytest.approx(1.0)


def test_fast_peaking_starter_is_vigorous() -> None:
    assert estimate_vigour([(3.0, C.ref_temp_c)], C) > 1.0


def test_slow_peaking_starter_is_sluggish() -> None:
    assert estimate_vigour([(12.0, C.ref_temp_c)], C) < 1.0


def test_heat_is_not_mistaken_for_vigour() -> None:
    """Peaking in 4h in a hot kitchen is not the same as peaking in 4h at 24C."""
    hot = estimate_vigour([(4.0, 30.0)], C)
    reference = estimate_vigour([(4.0, C.ref_temp_c)], C)
    assert hot < reference


def test_vigour_is_clamped() -> None:
    assert estimate_vigour([(0.1, C.ref_temp_c)], C) == C.vigour_max
    assert estimate_vigour([(500.0, C.ref_temp_c)], C) == C.vigour_min


def test_one_outlier_does_not_dominate() -> None:
    """Median, not mean: a starter forgotten overnight once is not a slow starter."""
    consistent = [(4.0, C.ref_temp_c)] * 4
    with_outlier = [*consistent, (40.0, C.ref_temp_c)]
    assert estimate_vigour(with_outlier, C) == pytest.approx(estimate_vigour(consistent, C))


def test_missing_temperature_assumes_reference() -> None:
    assert estimate_vigour([(4.0, None)], C) == pytest.approx(
        estimate_vigour([(4.0, C.ref_temp_c)], C)
    )


# --- coefficients are configuration, not constants ----------------------------


def test_model_responds_to_recalibrated_coefficients() -> None:
    """The plan requires tuning without a code change."""
    faster = Coefficients(**{**vars_of(C), "base_rise_per_hour": C.base_rise_per_hour * 2})
    assert predict_duration_hours(75, 24, 20, 1.0, faster) == pytest.approx(
        predict_duration_hours(75, 24, 20, 1.0, C) / 2
    )


def vars_of(c: Coefficients) -> dict[str, float]:
    return {field: getattr(c, field) for field in c.__slots__}
