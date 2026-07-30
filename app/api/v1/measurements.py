"""Units, ingredient densities, and conversion.

Grams are the only mass this service stores. These endpoints exist so a client
can offer cups, ounces, millilitres or Fahrenheit without any of it reaching the
fermentation model.

The one thing to preserve when editing: **a refusal is a result, not an error.**
Salt without a named variety and starter of any kind cannot be converted by
volume honestly, and a batch containing one of those still returns 200 with a
per-item `error`. Failing the whole request would push clients towards sending
one item at a time, which is the shape this endpoint exists to avoid.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.recipe import IngredientKind
from app.schemas.measurement import (
    ConversionResult,
    ConvertRequest,
    ConvertResponse,
    IngredientMeasureResponse,
    OverrideRequest,
    UnitCatalogueResponse,
    UnitInfo,
)
from app.services.measurements import (
    Density,
    MeasurementError,
    Unit,
    UnitFamily,
    convert,
    family,
    resolve,
)
from app.services.measurements import store as measure_store
from app.services.measurements.units import GRAMS_PER, LABELS, ML_PER

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix="/measurements", tags=["measurements"])

VOLUME_NOTE = (
    "Volume units have no gram figure because they do not have one: a cup of "
    "water is 237 g and a cup of cocoa is 84 g. Convert through an ingredient."
)


@router.get("/units", response_model=UnitCatalogueResponse)
async def list_units() -> UnitCatalogueResponse:
    """Every unit and its exact ratio. Static — cache it freely."""
    units = [
        UnitInfo(
            unit=unit,
            label=LABELS[unit][1],
            family=family(unit),
            grams=float(GRAMS_PER[unit]) if unit in GRAMS_PER else None,
            millilitres=float(ML_PER[unit]) if unit in ML_PER else None,
        )
        for unit in Unit
    ]
    return UnitCatalogueResponse(units=units, note=VOLUME_NOTE)


@router.get("/ingredients", response_model=list[IngredientMeasureResponse])
async def list_ingredients(
    user: CurrentUser,
    db: SessionDep,
    kind: Annotated[IngredientKind | None, Query()] = None,
) -> list[IngredientMeasureResponse]:
    """The density catalogue with the caller's own measurements merged in."""
    rows = await measure_store.list_catalogue(db, kind)
    overrides = await measure_store.load_overrides(db, user.id)
    return [
        IngredientMeasureResponse(
            slug=row.slug,
            name=row.name,
            kind=IngredientKind(row.kind),
            grams_per_cup=overrides.get(row.slug, row.grams_per_cup),
            method=row.method,
            source=row.source,
            aliases=list(row.aliases),
            volume_allowed=row.volume_allowed,
            reason=row.reason,
            overridden=row.slug in overrides,
        )
        for row in rows
    ]


@router.post("/convert", response_model=ConvertResponse)
async def convert_batch(
    payload: ConvertRequest, user: CurrentUser, db: SessionDep
) -> ConvertResponse:
    """Convert a batch of quantities. Refusals come back per item, not as a 4xx."""
    overrides = await measure_store.load_overrides(db, user.id)

    results: list[ConversionResult] = []
    for item in payload.items:
        density: Density | None = None
        if item.ingredient:
            density = resolve(item.ingredient, item.kind, overrides)

        needs_density = family(item.from_unit) is not family(item.to_unit) and (
            UnitFamily.temperature not in (family(item.from_unit), family(item.to_unit))
        )
        if needs_density and density is None:
            results.append(
                ConversionResult(
                    value=None,
                    unit=item.to_unit,
                    error=(
                        "converting between mass and volume needs an ingredient; "
                        "pass `ingredient` (and `kind` to allow a fallback)"
                    ),
                )
            )
            continue

        try:
            outcome = convert(item.value, item.from_unit, item.to_unit, density)
        except MeasurementError as exc:
            results.append(ConversionResult(value=None, unit=item.to_unit, error=str(exc)))
            continue

        results.append(
            ConversionResult(
                value=outcome.value,
                unit=outcome.unit,
                basis=outcome.basis,
                approximate=outcome.approximate,
                source_slug=outcome.source_slug,
            )
        )

    return ConvertResponse(results=results)


@router.put("/ingredients/{slug}/override", response_model=IngredientMeasureResponse)
async def set_override(
    slug: str, payload: OverrideRequest, user: VerifiedUser, db: SessionDep
) -> IngredientMeasureResponse:
    """Record your own measured density for one ingredient.

    A baker who weighed a cup of their local mill's rye knows better than any
    published chart. This does not override a *refusal*, though: no measurement
    makes a peaked levain's volume meaningful.
    """
    row = await measure_store.get_entry(db, slug)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ingredient")
    if not row.volume_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=row.reason or f"{row.name} cannot be measured by volume",
        )

    await measure_store.set_override(db, user.id, slug, payload.grams_per_cup, payload.note)
    return IngredientMeasureResponse(
        slug=row.slug,
        name=row.name,
        kind=IngredientKind(row.kind),
        grams_per_cup=payload.grams_per_cup,
        method=row.method,
        source=row.source,
        aliases=list(row.aliases),
        volume_allowed=row.volume_allowed,
        reason=row.reason,
        overridden=True,
    )


@router.delete("/ingredients/{slug}/override", status_code=status.HTTP_204_NO_CONTENT)
async def clear_override(slug: str, user: VerifiedUser, db: SessionDep) -> None:
    """Fall back to the published density again."""
    if not await measure_store.clear_override(db, user.id, slug):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No override set")
