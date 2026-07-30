"""Loading densities from the database and merging a baker's own measurements.

The conversion and formatting modules are pure and take densities as plain
values. This is the seam where those values come from Postgres: catalogue rows
plus whatever the caller has overridden.

`load_overrides` is the one that matters for correctness. Every read path that
renders a quantity needs it, and it must be a *single* query — resolving forty
recipe ingredients one lookup at a time would be forty round-trips per response.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import IngredientMeasureRow, UserIngredientMeasure
from app.models.recipe import IngredientKind
from app.services.measurements.convert import Density
from app.services.measurements.resolve import resolve


async def load_overrides(session: AsyncSession, user_id: uuid.UUID) -> dict[str, float]:
    """Every density this baker has replaced, as {slug: grams_per_cup}.

    One query, loaded once per request and passed down. Most bakers have none, so
    this is usually an empty dict and costs a single indexed scan.
    """
    rows = await session.execute(
        select(UserIngredientMeasure.slug, UserIngredientMeasure.grams_per_cup).where(
            UserIngredientMeasure.user_id == user_id
        )
    )
    return dict(rows.all())  # type: ignore[arg-type]


async def list_catalogue(
    session: AsyncSession, kind: IngredientKind | None = None
) -> Sequence[IngredientMeasureRow]:
    statement = select(IngredientMeasureRow).order_by(
        IngredientMeasureRow.kind, IngredientMeasureRow.name
    )
    if kind is not None:
        statement = statement.where(IngredientMeasureRow.kind == kind.value)
    return (await session.execute(statement)).scalars().all()


async def get_entry(session: AsyncSession, slug: str) -> IngredientMeasureRow | None:
    return await session.get(IngredientMeasureRow, slug)


async def set_override(
    session: AsyncSession,
    user_id: uuid.UUID,
    slug: str,
    grams_per_cup: float,
    note: str | None = None,
) -> UserIngredientMeasure:
    """Upsert, so setting the same density twice is not an error."""
    statement = (
        insert(UserIngredientMeasure)
        .values(user_id=user_id, slug=slug, grams_per_cup=grams_per_cup, note=note)
        .on_conflict_do_update(
            constraint="uq_user_ingredient_measure",
            set_={"grams_per_cup": grams_per_cup, "note": note},
        )
        .returning(UserIngredientMeasure)
    )
    result = await session.execute(statement)
    await session.flush()
    return result.scalar_one()


async def clear_override(session: AsyncSession, user_id: uuid.UUID, slug: str) -> bool:
    """Returns whether anything was removed, so the route can 404 honestly."""
    result = await session.execute(
        delete(UserIngredientMeasure).where(
            UserIngredientMeasure.user_id == user_id,
            UserIngredientMeasure.slug == slug,
        )
    )
    await session.flush()
    # DELETE returns a CursorResult, which does carry rowcount; the async
    # execute() signature is declared as the narrower Result.
    return bool(cast("CursorResult[Any]", result).rowcount)


def density_for(
    name: str,
    kind: IngredientKind | None = None,
    overrides: Mapping[str, float] | None = None,
) -> Density | None:
    """Thin pass-through, so callers need only import from one place."""
    return resolve(name, kind, overrides)
