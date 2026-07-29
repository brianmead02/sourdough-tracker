"""Rebuilding the XP ledger from the underlying data.

This is what the append-only, source-keyed ledger is *for*. A rule can be
rebalanced, or a new achievement added, and history is re-derived rather than
patched — including for data that predates the rule entirely.

Events are replayed in chronological order and pass through the same `award()`
as live play, so the daily caps apply exactly as they did at the time. A replay
that ignored caps would quietly pay more than playing normally ever could.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bake import Bake, BakePhoto, BakeRating, BakeStatus
from app.models.gamification import LeaderboardEntry, UserAchievement, XPEvent
from app.models.inventory import InventoryItem, InventoryTransaction, TransactionKind
from app.models.proofing import ProofSession, ProofStatus
from app.models.recipe import Recipe, RecipeStar
from app.models.starter import Feeding, Starter, StarterObservation
from app.models.user import User
from app.services import xp as xp_service
from app.services.achievements import ACHIEVEMENTS, evaluate
from app.services.events import BASE_XP, DAILY_CAPS, DomainEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplayResult:
    users: int = 0
    events: int = 0
    xp: int = 0
    achievements: int = 0


async def _timeline(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[datetime, DomainEvent, str, uuid.UUID]]:
    """Everything the user has ever done that pays, oldest first."""
    entries: list[tuple[datetime, DomainEvent, str, uuid.UUID]] = []

    starters = await db.execute(
        select(Starter.id, Starter.created_at).where(Starter.user_id == user_id)
    )
    for starter_id, created in starters.all():
        entries.append((created, DomainEvent.starter_created, "starter", starter_id))

    feedings = await db.execute(
        select(Feeding.id, Feeding.fed_at)
        .join(Starter, Starter.id == Feeding.starter_id)
        .where(Starter.user_id == user_id)
    )
    for feeding_id, fed_at in feedings.all():
        entries.append((fed_at, DomainEvent.feeding_logged, "feeding", feeding_id))

    observations = await db.execute(
        select(StarterObservation.id, StarterObservation.observed_at)
        .join(Starter, Starter.id == StarterObservation.starter_id)
        .where(Starter.user_id == user_id)
    )
    for observation_id, observed_at in observations.all():
        entries.append((observed_at, DomainEvent.observation_logged, "observation", observation_id))

    proofs = await db.execute(
        select(ProofSession.id, ProofSession.actual_end_at).where(
            ProofSession.user_id == user_id,
            ProofSession.status == ProofStatus.done,
            ProofSession.actual_end_at.is_not(None),
        )
    )
    for proof_id, ended in proofs.all():
        entries.append((ended, DomainEvent.proof_completed, "proof_session", proof_id))

    bakes = await db.execute(
        select(Bake.id, Bake.finished_at, Bake.started_at).where(
            Bake.user_id == user_id, Bake.status == BakeStatus.done
        )
    )
    for bake_id, finished, started in bakes.all():
        entries.append((finished or started, DomainEvent.bake_completed, "bake", bake_id))

    ratings = await db.execute(
        select(BakeRating.bake_id, BakeRating.created_at)
        .join(Bake, Bake.id == BakeRating.bake_id)
        .where(Bake.user_id == user_id)
    )
    for bake_id, created in ratings.all():
        entries.append((created, DomainEvent.bake_rated, "bake", bake_id))

    photos = await db.execute(
        select(BakePhoto.id, BakePhoto.created_at)
        .join(Bake, Bake.id == BakePhoto.bake_id)
        .where(Bake.user_id == user_id)
    )
    for photo_id, created in photos.all():
        entries.append((created, DomainEvent.photo_added, "photo", photo_id))

    recipes = await db.execute(
        select(Recipe.id, Recipe.created_at, Recipe.is_public).where(Recipe.owner_id == user_id)
    )
    for recipe_id, created, is_public in recipes.all():
        entries.append((created, DomainEvent.recipe_created, "recipe", recipe_id))
        if is_public:
            entries.append((created, DomainEvent.recipe_published, "recipe", recipe_id))

    # Credit for other people's forks of, and stars on, this user's recipes.
    owned = await db.execute(select(Recipe.id).where(Recipe.owner_id == user_id))
    owned_ids = [row[0] for row in owned.all()]
    if owned_ids:
        fork_rows = await db.execute(
            select(Recipe.id, Recipe.created_at, Recipe.owner_id).where(
                Recipe.forked_from_id.in_(owned_ids)
            )
        )
        for fork_id, created, forker_id in fork_rows.all():
            if forker_id != user_id:
                entries.append((created, DomainEvent.recipe_forked, "fork", fork_id))

        star_rows = await db.execute(
            select(RecipeStar.user_id, RecipeStar.recipe_id, RecipeStar.created_at).where(
                RecipeStar.recipe_id.in_(owned_ids)
            )
        )
        for star_user, recipe_id, created in star_rows.all():
            entries.append(
                (
                    created,
                    DomainEvent.recipe_starred,
                    "star",
                    xp_service.source_id_for(f"star:{star_user}:{recipe_id}"),
                )
            )

    purchases = await db.execute(
        select(InventoryTransaction.id, InventoryTransaction.occurred_at)
        .join(InventoryItem, InventoryItem.id == InventoryTransaction.item_id)
        .where(
            InventoryItem.user_id == user_id,
            InventoryTransaction.kind == TransactionKind.purchase,
        )
    )
    for transaction_id, occurred in purchases.all():
        entries.append(
            (occurred, DomainEvent.inventory_purchased, "inventory_transaction", transaction_id)
        )

    return sorted(entries, key=lambda e: e[0])


async def replay_user(db: AsyncSession, user_id: uuid.UUID) -> ReplayResult:
    """Rebuild one user's ledger. Assumes their existing events were cleared."""
    result = ReplayResult(users=1)

    for occurred_at, event, source_type, source_id in await _timeline(db, user_id):
        result.xp += await xp_service.award(
            db,
            user_id=user_id,
            rule_code=f"xp.{event.value}",
            source_type=source_type,
            source_id=source_id,
            amount=BASE_XP.get(event, 0),
            daily_cap=DAILY_CAPS.get(event),
            at=occurred_at,
        )
        result.events += 1

    # Achievements are evaluated once at the end against final metrics: their
    # thresholds are cumulative, so replaying them per-event would award the
    # same badges in the same order for more work.
    awards = await evaluate(db, user_id, ACHIEVEMENTS)
    result.achievements = len(awards)
    result.xp += sum(a.xp_award for a in awards)
    return result


async def replay_all(db: AsyncSession) -> ReplayResult:
    """Rebuild the whole ledger. Destructive and idempotent."""
    await db.execute(delete(XPEvent))
    await db.execute(delete(UserAchievement))
    await db.execute(delete(LeaderboardEntry))

    users = await db.execute(select(User.id).where(User.deleted_at.is_(None)))
    total = ReplayResult()
    for (user_id,) in users.all():
        one = await replay_user(db, user_id)
        total.users += one.users
        total.events += one.events
        total.xp += one.xp
        total.achievements += one.achievements

    logger.info(
        "replayed %d users, %d events, %d xp, %d achievements",
        total.users,
        total.events,
        total.xp,
        total.achievements,
    )
    return total
