"""Fermentation rate model and ETA prediction (docs/PLAN.md §5).

Pure functions over a coefficient snapshot, so the model can be exercised and
calibrated without a database or a running app.

The shape, per the plan:

    rate = base_rate * Q10^((T - T_ref)/10) * (inoculation/ref)^k * vigour
    eta  = target_rise_fraction / rate

Known limitations, stated plainly because they matter for how results are shown:

* **Rise is treated as linear in time.** Real dough accelerates as the yeast
  population grows, then plateaus as it runs out of food and gas escapes. Over a
  single proof window the straight-line approximation is close enough to be
  useful, and every logged check re-fits it (`refit_remaining_hours`), which is
  what actually keeps a long proof honest.
* **The result is a window, not an instant.** With no checks the spread is wide
  by design; presenting a bare timestamp would imply precision the model does not
  have.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from app.config import Settings, get_settings

# Outside this range the model is extrapolating nonsense: yeast is dormant below
# freezing and dying above ~45C.
MIN_MODEL_TEMP_C = 1.0
MAX_MODEL_TEMP_C = 45.0


@dataclass(frozen=True, slots=True)
class Coefficients:
    ref_temp_c: float
    base_rise_per_hour: float
    q10_warm: float
    q10_cold: float
    cold_threshold_c: float
    ref_starter_pct: float
    inoculation_exponent: float
    ref_peak_hours: float
    vigour_min: float
    vigour_max: float
    base_spread: float
    min_spread: float


def coefficients(settings: Settings | None = None) -> Coefficients:
    s = settings or get_settings()
    return Coefficients(
        ref_temp_c=s.ferment_ref_temp_c,
        base_rise_per_hour=s.ferment_base_rise_per_hour,
        q10_warm=s.ferment_q10_warm,
        q10_cold=s.ferment_q10_cold,
        cold_threshold_c=s.ferment_cold_threshold_c,
        ref_starter_pct=s.ferment_ref_starter_pct,
        inoculation_exponent=s.ferment_inoculation_exponent,
        ref_peak_hours=s.ferment_ref_peak_hours,
        vigour_min=s.ferment_vigour_min,
        vigour_max=s.ferment_vigour_max,
        base_spread=s.ferment_base_spread,
        min_spread=s.ferment_min_spread,
    )


def temperature_factor(temp_c: float, c: Coefficients) -> float:
    """Rate multiplier relative to the reference temperature.

    Piecewise Q10 — steeper in the cold — and continuous at the threshold, so a
    dough cooling through it does not jump.
    """
    temp = min(max(temp_c, MIN_MODEL_TEMP_C), MAX_MODEL_TEMP_C)

    if temp >= c.cold_threshold_c:
        return float(c.q10_warm ** ((temp - c.ref_temp_c) / 10))

    at_threshold = c.q10_warm ** ((c.cold_threshold_c - c.ref_temp_c) / 10)
    return float(at_threshold * c.q10_cold ** ((temp - c.cold_threshold_c) / 10))


def inoculation_factor(starter_pct: float, c: Coefficients) -> float:
    """Rate multiplier for the amount of starter, sub-linear in the ratio."""
    if starter_pct <= 0:
        raise ValueError("starter_pct must be positive")
    return float((starter_pct / c.ref_starter_pct) ** c.inoculation_exponent)


def predict_rate(dough_temp_c: float, starter_pct: float, vigour: float, c: Coefficients) -> float:
    """Rise fraction per hour."""
    return (
        c.base_rise_per_hour
        * temperature_factor(dough_temp_c, c)
        * inoculation_factor(starter_pct, c)
        * vigour
    )


def predict_duration_hours(
    target_rise_pct: float,
    dough_temp_c: float,
    starter_pct: float,
    vigour: float,
    c: Coefficients,
) -> float:
    """Hours to reach `target_rise_pct` from the start of the proof."""
    if target_rise_pct <= 0:
        raise ValueError("target_rise_pct must be positive")
    rate = predict_rate(dough_temp_c, starter_pct, vigour, c)
    return (target_rise_pct / 100) / rate


def spread_fraction(check_count: int, c: Coefficients) -> float:
    """How wide the window is, as a fraction of the estimate.

    Narrows with each observation and never reaches zero — the model does not
    earn certainty just because someone looked at the dough four times.
    """
    spread = c.base_spread / (1 + 0.8 * max(check_count, 0))
    return max(spread, c.min_spread)


def confidence_window(hours: float, check_count: int, c: Coefficients) -> tuple[float, float]:
    """(earliest, latest) hours for the estimate."""
    spread = spread_fraction(check_count, c)
    return hours * (1 - spread), hours * (1 + spread)


def refit_remaining_hours(
    *,
    target_rise_pct: float,
    observed_rise_pct: float,
    elapsed_hours: float,
    model_rate: float,
    check_count: int,
) -> float:
    """Hours still to go, blending the model with what the dough is actually doing.

    The blend shifts towards observation as checks accumulate: one data point on a
    young proof is noisy (dough barely moves in the first hour), but by the third
    check the dough is a better guide than the model.
    """
    if observed_rise_pct >= target_rise_pct:
        return 0.0

    remaining_rise = (target_rise_pct - observed_rise_pct) / 100

    # Too early to infer a rate from: a near-zero elapsed time makes the
    # observed rate explode or collapse.
    if elapsed_hours < 0.25:
        return remaining_rise / model_rate

    observed_rate = (observed_rise_pct / 100) / elapsed_hours
    if observed_rate <= 0:
        # Nothing has happened yet. Trust the model, but the dough is behind it.
        return remaining_rise / model_rate

    weight = check_count / (check_count + 1)
    blended_rate = weight * observed_rate + (1 - weight) * model_rate
    return remaining_rise / blended_rate


def estimate_vigour(peak_times: Sequence[tuple[float, float | None]], c: Coefficients) -> float:
    """Starter vigour from recent time-to-peak observations.

    Each entry is (hours_to_peak, temperature_at_peak). Times are normalised to
    the reference temperature before comparison, so a starter that peaked fast
    only because the kitchen was hot is not credited with being vigorous.

    Returns 1.0 (the reference starter) when there is nothing to go on.
    """
    if not peak_times:
        return 1.0

    normalised = [
        hours * temperature_factor(temp if temp is not None else c.ref_temp_c, c)
        for hours, temp in peak_times
        if hours > 0
    ]
    if not normalised:
        return 1.0

    # Median, not mean: one forgotten starter left out overnight should not drag
    # the estimate down.
    typical = statistics.median(normalised)
    if typical <= 0:
        return 1.0

    return min(max(c.ref_peak_hours / typical, c.vigour_min), c.vigour_max)
