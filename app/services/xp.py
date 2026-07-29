"""XP awards, tiers and seasons."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import Season, XPEvent

# Namespace for deriving a stable source id from a string key, so awards that
# have no natural row (an achievement, a season bonus) still get a unique key.
SOURCE_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


@dataclass(frozen=True, slots=True)
class Tier:
    name: str
    threshold: int
    icon: str


# Lifetime XP, so a tier is never lost when a season resets.
TIERS: tuple[Tier, ...] = (
    Tier("Novice", 0, "🌱"),
    Tier("Home Baker", 250, "🍞"),
    Tier("Levain Keeper", 1_000, "🫙"),
    Tier("Crumb Chaser", 3_000, "🔍"),
    Tier("Artisan", 8_000, "🥖"),
    Tier("Master Baker", 20_000, "👑"),
)


@dataclass(slots=True)
class TierProgress:
    tier: str
    icon: str
    lifetime_xp: int
    next_tier: str | None
    xp_to_next: int | None
    progress_pct: float


def tier_for(lifetime_xp: int) -> Tier:
    current = TIERS[0]
    for tier in TIERS:
        if lifetime_xp >= tier.threshold:
            current = tier
    return current


def tier_progress(lifetime_xp: int) -> TierProgress:
    current = tier_for(lifetime_xp)
    index = TIERS.index(current)
    following = TIERS[index + 1] if index + 1 < len(TIERS) else None

    if following is None:
        return TierProgress(current.name, current.icon, lifetime_xp, None, None, 100.0)

    span = following.threshold - current.threshold
    gained = lifetime_xp - current.threshold
    return TierProgress(
        tier=current.name,
        icon=current.icon,
        lifetime_xp=lifetime_xp,
        next_tier=following.name,
        xp_to_next=following.threshold - lifetime_xp,
        progress_pct=round(gained / span * 100, 1) if span else 100.0,
    )


def source_id_for(key: str) -> uuid.UUID:
    """Deterministic id for an award with no natural row."""
    return uuid.uuid5(SOURCE_NAMESPACE, key)


# --- seasons ----------------------------------------------------------------


def quarter_bounds(moment: datetime) -> tuple[str, datetime, datetime]:
    quarter = (moment.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    starts = datetime(moment.year, start_month, 1, tzinfo=UTC)
    if quarter == 4:
        ends = datetime(moment.year + 1, 1, 1, tzinfo=UTC)
    else:
        ends = datetime(moment.year, start_month + 3, 1, tzinfo=UTC)
    return f"{moment.year} Q{quarter}", starts, ends


async def current_season(db: AsyncSession, moment: datetime | None = None) -> Season:
    """The season containing `moment`, created on demand.

    Quarters are derived from the calendar rather than administered, so a season
    can never fail to exist because nobody remembered to roll it over.
    """
    now = moment or datetime.now(UTC)
    name, starts, ends = quarter_bounds(now)

    result = await db.execute(select(Season).where(Season.name == name))
    season = result.scalar_one_or_none()
    if season is not None:
        return season

    # Two requests can race here; the unique name makes the loser a no-op.
    await db.execute(
        insert(Season)
        .values(id=uuid.uuid4(), name=name, starts_at=starts, ends_at=ends)
        .on_conflict_do_nothing(index_elements=["name"])
    )
    await db.flush()
    result = await db.execute(select(Season).where(Season.name == name))
    return result.scalar_one()


# --- awarding ---------------------------------------------------------------


def day_start(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def daily_count(db: AsyncSession, user_id: uuid.UUID, rule_code: str, at: datetime) -> int:
    """How many times this rule has paid out on the UTC day containing `at`.

    A calendar day rather than a rolling 24 hours: it is predictable for the
    user ("resets at midnight UTC") and it lets `sdt recompute-xp` replay the
    same caps exactly, which a sliding window could not.
    """
    start = day_start(at)
    result = await db.execute(
        select(func.count())
        .select_from(XPEvent)
        .where(
            XPEvent.user_id == user_id,
            XPEvent.rule_code == rule_code,
            XPEvent.created_at >= start,
            XPEvent.created_at < start + timedelta(days=1),
        )
    )
    return int(result.scalar_one())


async def award(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    rule_code: str,
    source_type: str,
    source_id: uuid.UUID,
    amount: int,
    daily_cap: int | None = None,
    at: datetime | None = None,
) -> int:
    """Record an XP award. Returns the XP actually granted (0 if not granted).

    Duplicate awards are absorbed by the unique key rather than checked first,
    so two concurrent requests cannot both pass a check and both insert.

    `at` backdates the award, which replay uses so historical events land in the
    season and the daily bucket they actually belong to.
    """
    if amount <= 0:
        return 0

    moment = at or datetime.now(UTC)

    if daily_cap is not None and await daily_count(db, user_id, rule_code, moment) >= daily_cap:
        # Blunts grinding without punishing a genuinely busy baking day: the
        # action still succeeds, it just stops paying.
        return 0

    season = await current_season(db, moment)
    result = await db.execute(
        insert(XPEvent)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            rule_code=rule_code,
            source_type=source_type,
            source_id=source_id,
            amount=amount,
            season_id=season.id,
            created_at=moment,
        )
        .on_conflict_do_nothing(constraint="uq_xp_event_source")
        .returning(XPEvent.id)
    )
    return amount if result.first() is not None else 0


async def lifetime_xp(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(XPEvent.amount), 0)).where(XPEvent.user_id == user_id)
    )
    return int(result.scalar_one())


async def season_xp(db: AsyncSession, user_id: uuid.UUID, season_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(XPEvent.amount), 0)).where(
            XPEvent.user_id == user_id, XPEvent.season_id == season_id
        )
    )
    return int(result.scalar_one())
