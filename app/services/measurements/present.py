"""Building `display` payloads for API responses.

One place, so every read path renders a quantity the same way and carries the
same honesty fields. Routes pass the ingredient name and kind; this resolves the
density, formats, and hands back something serialisable — or `None` when there is
nothing sensible to say.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.models.recipe import IngredientKind
from app.schemas.measurement import MeasureDisplay
from app.services.measurements.convert import Density
from app.services.measurements.format import describe
from app.services.measurements.resolve import resolve
from app.services.measurements.units import System


def display_for(
    grams: float,
    system: System,
    *,
    ingredient: str | None = None,
    kind: IngredientKind | None = None,
    overrides: Mapping[str, float] | None = None,
) -> MeasureDisplay:
    """Render one gram figure for the caller's preferred system.

    Never raises. A refused ingredient (salt, starter) or an unmatched name falls
    back to exact mass, which needs no density — a precise answer beats an error
    the client has to special-case on a read path.
    """
    density: Density | None = None
    if ingredient is not None:
        density = resolve(ingredient, kind, overrides)

    measurement = describe(grams, density, system)
    return MeasureDisplay(
        text=measurement.text,
        system=system,
        basis=measurement.basis,
        approximate=measurement.approximate,
        grams=measurement.grams,
        drift_pct=round(measurement.drift_pct, 2),
        advise_weighing=measurement.advise_weighing,
    )
