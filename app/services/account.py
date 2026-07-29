"""Account data export and erasure.

Both exist because a public service holding personal data owes its users a copy
of it and a way out. Neither is a nice-to-have that can be bolted on later: the
export has to know about every table, and erasure has to know which foreign keys
cascade and which would orphan someone *else's* data.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bake import Bake, BakePhoto, BakeRating
from app.models.gamification import LeaderboardEntry, UserAchievement, XPEvent
from app.models.inventory import InventoryItem, InventoryTransaction
from app.models.notification import (
    InAppNotification,
    NotificationChannel,
    NotificationLog,
    NotificationSettings,
    ScheduledNotification,
)
from app.models.proofing import ProofCheck, ProofSession
from app.models.recipe import Recipe, RecipeIngredient, RecipeStar
from app.models.starter import Feeding, Starter, StarterObservation
from app.models.user import EmailVerification, PasswordReset, RefreshToken, User, UserProfile
from app.services import storage

logger = logging.getLogger(__name__)

# Fields that must never appear in an export: they are credentials, not data
# about the person. Handing back a password hash or a live refresh token would
# turn a convenience feature into a way to leak secrets.
REDACTED = {"password_hash", "token_hash", "target_hash"}


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Serialise an ORM row, dropping credentials and normalising timestamps."""
    out: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in REDACTED:
            continue
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, uuid.UUID):
            value = str(value)
        out[column.name] = value
    return out


async def _all(session: AsyncSession, statement: Any) -> list[dict[str, Any]]:
    result = await session.execute(statement)
    return [_row_to_dict(row) for row in result.scalars().all()]


async def export_account(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything held about one account, as plain JSON.

    Generated synchronously. A home baker's history is a few hundred rows; if
    that stops being true this becomes a worker job writing to object storage,
    and the shape of the document does not have to change.
    """
    starter_ids = select(Starter.id).where(Starter.user_id == user.id)
    bake_ids = select(Bake.id).where(Bake.user_id == user.id)
    item_ids = select(InventoryItem.id).where(InventoryItem.user_id == user.id)
    proof_ids = select(ProofSession.id).where(ProofSession.user_id == user.id)

    photos = await _all(session, select(BakePhoto).where(BakePhoto.bake_id.in_(bake_ids)))
    for photo in photos:
        # A URL rather than bytes: the export stays small, and the link works
        # for as long as a download reasonably takes.
        photo["download_url"] = storage.presign_download(str(photo["object_key"]))

    settings_row = await session.get(NotificationSettings, user.id)
    profile = await session.get(UserProfile, user.id)

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": _row_to_dict(user),
        "profile": _row_to_dict(profile) if profile else {},
        "starters": await _all(session, select(Starter).where(Starter.user_id == user.id)),
        "feedings": await _all(session, select(Feeding).where(Feeding.starter_id.in_(starter_ids))),
        "observations": await _all(
            session,
            select(StarterObservation).where(StarterObservation.starter_id.in_(starter_ids)),
        ),
        "proof_sessions": await _all(
            session, select(ProofSession).where(ProofSession.user_id == user.id)
        ),
        "proof_checks": await _all(
            session, select(ProofCheck).where(ProofCheck.session_id.in_(proof_ids))
        ),
        "recipes": [
            {
                **recipe,
                "ingredients": await _all(
                    session,
                    select(RecipeIngredient).where(
                        RecipeIngredient.recipe_id == uuid.UUID(recipe["id"])
                    ),
                ),
            }
            for recipe in await _all(session, select(Recipe).where(Recipe.owner_id == user.id))
        ],
        "bakes": await _all(session, select(Bake).where(Bake.user_id == user.id)),
        "ratings": await _all(session, select(BakeRating).where(BakeRating.bake_id.in_(bake_ids))),
        "photos": photos,
        "inventory_items": await _all(
            session, select(InventoryItem).where(InventoryItem.user_id == user.id)
        ),
        "inventory_transactions": await _all(
            session, select(InventoryTransaction).where(InventoryTransaction.item_id.in_(item_ids))
        ),
        "achievements": await _all(
            session, select(UserAchievement).where(UserAchievement.user_id == user.id)
        ),
        "xp_events": await _all(session, select(XPEvent).where(XPEvent.user_id == user.id)),
        "notification_settings": _row_to_dict(settings_row) if settings_row else None,
        "notification_channels": await _all(
            session, select(NotificationChannel).where(NotificationChannel.user_id == user.id)
        ),
        "inbox": await _all(
            session, select(InAppNotification).where(InAppNotification.user_id == user.id)
        ),
    }


async def delete_account(session: AsyncSession, user: User) -> tuple[dict[str, int], int]:
    """Erase an account for real. Returns (rows removed per table, photos removed).

    This is a hard delete, not the soft delete used elsewhere: soft deletion
    exists to stop people farming XP by recreating content, which is not a
    reason to keep someone's data after they have asked for it to go.

    Two things deliberately survive, because they are not this user's to erase:

    * **Forks other people made** of their recipes. `forked_from_id` is nulled,
      so the copy stays whole and merely loses its parent link.
    * **Stars this user gave** are removed, but the counter on the other
      person's recipe is decremented rather than left overstated.
    """
    user_id = user.id
    removed: dict[str, int] = {}

    async def run(label: str, statement: Any) -> None:
        result = cast(CursorResult[Any], await session.execute(statement))
        if result.rowcount:
            removed[label] = result.rowcount

    # Photos first: the objects live outside the database and nothing else will
    # ever reference them again.
    bake_ids = select(Bake.id).where(Bake.user_id == user_id)
    keys = await session.execute(
        select(BakePhoto.object_key).where(BakePhoto.bake_id.in_(bake_ids))
    )
    object_keys = [key for (key,) in keys.all()]
    for key in object_keys:
        try:
            await storage.delete(key)
        except Exception:  # noqa: BLE001 - a stranded object must not block erasure
            logger.warning("could not delete object %s during account erasure", key)

    # Other people's forks keep working; they just lose the parent link.
    await run(
        "forks_orphaned",
        update(Recipe)
        .where(Recipe.forked_from_id.in_(select(Recipe.id).where(Recipe.owner_id == user_id)))
        .values(forked_from_id=None),
    )

    # Stars this user gave: withdraw them and correct the owners' counters.
    starred = await session.execute(
        select(RecipeStar.recipe_id).where(RecipeStar.user_id == user_id)
    )
    for (recipe_id,) in starred.all():
        await session.execute(
            update(Recipe)
            .where(Recipe.id == recipe_id, Recipe.star_count > 0)
            .values(star_count=Recipe.star_count - 1)
        )
    await run("stars_withdrawn", delete(RecipeStar).where(RecipeStar.user_id == user_id))

    # Everything owned by the account. Most of these would cascade from the user
    # row, but doing it explicitly gives an auditable count of what went.
    starter_ids = select(Starter.id).where(Starter.user_id == user_id)
    item_ids = select(InventoryItem.id).where(InventoryItem.user_id == user_id)
    proof_ids = select(ProofSession.id).where(ProofSession.user_id == user_id)

    await run("proof_checks", delete(ProofCheck).where(ProofCheck.session_id.in_(proof_ids)))
    await run("proof_sessions", delete(ProofSession).where(ProofSession.user_id == user_id))
    await run(
        "observations",
        delete(StarterObservation).where(StarterObservation.starter_id.in_(starter_ids)),
    )
    await run("feedings", delete(Feeding).where(Feeding.starter_id.in_(starter_ids)))
    await run("starters", delete(Starter).where(Starter.user_id == user_id))
    await run("photos", delete(BakePhoto).where(BakePhoto.bake_id.in_(bake_ids)))
    await run("ratings", delete(BakeRating).where(BakeRating.bake_id.in_(bake_ids)))
    await run("bakes", delete(Bake).where(Bake.user_id == user_id))
    await run(
        "recipe_ingredients",
        delete(RecipeIngredient).where(
            RecipeIngredient.recipe_id.in_(select(Recipe.id).where(Recipe.owner_id == user_id))
        ),
    )
    await run("recipes", delete(Recipe).where(Recipe.owner_id == user_id))
    await run(
        "inventory_transactions",
        delete(InventoryTransaction).where(InventoryTransaction.item_id.in_(item_ids)),
    )
    await run("inventory_items", delete(InventoryItem).where(InventoryItem.user_id == user_id))
    await run("xp_events", delete(XPEvent).where(XPEvent.user_id == user_id))
    await run("achievements", delete(UserAchievement).where(UserAchievement.user_id == user_id))
    await run(
        "leaderboard_entries", delete(LeaderboardEntry).where(LeaderboardEntry.user_id == user_id)
    )
    await run(
        "notification_logs", delete(NotificationLog).where(NotificationLog.user_id == user_id)
    )
    await run(
        "scheduled_notifications",
        delete(ScheduledNotification).where(ScheduledNotification.user_id == user_id),
    )
    await run("inbox", delete(InAppNotification).where(InAppNotification.user_id == user_id))
    await run(
        "notification_channels",
        delete(NotificationChannel).where(NotificationChannel.user_id == user_id),
    )
    await run(
        "notification_settings",
        delete(NotificationSettings).where(NotificationSettings.user_id == user_id),
    )
    await run("refresh_tokens", delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await run(
        "email_verifications", delete(EmailVerification).where(EmailVerification.user_id == user_id)
    )
    await run("password_resets", delete(PasswordReset).where(PasswordReset.user_id == user_id))
    await run("profile", delete(UserProfile).where(UserProfile.user_id == user_id))
    await run("account", delete(User).where(User.id == user_id))

    logger.info("erased account %s: %s", user_id, removed)
    return removed, len(object_keys)


async def instance_stats(session: AsyncSession) -> dict[str, int]:
    """A one-screen view of what the instance is holding."""

    async def count(statement: Any) -> int:
        return int((await session.execute(statement)).scalar_one() or 0)

    from app.models.notification import DeliveryStatus

    return {
        "users_total": await count(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        ),
        "users_verified": await count(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.email_verified_at.is_not(None))
        ),
        "users_suspended": await count(
            select(func.count()).select_from(User).where(User.is_suspended.is_(True))
        ),
        "starters": await count(
            select(func.count()).select_from(Starter).where(Starter.deleted_at.is_(None))
        ),
        "feedings": await count(select(func.count()).select_from(Feeding)),
        "proof_sessions": await count(select(func.count()).select_from(ProofSession)),
        "bakes": await count(
            select(func.count()).select_from(Bake).where(Bake.deleted_at.is_(None))
        ),
        "recipes": await count(
            select(func.count()).select_from(Recipe).where(Recipe.deleted_at.is_(None))
        ),
        "recipes_public": await count(
            select(func.count())
            .select_from(Recipe)
            .where(Recipe.deleted_at.is_(None), Recipe.is_public.is_(True))
        ),
        "photos": await count(select(func.count()).select_from(BakePhoto)),
        "notifications_pending": await count(
            select(func.count())
            .select_from(ScheduledNotification)
            .where(ScheduledNotification.status == DeliveryStatus.pending)
        ),
        "notifications_failed": await count(
            select(func.count())
            .select_from(ScheduledNotification)
            .where(ScheduledNotification.status == DeliveryStatus.failed)
        ),
        "xp_awarded": await count(select(func.coalesce(func.sum(XPEvent.amount), 0))),
        "achievements_earned": await count(select(func.count()).select_from(UserAchievement)),
        "database_bytes": await count(select(func.pg_database_size(func.current_database()))),
    }
