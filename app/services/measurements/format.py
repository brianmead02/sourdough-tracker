"""Turning grams into something a baker can actually measure.

`500 g ÷ 127 g/cup = 3.937 cups` is true and useless. Nobody owns a 3.937-cup
measure. This module renders a mass as terms a real measuring set can express,
and — because the result is necessarily lossy — reports how far off it is.

**The obvious rule is wrong.** Rounding the leading term to the nearest fraction
overshoots, which makes the remainder negative, which drops it: 340 g of water
renders as "1½ cups", 4.4% high. Fifteen grams of water is 3% hydration on a
500 g loaf. So candidates are generated and scored instead:

  * every term but the last is *floored*, keeping the remainder positive
  * the last term rounds to nearest, since nothing below it can carry a remainder
  * fractions are restricted per unit to what exists — tablespoons come in halves,
    because `1⅔ tbsp` is not a measurement anyone can make (`5 tsp` is)
  * the fewest terms that land inside tolerance wins

Small quantities cannot be rescued by any of this. 10 g of fine salt is 1.667
tsp and no spoon set has a third of a teaspoon, so anything under
`WEIGH_BELOW_GRAMS` is flagged `advise_weighing` rather than presented as though
the spoon were precise.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from app.services.measurements.convert import (
    WEIGH_BELOW_GRAMS,
    Basis,
    Density,
    from_grams,
)
from app.services.measurements.units import (
    GRAMS_PER_POUND,
    LABELS,
    ML_PER,
    System,
    Unit,
)

GLYPHS: dict[Fraction, str] = {
    Fraction(1, 8): "⅛",
    Fraction(1, 4): "¼",
    Fraction(1, 3): "⅓",
    Fraction(1, 2): "½",
    Fraction(2, 3): "⅔",
    Fraction(3, 4): "¾",
}

# What each measure is actually graduated in. A cup set has thirds; a spoon set
# does not. Offering ⅓ tbsp would produce strings that cannot be followed.
FRACTIONS: dict[Unit, tuple[Fraction, ...]] = {
    Unit.cup: (
        Fraction(0),
        Fraction(1, 8),
        Fraction(1, 4),
        Fraction(1, 3),
        Fraction(1, 2),
        Fraction(2, 3),
        Fraction(3, 4),
    ),
    Unit.tablespoon: (Fraction(0), Fraction(1, 2)),
    Unit.teaspoon: (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)),
}

#: Largest to smallest. Volume rendering cascades down this and no further.
LADDER: tuple[Unit, ...] = (Unit.cup, Unit.tablespoon, Unit.teaspoon)

MAX_TERMS = 3

#: How much of a unit anyone actually says out loud before switching to a bigger
#: one. Measuring sets cascade — 3 tsp make a tbsp, 4 tbsp make a quarter cup —
#: so "200 tsp" is arithmetically perfect and useless. Cups have no ceiling:
#: "8⅓ cups" is a normal thing to read in a recipe.
MAX_PER_TERM: dict[Unit, float] = {
    Unit.cup: float("inf"),
    Unit.tablespoon: 3.75,
    Unit.teaspoon: 3.0,
}

#: If the best volume rendering is further out than this, volume is the wrong
#: answer entirely and grams are given instead. 1 g of honey is 0.7 ml, and the
#: smallest thing a spoon set expresses is a quarter teaspoon at 1.23 ml — so
#: "¼ tsp" would be 77% high. A precise gram figure the baker cannot measure with
#: a cup beats a spoon measurement that is simply wrong.
MAX_DRIFT_PCT = 10.0


@dataclass(frozen=True, slots=True)
class Term:
    whole: int
    fraction: Fraction
    unit: Unit

    def __str__(self) -> str:
        singular, plural = LABELS[self.unit]
        label = singular if self.amount <= 1 else plural
        if self.whole and self.fraction:
            return f"{self.whole}{GLYPHS[self.fraction]} {label}"
        if self.whole:
            return f"{self.whole} {label}"
        return f"{GLYPHS[self.fraction]} {label}"

    @property
    def amount(self) -> float:
        return self.whole + float(self.fraction)


@dataclass(frozen=True, slots=True)
class Measurement:
    """A renderable quantity that carries its own inaccuracy."""

    text: str
    terms: tuple[Term, ...]
    grams: float
    """What `text` weighs if a baker measures it exactly as written."""
    requested_grams: float
    basis: Basis
    approximate: bool
    advise_weighing: bool

    @property
    def drift_pct(self) -> float:
        if not self.requested_grams:
            return 0.0
        return (self.grams - self.requested_grams) / self.requested_grams * 100


def _floor_fraction(value: float, allowed: tuple[Fraction, ...]) -> tuple[int, Fraction]:
    whole = int(value)
    remainder = value - whole
    candidates = [f for f in allowed if float(f) <= remainder + 1e-9]
    return whole, max(candidates, key=float) if candidates else Fraction(0)


def _nearest_fraction(value: float, allowed: tuple[Fraction, ...]) -> tuple[int, Fraction]:
    whole = int(value)
    remainder = value - whole
    options = (*allowed, Fraction(1))
    best = min(options, key=lambda f: abs(float(f) - remainder))
    if best == 1:
        return whole + 1, Fraction(0)
    return whole, best


def _candidate(total_ml: float, rungs: tuple[Unit, ...]) -> tuple[Term, ...]:
    """Build one rendering: floor every term but the last, round the last."""
    terms: list[Term] = []
    remaining = total_ml
    for index, unit in enumerate(rungs):
        size = float(ML_PER[unit])
        allowed = FRACTIONS[unit]
        is_last = index == len(rungs) - 1
        whole, fraction = (
            _nearest_fraction(remaining / size, allowed)
            if is_last
            else _floor_fraction(remaining / size, allowed)
        )
        if whole or fraction:
            terms.append(Term(whole, fraction, unit))
            remaining -= (whole + float(fraction)) * size
        elif is_last and not terms:
            # Smaller than the smallest graduation we offer; say the smallest
            # thing rather than nothing at all.
            terms.append(Term(0, allowed[1], unit))
    return tuple(terms)


def _smallest_step(unit: Unit) -> float:
    """Millilitres in the finest graduation this unit offers."""
    fractions = [f for f in FRACTIONS[unit] if f]
    return float(ML_PER[unit]) * float(min(fractions, key=float))


def _volume_terms(total_ml: float) -> tuple[Term, ...]:
    """Best rendering across every plausible starting unit.

    Candidates are generated from each usable rung, not only the largest, because
    the largest is often the wrong place to start: 10 g of salt is 8.2 ml, which
    from the tablespoon rung reads "½ tbsp + ¼ tsp" and from the teaspoon rung
    reads "1¾ tsp" — the same amount, one term, far clearer.

    A rung becomes usable at its *smallest graduation*, not a whole unit;
    requiring a whole cup made 227 ml render as "15½ tbsp" instead of
    "¾ cup + 3½ tbsp".
    """
    first = next(
        (i for i, unit in enumerate(LADDER) if total_ml >= _smallest_step(unit)),
        len(LADDER) - 1,
    )

    tolerance_ml = max(total_ml * 0.01, float(ML_PER[Unit.teaspoon]) * 0.1)
    within: list[tuple[int, float, tuple[Term, ...]]] = []
    everything: list[tuple[float, int, tuple[Term, ...]]] = []

    for start in range(first, len(LADDER)):
        available = LADDER[start:]
        for count in range(1, min(MAX_TERMS, len(available)) + 1):
            terms = _candidate(total_ml, available[:count])
            if not terms:
                continue
            rendered_ml = sum(t.amount * float(ML_PER[t.unit]) for t in terms)
            error = abs(rendered_ml - total_ml)
            if any(t.amount > MAX_PER_TERM[t.unit] for t in terms):
                continue
            everything.append((error, len(terms), terms))
            if error <= tolerance_ml:
                within.append((len(terms), error, terms))

    if within:
        # Accurate enough: prefer the simplest way of saying it.
        return min(within, key=lambda c: (c[0], c[1]))[2]
    if everything:
        # Nothing is accurate enough, so accuracy now outranks brevity.
        return min(everything, key=lambda c: (c[0], c[1]))[2]
    # Every candidate was unsayable. Fall back to the plain leading-unit
    # rendering rather than returning nothing.
    return _candidate(total_ml, LADDER[first : first + 1])


def _metric_text(grams: float) -> str:
    if grams >= 1000:
        kilos = Decimal(str(grams)) / 1000
        return f"{kilos.normalize():f} kg".replace("E+0", "")
    if grams >= 10:
        return f"{round(grams)} g"
    return f"{grams:.1f} g"


def _us_mass_terms(grams: float) -> tuple[str, float]:
    """Ounces and pounds — no density needed, so always available.

    Quarter-ounce granularity is fine for a loaf's worth of flour and hopeless
    for 11 g of salt, which rounds to "0.5 oz" and is 25% high. Past
    MAX_DRIFT_PCT this falls back to grams, exactly as the volume path does.
    """
    pounds_g = float(GRAMS_PER_POUND)
    if grams >= pounds_g:
        whole_pounds = int(grams // pounds_g)
        rest = grams - whole_pounds * pounds_g
        ounces = round(from_grams(rest, Unit.ounce).value * 4) / 4
        if ounces >= 16:
            whole_pounds, ounces = whole_pounds + 1, 0.0
        text = f"{whole_pounds} lb" + (f" {_trim(ounces)} oz" if ounces else "")
        return text, whole_pounds * pounds_g + float(
            Decimal(str(ounces)) * Decimal(str(pounds_g)) / 16
        )
    ounces = round(from_grams(grams, Unit.ounce).value * 4) / 4
    if not ounces:
        return _metric_text(grams), grams
    rendered = float(Decimal(str(ounces)) * Decimal(str(pounds_g)) / 16)
    if grams and abs(rendered - grams) / grams * 100 > MAX_DRIFT_PCT:
        return _metric_text(grams), grams
    return f"{_trim(ounces)} oz", rendered


def _trim(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def describe(
    grams: float, density: Density | None = None, system: System = System.metric
) -> Measurement:
    """Render a gram quantity for the baker's preferred system.

    Metric is grams and kilograms — exact, and what a metric baker's scale shows.
    US prefers volume, because the whole point is bakers who own cups; when no
    density is available (or the ingredient refuses volume, as salt and starter
    do) it falls back to ounces and pounds, which need no density and are exact.
    That fallback is strictly better than refusing to answer.
    """
    if system is System.metric:
        return Measurement(
            text=_metric_text(grams),
            terms=(),
            grams=grams,
            requested_grams=grams,
            basis=Basis.exact,
            approximate=False,
            advise_weighing=False,
        )

    usable = density is not None and density.volume_allowed
    if not usable:
        text, rendered = _us_mass_terms(grams)
        return Measurement(
            text=text,
            terms=(),
            grams=rendered,
            requested_grams=grams,
            basis=Basis.exact,
            approximate=False,
            advise_weighing=False,
        )

    assert density is not None  # narrowed by `usable`
    total_ml = grams / density.grams_per_ml
    terms = _volume_terms(total_ml)
    rendered_ml = sum(t.amount * float(ML_PER[t.unit]) for t in terms)
    rendered_grams = rendered_ml * density.grams_per_ml

    drift = abs(rendered_grams - grams) / grams * 100 if grams else 0.0
    if drift > MAX_DRIFT_PCT:
        # Too small for any spoon to express. Give the exact mass and say so,
        # rather than a measurement that is confidently wrong.
        return Measurement(
            text=_metric_text(grams),
            terms=(),
            grams=grams,
            requested_grams=grams,
            basis=Basis.exact,
            approximate=False,
            advise_weighing=True,
        )

    return Measurement(
        text=" + ".join(str(t) for t in terms),
        terms=terms,
        grams=rendered_grams,
        requested_grams=grams,
        basis=density.basis,
        approximate=True,
        advise_weighing=grams < WEIGH_BELOW_GRAMS,
    )


def cups_from_grams(grams: float, density: Density) -> float:
    """Unrounded cups, for clients that would rather format it themselves."""
    return grams / density.grams_per_cup
