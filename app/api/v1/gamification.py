"""XP, tiers and achievements for the signed-in user."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db import get_session
from app.models.gamification import UserAchievement, XPEvent
from app.schemas.gamification import (
    AchievementResponse,
    TierResponse,
    XPEventResponse,
)
from app.services import xp as xp_service
from app.services.achievements import ACHIEVEMENTS, BY_CODE, progress_for

router = APIRouter(prefix="/gamification", tags=["gamification"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/tier", response_model=TierResponse)
async def my_tier(user: CurrentUser, db: SessionDep) -> TierResponse:
    lifetime = await xp_service.lifetime_xp(db, user.id)
    season = await xp_service.current_season(db)
    seasonal = await xp_service.season_xp(db, user.id, season.id)
    progress = xp_service.tier_progress(lifetime)

    earned = await db.execute(select(func.count()).where(UserAchievement.user_id == user.id))

    return TierResponse(
        tier=progress.tier,
        icon=progress.icon,
        lifetime_xp=progress.lifetime_xp,
        season_xp=seasonal,
        season_name=season.name,
        next_tier=progress.next_tier,
        xp_to_next=progress.xp_to_next,
        progress_pct=progress.progress_pct,
        achievements_earned=int(earned.scalar_one()),
        achievements_total=len(ACHIEVEMENTS),
    )


@router.get("/achievements", response_model=list[AchievementResponse])
async def my_achievements(
    user: CurrentUser,
    db: SessionDep,
    earned_only: Annotated[bool, Query()] = False,
) -> list[AchievementResponse]:
    """The full catalogue with this user's progress against each entry."""
    progress = await progress_for(db, user.id)
    rows = [
        AchievementResponse(
            code=entry.code,
            name=BY_CODE[entry.code].name,
            description=BY_CODE[entry.code].description,
            category=BY_CODE[entry.code].category,
            rarity=BY_CODE[entry.code].rarity,
            icon=BY_CODE[entry.code].icon,
            xp_award=BY_CODE[entry.code].xp_award,
            target=entry.target,
            requires_photo=BY_CODE[entry.code].requires_photo,
            current=entry.current,
            percent=entry.percent,
            earned=entry.earned,
            earned_at=entry.earned_at,
        )
        for entry in progress
    ]
    if earned_only:
        rows = [r for r in rows if r.earned]
    # Earned first, then whatever is closest to completion.
    return sorted(rows, key=lambda r: (not r.earned, -r.percent))


@router.get("/xp/history", response_model=list[XPEventResponse])
async def xp_history(
    user: CurrentUser,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[XPEventResponse]:
    result = await db.execute(
        select(XPEvent)
        .where(XPEvent.user_id == user.id)
        .order_by(XPEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        XPEventResponse(
            rule_code=event.rule_code,
            source_type=event.source_type,
            amount=event.amount,
            created_at=event.created_at,
        )
        for event in result.scalars().all()
    ]
