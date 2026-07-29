"""The measurable quantities achievements are defined against.

Every metric is a single aggregate over the user's own data, so an achievement
is always recomputable from first principles rather than depending on a counter
that was incremented at the right moment.
"""

import enum
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from app.models.bake import Bake, BakePhoto, BakeRating, BakeStatus
from app.models.gamification import UserAchievement
from app.models.inventory import InventoryTransaction, TransactionKind
from app.models.proofing import ProofSession, ProofStatus
from app.models.recipe import Recipe
from app.models.starter import Feeding, Starter, StarterObservation
from app.services.starters import compute_streak


class Metric(enum.StrEnum):
    bakes_completed = "bakes_completed"
    feedings_logged = "feedings_logged"
    proofs_completed = "proofs_completed"
    observations_logged = "observations_logged"
    starters_kept = "starters_kept"
    recipes_created = "recipes_created"
    recipes_published = "recipes_published"
    forks_received = "forks_received"
    stars_received = "stars_received"
    photos_uploaded = "photos_uploaded"
    perfect_bakes = "perfect_bakes"
    longest_feed_streak = "longest_feed_streak"
    distinct_flours = "distinct_flours"
    max_hydration_success = "max_hydration_success"
    longest_retard_hours = "longest_retard_hours"
    night_bakes = "night_bakes"
    flour_purchased_kg = "flour_purchased_kg"
    achievements_earned = "achievements_earned"
    loaves_baked = "loaves_baked"


async def _scalar(db: AsyncSession, statement: Executable) -> float:
    result = await db.execute(statement)
    return float(result.scalar_one() or 0)


async def _bakes_completed(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count()).where(
            Bake.user_id == user_id,
            Bake.deleted_at.is_(None),
            Bake.status == BakeStatus.done,
        ),
    )


async def _loaves_baked(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.sum(Bake.loaf_count), 0)).where(
            Bake.user_id == user_id,
            Bake.deleted_at.is_(None),
            Bake.status == BakeStatus.done,
        ),
    )


async def _feedings_logged(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count())
        .select_from(Feeding)
        .join(Starter, Starter.id == Feeding.starter_id)
        .where(Starter.user_id == user_id),
    )


async def _proofs_completed(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count()).where(
            ProofSession.user_id == user_id, ProofSession.status == ProofStatus.done
        ),
    )


async def _observations_logged(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count())
        .select_from(StarterObservation)
        .join(Starter, Starter.id == StarterObservation.starter_id)
        .where(Starter.user_id == user_id),
    )


async def _starters_kept(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count()).where(Starter.user_id == user_id, Starter.deleted_at.is_(None)),
    )


async def _recipes_created(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count()).where(Recipe.owner_id == user_id, Recipe.deleted_at.is_(None)),
    )


async def _recipes_published(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count()).where(
            Recipe.owner_id == user_id,
            Recipe.deleted_at.is_(None),
            Recipe.is_public.is_(True),
        ),
    )


async def _forks_received(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.sum(Recipe.fork_count), 0)).where(
            Recipe.owner_id == user_id, Recipe.deleted_at.is_(None)
        ),
    )


async def _stars_received(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.coalesce(func.sum(Recipe.star_count), 0)).where(
            Recipe.owner_id == user_id, Recipe.deleted_at.is_(None)
        ),
    )


async def _photos_uploaded(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count())
        .select_from(BakePhoto)
        .join(Bake, Bake.id == BakePhoto.bake_id)
        .where(Bake.user_id == user_id, Bake.deleted_at.is_(None)),
    )


async def _perfect_bakes(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(func.count())
        .select_from(BakeRating)
        .join(Bake, Bake.id == BakeRating.bake_id)
        .where(Bake.user_id == user_id, Bake.deleted_at.is_(None), BakeRating.overall == 5),
    )


async def _longest_feed_streak(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Best streak across all of the user's starters, computed from feedings."""
    starters = await db.execute(
        select(Starter.id, Starter.feed_interval_hours).where(
            Starter.user_id == user_id, Starter.deleted_at.is_(None)
        )
    )
    best = 0
    for starter_id, interval in starters.all():
        times = await db.execute(
            select(Feeding.fed_at).where(Feeding.starter_id == starter_id).order_by(Feeding.fed_at)
        )
        stats = compute_streak(list(times.scalars().all()), interval, datetime.now(UTC))
        best = max(best, stats.longest)
    return float(best)


async def _distinct_flours(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Distinct flours named across the user's bake blends."""
    rows = await db.execute(
        select(Bake.flour_blend).where(
            Bake.user_id == user_id,
            Bake.deleted_at.is_(None),
            Bake.flour_blend.is_not(None),
        )
    )
    seen: set[str] = set()
    for (blend,) in rows.all():
        if blend:
            seen.update(name.strip().lower() for name in blend)
    return float(len(seen))


async def _max_hydration_success(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Highest hydration that produced a bake rated 4 or better.

    Hydration alone would reward typing a big number; pairing it with the rating
    means the loaf has to have actually worked.
    """
    return await _scalar(
        db,
        select(func.coalesce(func.max(Bake.hydration_pct), 0.0))
        .select_from(Bake)
        .join(BakeRating, BakeRating.bake_id == Bake.id)
        .where(
            Bake.user_id == user_id,
            Bake.deleted_at.is_(None),
            Bake.hydration_pct.is_not(None),
            BakeRating.overall >= 4,
        ),
    )


async def _longest_retard_hours(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(
        db,
        select(
            func.coalesce(
                func.max(
                    cast(
                        func.extract("epoch", ProofSession.actual_end_at - ProofSession.started_at),
                        Float,
                    )
                    / 3600.0
                ),
                0.0,
            )
        ).where(
            ProofSession.user_id == user_id,
            ProofSession.stage == "retard",
            ProofSession.status == ProofStatus.done,
            ProofSession.actual_end_at.is_not(None),
        ),
    )


async def _night_bakes(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Bakes finished between midnight and 5am UTC."""
    hour = func.extract("hour", Bake.finished_at)
    return await _scalar(
        db,
        select(func.count()).where(
            Bake.user_id == user_id,
            Bake.deleted_at.is_(None),
            Bake.finished_at.is_not(None),
            and_(hour >= 0, hour < 5),
        ),
    )


async def _flour_purchased_kg(db: AsyncSession, user_id: uuid.UUID) -> float:
    from app.models.inventory import InventoryItem

    return await _scalar(
        db,
        select(func.coalesce(func.sum(InventoryTransaction.delta_g), 0.0) / 1000.0)
        .select_from(InventoryTransaction)
        .join(InventoryItem, InventoryItem.id == InventoryTransaction.item_id)
        .where(
            InventoryItem.user_id == user_id,
            InventoryTransaction.kind == TransactionKind.purchase,
        ),
    )


async def _achievements_earned(db: AsyncSession, user_id: uuid.UUID) -> float:
    return await _scalar(db, select(func.count()).where(UserAchievement.user_id == user_id))


METRIC_FUNCTIONS: dict[Metric, Callable[[AsyncSession, uuid.UUID], Awaitable[float]]] = {
    Metric.bakes_completed: _bakes_completed,
    Metric.loaves_baked: _loaves_baked,
    Metric.feedings_logged: _feedings_logged,
    Metric.proofs_completed: _proofs_completed,
    Metric.observations_logged: _observations_logged,
    Metric.starters_kept: _starters_kept,
    Metric.recipes_created: _recipes_created,
    Metric.recipes_published: _recipes_published,
    Metric.forks_received: _forks_received,
    Metric.stars_received: _stars_received,
    Metric.photos_uploaded: _photos_uploaded,
    Metric.perfect_bakes: _perfect_bakes,
    Metric.longest_feed_streak: _longest_feed_streak,
    Metric.distinct_flours: _distinct_flours,
    Metric.max_hydration_success: _max_hydration_success,
    Metric.longest_retard_hours: _longest_retard_hours,
    Metric.night_bakes: _night_bakes,
    Metric.flour_purchased_kg: _flour_purchased_kg,
    Metric.achievements_earned: _achievements_earned,
}


async def measure(db: AsyncSession, metric: Metric, user_id: uuid.UUID) -> float:
    return await METRIC_FUNCTIONS[metric](db, user_id)
