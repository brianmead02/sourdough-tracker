"""Conversion between units, and the honesty that has to travel with it.

Grams are the only thing this service stores. Everything here exists so a baker
can type "1 cup" or read "3¾ cups" without any of it reaching the fermentation
model, which reasons about mass ratios and would be quietly wrong given a volume.

The design rule: **a conversion returns how it was arrived at, not just a
number.** Mass to mass is definitional. Volume to mass is a per-ingredient
density that can be 20% out. Rendering the second as though it were the first is
the failure this module is built to prevent, so `basis` and `approximate` are
part of every result rather than something a caller reconstructs.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal

from app.services.measurements.units import (
    GRAMS_PER,
    ML_PER,
    ML_PER_US_CUP,
    TEMPERATURE_UNITS,
    Unit,
    UnitFamily,
    family,
)


class Basis(enum.StrEnum):
    """How much a converted number can be trusted."""

    exact = "exact"
    """Definitional: mass↔mass, volume↔volume, temperature."""

    user_override = "user_override"
    """The baker weighed their own flour. The best number available."""

    catalogue = "catalogue"
    """Matched a named catalogue entry. Good to roughly ±5%."""

    kind_default = "kind_default"
    """Fell back to a representative density for the ingredient kind. ±20%."""


APPROXIMATE_BASES = frozenset({Basis.catalogue, Basis.kind_default, Basis.user_override})

#: Below this, volume measurement stops being meaningful: 10 g of fine salt is
#: 1.667 tsp and no spoon set has a third of a teaspoon.
WEIGH_BELOW_GRAMS = 15.0


class MeasurementError(Exception):
    """Base for every refusal in this module."""


class DensityRequiredError(MeasurementError):
    """Volume↔mass was attempted without a density."""


class VolumeNotAllowedError(MeasurementError):
    """This ingredient may not be measured by volume at all.

    Raised for salt without a named variety (6.0 g/tsp fine vs 2.85 g/tsp
    Diamond Crystal — a 2.1-fold spread) and for starter, whose volume depends on
    how aerated it is rather than how much of it there is.
    """


class IncompatibleUnitsError(MeasurementError):
    """Temperature does not convert to mass or volume."""


@dataclass(frozen=True, slots=True)
class Density:
    """Everything needed to move one ingredient between mass and volume."""

    slug: str
    grams_per_cup: float
    basis: Basis
    volume_allowed: bool = True
    reason: str | None = None
    """Why volume is refused, shown to the baker rather than swallowed."""

    @property
    def grams_per_ml(self) -> float:
        return self.grams_per_cup / float(ML_PER_US_CUP)


@dataclass(frozen=True, slots=True)
class Conversion:
    value: float
    unit: Unit
    basis: Basis
    approximate: bool
    source_slug: str | None = None

    @property
    def advise_weighing(self) -> bool:
        """True when the quantity is too small for a spoon to express honestly."""
        if not self.approximate:
            return False
        return self.unit in ML_PER and _is_small(self)


def _is_small(conversion: Conversion) -> bool:
    # Only meaningful once expressed in grams; the caller knows the mass, so this
    # is a conservative check on the volume side.
    return conversion.value <= 3.0 and conversion.unit is Unit.teaspoon


def _guard_density(unit: Unit, density: Density | None) -> Density:
    if density is None:
        raise DensityRequiredError(
            f"converting {unit.value} to or from grams needs a density for the ingredient"
        )
    if not density.volume_allowed:
        raise VolumeNotAllowedError(
            density.reason or f"{density.slug} cannot be measured by volume"
        )
    return density


def to_grams(value: float, unit: Unit, density: Density | None = None) -> Conversion:
    """Convert any mass or volume quantity into grams."""
    if unit in TEMPERATURE_UNITS:
        raise IncompatibleUnitsError("temperature has no mass; use convert_temperature")

    amount = Decimal(str(value))

    if unit in GRAMS_PER:
        return Conversion(
            value=float(amount * GRAMS_PER[unit]),
            unit=Unit.gram,
            basis=Basis.exact,
            approximate=False,
        )

    resolved = _guard_density(unit, density)
    millilitres = amount * ML_PER[unit]
    grams = millilitres * Decimal(str(resolved.grams_per_ml))
    return Conversion(
        value=float(grams),
        unit=Unit.gram,
        basis=resolved.basis,
        approximate=True,
        source_slug=resolved.slug,
    )


def from_grams(grams: float, unit: Unit, density: Density | None = None) -> Conversion:
    """Express a gram quantity in some other unit."""
    if unit in TEMPERATURE_UNITS:
        raise IncompatibleUnitsError("grams do not convert to a temperature")

    amount = Decimal(str(grams))

    if unit in GRAMS_PER:
        return Conversion(
            value=float(amount / GRAMS_PER[unit]),
            unit=unit,
            basis=Basis.exact,
            approximate=False,
        )

    resolved = _guard_density(unit, density)
    millilitres = amount / Decimal(str(resolved.grams_per_ml))
    return Conversion(
        value=float(millilitres / ML_PER[unit]),
        unit=unit,
        basis=resolved.basis,
        approximate=True,
        source_slug=resolved.slug,
    )


def convert(value: float, frm: Unit, to: Unit, density: Density | None = None) -> Conversion:
    """Convert between any two compatible units.

    Same family is an exact ratio and needs no density. Crossing between mass and
    volume does. Temperature converts only to temperature.
    """
    frm_family, to_family = family(frm), family(to)

    if (frm_family is UnitFamily.temperature) != (to_family is UnitFamily.temperature):
        raise IncompatibleUnitsError(f"cannot convert {frm.value} to {to.value}")

    if frm_family is UnitFamily.temperature:
        return Conversion(
            value=convert_temperature(value, frm, to),
            unit=to,
            basis=Basis.exact,
            approximate=False,
        )

    if frm_family is to_family:
        table = GRAMS_PER if frm_family is UnitFamily.mass else ML_PER
        ratio = Decimal(str(value)) * table[frm] / table[to]
        return Conversion(value=float(ratio), unit=to, basis=Basis.exact, approximate=False)

    # Crossing families: go through grams, which is the only thing stored.
    as_grams = to_grams(value, frm, density)
    result = from_grams(as_grams.value, to, density)
    # The weaker of the two bases wins; both legs used the same density, so this
    # is really just "did a density get involved at all".
    return Conversion(
        value=result.value,
        unit=to,
        basis=as_grams.basis if as_grams.basis is not Basis.exact else result.basis,
        approximate=True,
        source_slug=result.source_slug or as_grams.source_slug,
    )


def convert_temperature(value: float, frm: Unit, to: Unit) -> float:
    """Celsius and Fahrenheit only.

    Kept separate from the ratio path deliberately. Temperature is affine: 20 °C
    is 68 °F, but a *rise* of 20 °C is a rise of 36 °F, not 68. Routing it
    through a ratio table would produce numbers that look plausible and are
    wrong, and the Q10 fermentation model consumes this value.
    """
    if frm not in TEMPERATURE_UNITS or to not in TEMPERATURE_UNITS:
        raise IncompatibleUnitsError("convert_temperature handles °C and °F only")
    if frm is to:
        return value
    if frm is Unit.celsius:
        return value * 9 / 5 + 32
    return (value - 32) * 5 / 9


def c_to_f(celsius: float) -> float:
    return convert_temperature(celsius, Unit.celsius, Unit.fahrenheit)


def f_to_c(fahrenheit: float) -> float:
    return convert_temperature(fahrenheit, Unit.fahrenheit, Unit.celsius)
