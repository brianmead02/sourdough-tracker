"""Units, densities and the conversions between them.

Grams are the only mass this service stores, and Celsius the only temperature.
Everything here exists so a baker can work in cups, ounces or Fahrenheit without
any of it reaching the fermentation model, which reasons about mass ratios.

The organising idea is that **a conversion carries how much it can be trusted**.
Mass to mass is definitional; volume to mass is a per-ingredient density that can
be 20% out; salt and starter refuse volume altogether. See `Basis`.
"""

from app.services.measurements.catalogue import (
    BY_ALIAS,
    BY_SLUG,
    CATALOGUE,
    KIND_DEFAULTS,
    IngredientMeasure,
    Method,
)
from app.services.measurements.convert import (
    WEIGH_BELOW_GRAMS,
    Basis,
    Conversion,
    Density,
    DensityRequiredError,
    IncompatibleUnitsError,
    MeasurementError,
    VolumeNotAllowedError,
    c_to_f,
    convert,
    convert_temperature,
    f_to_c,
    from_grams,
    to_grams,
)
from app.services.measurements.format import Measurement, Term, cups_from_grams, describe
from app.services.measurements.resolve import normalise, resolve
from app.services.measurements.units import System, Unit, UnitFamily, family

__all__ = [
    "BY_ALIAS",
    "BY_SLUG",
    "CATALOGUE",
    "KIND_DEFAULTS",
    "WEIGH_BELOW_GRAMS",
    "Basis",
    "Conversion",
    "Density",
    "DensityRequiredError",
    "IncompatibleUnitsError",
    "IngredientMeasure",
    "Measurement",
    "MeasurementError",
    "Method",
    "System",
    "Term",
    "Unit",
    "UnitFamily",
    "VolumeNotAllowedError",
    "c_to_f",
    "convert",
    "convert_temperature",
    "cups_from_grams",
    "describe",
    "f_to_c",
    "family",
    "from_grams",
    "normalise",
    "resolve",
    "to_grams",
]
