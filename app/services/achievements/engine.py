"""Evaluating achievements and publishing domain events."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bake import Bake, BakePhoto
from app.models.gamification import UserAchievement
from app.services import xp as xp_service
from app.services.achievements.definitions import ACHIEVEMENTS, BY_EVENT, AchievementDef
from app.services.achievements.metrics import measure
from app.services.events import BASE_XP, DAILY_CAPS, DomainEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Award:
    code: str
    name: str
    description: str
    icon: str
    rarity: str
    xp_award: int


@dataclass(slots=True)
class PublishResult:
    xp_gained: int = 0
    awards: list[Award] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.awards is None:
            self.awards = []


@dataclass(slots=True)
class AchievementProgress:
    code: str
    current: float
    target: float
    percent: float
    earned: bool
    earned_at: datetime | None


async def _has_photo_evidence(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(BakePhoto)
        .join(Bake, Bake.id == BakePhoto.bake_id)
        .where(Bake.user_id == user_id, Bake.deleted_at.is_(None))
    )
    return int(result.scalar_one()) > 0


async def _earned_codes(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    result = await db.execute(
        select(UserAchievement.achievement_code).where(UserAchievement.user_id == user_id)
    )
    return set(result.scalars().all())


async def evaluate(
    db: AsyncSession,
    user_id: uuid.UUID,
    candidates: tuple[AchievementDef, ...],
) -> list[Award]:
    """Award any of `candidates` whose metric has reached its target."""
    if not candidates:
        return []

    already = await _earned_codes(db, user_id)
    pending = [a for a in candidates if a.code not in already]
    if not pending:
        return []

    # One measurement per distinct metric, however many badges use it.
    values: dict[str, float] = {}
    for definition in pending:
        if definition.metric not in values:
            values[definition.metric] = await measure(db, definition.metric, user_id)

    awards: list[Award] = []
    now = datetime.now(UTC)
    photo_checked: bool | None = None

    for definition in pending:
        value = values[definition.metric]
        if value < definition.target:
            continue

        if definition.requires_photo:
            if photo_checked is None:
                photo_checked = await _has_photo_evidence(db, user_id)
            if not photo_checked:
                # Earned on the numbers, withheld for want of evidence. It will
                # be granted the moment a photo exists.
                continue

        result = await db.execute(
            insert(UserAchievement)
            .values(
                user_id=user_id,
                achievement_code=definition.code,
                earned_at=now,
                earned_value=value,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "achievement_code"])
            .returning(UserAchievement.achievement_code)
        )
        if result.first() is None:
            continue  # raced with another request; it was awarded there

        await xp_service.award(
            db,
            user_id=user_id,
            rule_code=f"achievement.{definition.code}",
            source_type="achievement",
            source_id=xp_service.source_id_for(definition.code),
            amount=definition.xp_award,
        )
        awards.append(
            Award(
                code=definition.code,
                name=definition.name,
                description=definition.description,
                icon=definition.icon,
                rarity=definition.rarity.value,
                xp_award=definition.xp_award,
            )
        )
        logger.info("achievement earned user=%s code=%s", user_id, definition.code)

    return awards


async def publish(
    db: AsyncSession,
    event: DomainEvent,
    *,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> PublishResult:
    """Record that something happened: pay its XP, then check its achievements."""
    result = PublishResult()

    result.xp_gained += await xp_service.award(
        db,
        user_id=user_id,
        rule_code=f"xp.{event.value}",
        source_type=source_type,
        source_id=source_id,
        amount=BASE_XP.get(event, 0),
        daily_cap=DAILY_CAPS.get(event),
    )

    awards = await evaluate(db, user_id, BY_EVENT.get(event, ()))
    # Earning a badge can itself complete a "collect N badges" badge, so run one
    # more pass. One extra round is enough: meta-achievements do not chain.
    if awards:
        awards += await evaluate(db, user_id, BY_EVENT.get(DomainEvent.achievement_earned, ()))

    result.awards.extend(awards)
    result.xp_gained += sum(a.xp_award for a in awards)
    return result


async def progress_for(db: AsyncSession, user_id: uuid.UUID) -> list[AchievementProgress]:
    """Every achievement with the user's current standing against it."""
    earned = await db.execute(
        select(UserAchievement.achievement_code, UserAchievement.earned_at).where(
            UserAchievement.user_id == user_id
        )
    )
    earned_at_by_code: dict[str, datetime] = {row[0]: row[1] for row in earned.all()}

    values: dict[str, float] = {}
    for definition in ACHIEVEMENTS:
        if definition.metric not in values:
            values[definition.metric] = await measure(db, definition.metric, user_id)

    return [
        AchievementProgress(
            code=definition.code,
            current=round(values[definition.metric], 2),
            target=definition.target,
            percent=round(min(values[definition.metric] / definition.target * 100, 100.0), 1)
            if definition.target
            else 100.0,
            earned=definition.code in earned_at_by_code,
            earned_at=earned_at_by_code.get(definition.code),
        )
        for definition in ACHIEVEMENTS
    ]
