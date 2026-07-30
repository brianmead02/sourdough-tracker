"""Units and the ratios between them.

Every constant here is *defined*, not measured, so each is written at full
precision and computed from its definition rather than transcribed. If a value
looks oddly long, that is why — rounding it would make `3 tsp == 1 tbsp` false.

Arithmetic is done in `Decimal` and only converted to `float` at the boundary.
That is not fussiness: with floats, `TSP * 3 == TBSP` fails, and a test asserting
the ratios hold would have to be written with a tolerance, which would then hide
a genuine transcription error.
"""

from __future__ import annotations

import enum
from decimal import Decimal


class UnitFamily(enum.StrEnum):
    """What kind of quantity a unit measures.

    Conversion within a family is an exact ratio. Between mass and volume it
    needs a density. Temperature converts to nothing else at all — it is affine,
    so it has an offset and does not scale.
    """

    mass = "mass"
    volume = "volume"
    temperature = "temperature"


class Unit(enum.StrEnum):
    gram = "g"
    kilogram = "kg"
    ounce = "oz"
    pound = "lb"

    millilitre = "ml"
    litre = "l"
    teaspoon = "tsp"
    tablespoon = "tbsp"
    fluid_ounce = "fl_oz"
    cup = "cup"
    pint = "pint"
    quart = "quart"

    celsius = "c"
    fahrenheit = "f"


class System(enum.StrEnum):
    """Which unit family a baker is shown by default."""

    metric = "metric"
    us = "us"


# --- defined constants ------------------------------------------------------

# The avoirdupois pound is defined as exactly 0.45359237 kg; the ounce is 1/16
# of it. Both are exact, not approximations.
GRAMS_PER_POUND = Decimal("453.59237")
GRAMS_PER_OUNCE = GRAMS_PER_POUND / 16
GRAMS_PER_KILOGRAM = Decimal(1000)

# The US liquid gallon is defined as exactly 231 cubic inches = 3.785411784 L.
# Everything else in US volume is a fraction of it, so deriving rather than
# transcribing keeps the whole ladder internally consistent.
ML_PER_US_GALLON = Decimal("3785.411784")
ML_PER_US_FL_OZ = ML_PER_US_GALLON / 128
ML_PER_US_CUP = ML_PER_US_FL_OZ * 8
ML_PER_US_PINT = ML_PER_US_FL_OZ * 16
ML_PER_US_QUART = ML_PER_US_FL_OZ * 32
ML_PER_US_TBSP = ML_PER_US_FL_OZ / 2
ML_PER_US_TSP = ML_PER_US_FL_OZ / 6
ML_PER_LITRE = Decimal(1000)

# Grams per millilitre, for water. Real water is 0.99821 g/ml at 20 °C, so this
# is 0.18% high — an order of magnitude below what a kitchen scale can resolve,
# and it matches every published ingredient chart. Agreeing with the charts is
# worth more here than being right in the fourth digit.
WATER_GRAMS_PER_ML = Decimal(1)

FAMILY: dict[Unit, UnitFamily] = {
    Unit.gram: UnitFamily.mass,
    Unit.kilogram: UnitFamily.mass,
    Unit.ounce: UnitFamily.mass,
    Unit.pound: UnitFamily.mass,
    Unit.millilitre: UnitFamily.volume,
    Unit.litre: UnitFamily.volume,
    Unit.teaspoon: UnitFamily.volume,
    Unit.tablespoon: UnitFamily.volume,
    Unit.fluid_ounce: UnitFamily.volume,
    Unit.cup: UnitFamily.volume,
    Unit.pint: UnitFamily.volume,
    Unit.quart: UnitFamily.volume,
    Unit.celsius: UnitFamily.temperature,
    Unit.fahrenheit: UnitFamily.temperature,
}

#: One of this unit, in grams. Mass only.
GRAMS_PER: dict[Unit, Decimal] = {
    Unit.gram: Decimal(1),
    Unit.kilogram: GRAMS_PER_KILOGRAM,
    Unit.ounce: GRAMS_PER_OUNCE,
    Unit.pound: GRAMS_PER_POUND,
}

#: One of this unit, in millilitres. Volume only.
ML_PER: dict[Unit, Decimal] = {
    Unit.millilitre: Decimal(1),
    Unit.litre: ML_PER_LITRE,
    Unit.teaspoon: ML_PER_US_TSP,
    Unit.tablespoon: ML_PER_US_TBSP,
    Unit.fluid_ounce: ML_PER_US_FL_OZ,
    Unit.cup: ML_PER_US_CUP,
    Unit.pint: ML_PER_US_PINT,
    Unit.quart: ML_PER_US_QUART,
}

#: Human-readable, singular and plural. Used by the formatter, not by clients.
LABELS: dict[Unit, tuple[str, str]] = {
    Unit.gram: ("g", "g"),
    Unit.kilogram: ("kg", "kg"),
    Unit.ounce: ("oz", "oz"),
    Unit.pound: ("lb", "lb"),
    Unit.millilitre: ("ml", "ml"),
    Unit.litre: ("l", "l"),
    Unit.teaspoon: ("tsp", "tsp"),
    Unit.tablespoon: ("tbsp", "tbsp"),
    Unit.fluid_ounce: ("fl oz", "fl oz"),
    Unit.cup: ("cup", "cups"),
    Unit.pint: ("pint", "pints"),
    Unit.quart: ("quart", "quarts"),
    Unit.celsius: ("°C", "°C"),
    Unit.fahrenheit: ("°F", "°F"),
}

MASS_UNITS = frozenset(GRAMS_PER)
VOLUME_UNITS = frozenset(ML_PER)
TEMPERATURE_UNITS = frozenset({Unit.celsius, Unit.fahrenheit})


def family(unit: Unit) -> UnitFamily:
    return FAMILY[unit]
