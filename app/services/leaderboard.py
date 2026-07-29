"""Leaderboard rollup.

Every board — XP, bakes, streaks, crumb — reads one periodically-refreshed
table. Computing them live would mean aggregating the whole history of the
service on every page view; a rollup makes a board an indexed scan.

The plan floated a Redis sorted set in front of this. That is deliberately not
here: the rollup table is already a cache, and a second one would be a third
copy of the truth to keep in step for no measurable gain at this size. The seam
is a single function, so it can be added when a board is actually slow.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Float, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bake import Bake, BakeRating, BakeStatus
from app.models.gamification import LeaderboardEntry, Season, UserAchievement, XPEvent
from app.models.starter import Feeding, Starter
from app.models.user import User
from app.services import xp as xp_service
from app.services.starters import compute_streak

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RefreshResult:
    season_name: str
    users_ranked: int


async def _longest_streaks(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Best streak per user, derived from feedings (never a stored counter)."""
    if not user_ids:
        return {}

    rows = await db.execute(
        select(Starter.user_id, Starter.id, Starter.feed_interval_hours).where(
            Starter.user_id.in_(user_ids), Starter.deleted_at.is_(None)
        )
    )
    starters = rows.all()
    if not starters:
        return {}

    feedings = await db.execute(
        select(Feeding.starter_id, Feeding.fed_at)
        .where(Feeding.starter_id.in_([s[1] for s in starters]))
        .order_by(Feeding.fed_at)
    )
    times_by_starter: dict[uuid.UUID, list[datetime]] = {}
    for starter_id, fed_at in feedings.all():
        times_by_starter.setdefault(starter_id, []).append(fed_at)

    now = datetime.now(UTC)
    best: dict[uuid.UUID, int] = {}
    for user_id, starter_id, interval in starters:
        stats = compute_streak(times_by_starter.get(starter_id, []), interval, now)
        best[user_id] = max(best.get(user_id, 0), stats.longest)
    return best


async def refresh(db: AsyncSession, season_id: uuid.UUID | None = None) -> RefreshResult:
    """Rebuild the rollup for a season. Idempotent — safe to run on a cron."""
    if season_id is None:
        season = await xp_service.current_season(db)
    else:
        found = await db.get(Season, season_id)
        if found is None:
            raise ValueError(f"unknown season {season_id}")
        season = found

    lifetime = await db.execute(
        select(XPEvent.user_id, func.sum(XPEvent.amount)).group_by(XPEvent.user_id)
    )
    lifetime_by_user = {row[0]: int(row[1] or 0) for row in lifetime.all()}

    seasonal = await db.execute(
        select(XPEvent.user_id, func.sum(XPEvent.amount))
        .where(XPEvent.season_id == season.id)
        .group_by(XPEvent.user_id)
    )
    season_by_user = {row[0]: int(row[1] or 0) for row in seasonal.all()}

    bakes = await db.execute(
        select(Bake.user_id, func.count())
        .where(Bake.deleted_at.is_(None), Bake.status == BakeStatus.done)
        .group_by(Bake.user_id)
    )
    bakes_by_user = {row[0]: int(row[1]) for row in bakes.all()}

    crumb = await db.execute(
        select(Bake.user_id, func.avg(cast(BakeRating.crumb, Float)))
        .join(BakeRating, BakeRating.bake_id == Bake.id)
        .where(Bake.deleted_at.is_(None), BakeRating.crumb.is_not(None))
        .group_by(Bake.user_id)
    )
    crumb_by_user = {row[0]: float(row[1]) for row in crumb.all()}

    badges = await db.execute(
        select(UserAchievement.user_id, func.count()).group_by(UserAchievement.user_id)
    )
    badges_by_user = {row[0]: int(row[1]) for row in badges.all()}

    # Suspended and deleted accounts never appear on a public board.
    eligible = await db.execute(
        select(User.id).where(User.deleted_at.is_(None), User.is_suspended.is_(False))
    )
    user_ids = [
        user_id
        for (user_id,) in eligible.all()
        if user_id in lifetime_by_user or user_id in bakes_by_user
    ]

    streaks = await _longest_streaks(db, user_ids)

    ranked = sorted(
        user_ids,
        key=lambda uid: (-season_by_user.get(uid, 0), -lifetime_by_user.get(uid, 0), str(uid)),
    )

    await db.execute(delete(LeaderboardEntry).where(LeaderboardEntry.season_id == season.id))
    for position, user_id in enumerate(ranked, start=1):
        db.add(
            LeaderboardEntry(
                season_id=season.id,
                user_id=user_id,
                season_xp=season_by_user.get(user_id, 0),
                lifetime_xp=lifetime_by_user.get(user_id, 0),
                bake_count=bakes_by_user.get(user_id, 0),
                longest_streak=streaks.get(user_id, 0),
                average_crumb=round(crumb_by_user[user_id], 2)
                if user_id in crumb_by_user
                else None,
                achievement_count=badges_by_user.get(user_id, 0),
                rank=position,
            )
        )

    await db.flush()
    logger.info("leaderboard refreshed season=%s users=%d", season.name, len(ranked))
    return RefreshResult(season_name=season.name, users_ranked=len(ranked))
