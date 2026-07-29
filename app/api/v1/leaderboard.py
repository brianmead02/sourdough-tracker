"""Service-wide leaderboards."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.db import get_session
from app.models.gamification import LeaderboardEntry, Season
from app.models.user import User, UserProfile, UserRole
from app.schemas.gamification import (
    LeaderboardPage,
    LeaderboardRow,
    MyRankResponse,
    RefreshResponse,
)
from app.services import leaderboard as leaderboard_service
from app.services import xp as xp_service

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

Category = Literal["xp", "lifetime", "bakes", "streak", "crumb", "achievements"]

# Category boards exist so one metric cannot dominate: someone who bakes rarely
# but keeps an immaculate starter still has a board to top (docs/PLAN.md §7).
ORDERING: dict[str, Any] = {
    "xp": LeaderboardEntry.season_xp.desc(),
    "lifetime": LeaderboardEntry.lifetime_xp.desc(),
    "bakes": LeaderboardEntry.bake_count.desc(),
    "streak": LeaderboardEntry.longest_streak.desc(),
    "crumb": LeaderboardEntry.average_crumb.desc().nullslast(),
    "achievements": LeaderboardEntry.achievement_count.desc(),
}


def _row(
    entry: LeaderboardEntry,
    handle: str | None,
    display_name: str | None,
    is_public: bool,
    viewer_id: uuid.UUID,
    position: int,
) -> LeaderboardRow:
    """A private profile still ranks, but appears anonymously.

    Opting out of a public profile should not mean opting out of competing, and
    it must not silently expose a name the user chose not to publish.
    """
    mine = entry.user_id == viewer_id
    visible = is_public or mine
    return LeaderboardRow(
        rank=position,
        handle=handle if visible else None,
        display_name=display_name if visible else "Anonymous Baker",
        is_you=mine,
        season_xp=entry.season_xp,
        lifetime_xp=entry.lifetime_xp,
        bake_count=entry.bake_count,
        longest_streak=entry.longest_streak,
        average_crumb=entry.average_crumb,
        achievement_count=entry.achievement_count,
        tier=xp_service.tier_for(entry.lifetime_xp).name,
    )


async def _resolve_season(db: AsyncSession, season_name: str | None) -> Season:
    if season_name is None:
        return await xp_service.current_season(db)
    result = await db.execute(select(Season).where(Season.name == season_name))
    season = result.scalar_one_or_none()
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    return season


@router.get("", response_model=LeaderboardPage)
async def read_leaderboard(
    user: CurrentUser,
    db: SessionDep,
    category: Annotated[Category, Query()] = "xp",
    season: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardPage:
    active = await _resolve_season(db, season)

    rows = await db.execute(
        select(
            LeaderboardEntry, UserProfile.handle, UserProfile.display_name, UserProfile.is_public
        )
        .join(User, User.id == LeaderboardEntry.user_id)
        .join(UserProfile, UserProfile.user_id == LeaderboardEntry.user_id)
        .where(
            LeaderboardEntry.season_id == active.id,
            User.deleted_at.is_(None),
            User.is_suspended.is_(False),
        )
        .order_by(ORDERING[category], LeaderboardEntry.lifetime_xp.desc())
        .limit(limit)
        .offset(offset)
    )

    entries = rows.all()
    refreshed = max((e[0].updated_at for e in entries), default=None)
    return LeaderboardPage(
        season_id=active.id,
        season_name=active.name,
        category=category,
        # Position is per-board: rank 1 on the crumb board is not rank 1 on XP.
        rows=[
            _row(entry, handle, display_name, is_public, user.id, offset + index)
            for index, (entry, handle, display_name, is_public) in enumerate(entries, start=1)
        ],
        refreshed_at=refreshed,
    )


@router.get("/me", response_model=MyRankResponse)
async def my_rank(
    user: CurrentUser,
    db: SessionDep,
    season: Annotated[str | None, Query(max_length=30)] = None,
) -> MyRankResponse:
    """Your standing, with the bakers immediately above and below you."""
    active = await _resolve_season(db, season)

    total = await db.execute(select(func.count()).where(LeaderboardEntry.season_id == active.id))
    mine = await db.execute(
        select(LeaderboardEntry).where(
            LeaderboardEntry.season_id == active.id, LeaderboardEntry.user_id == user.id
        )
    )
    entry = mine.scalar_one_or_none()
    if entry is None:
        return MyRankResponse(
            season_name=active.name, rank=None, total_ranked=int(total.scalar_one()), neighbours=[]
        )

    window_start = max(entry.rank - 2, 1)
    rows = await db.execute(
        select(
            LeaderboardEntry, UserProfile.handle, UserProfile.display_name, UserProfile.is_public
        )
        .join(UserProfile, UserProfile.user_id == LeaderboardEntry.user_id)
        .where(
            LeaderboardEntry.season_id == active.id,
            LeaderboardEntry.rank >= window_start,
            LeaderboardEntry.rank <= entry.rank + 2,
        )
        .order_by(LeaderboardEntry.rank)
    )

    return MyRankResponse(
        season_name=active.name,
        rank=entry.rank,
        total_ranked=int(total.scalar_one()),
        neighbours=[
            _row(row, handle, display_name, is_public, user.id, row.rank)
            for row, handle, display_name, is_public in rows.all()
        ],
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(require_role(UserRole.admin))],
)
async def refresh_leaderboard(db: SessionDep) -> RefreshResponse:
    """Rebuild the rollup now. Also runs on a schedule in the beat worker."""
    result = await leaderboard_service.refresh(db)
    return RefreshResponse(season_name=result.season_name, users_ranked=result.users_ranked)
