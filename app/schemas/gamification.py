"""Request/response models for XP, achievements and leaderboards."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.gamification import AchievementCategory, Rarity


class AwardResponse(BaseModel):
    code: str
    name: str
    description: str
    icon: str
    rarity: str
    xp_award: int


class TierResponse(BaseModel):
    tier: str
    icon: str
    lifetime_xp: int
    season_xp: int
    season_name: str
    next_tier: str | None
    xp_to_next: int | None
    progress_pct: float
    achievements_earned: int
    achievements_total: int


class AchievementResponse(BaseModel):
    code: str
    name: str
    description: str
    category: AchievementCategory
    rarity: Rarity
    icon: str
    xp_award: int
    target: float
    requires_photo: bool
    current: float
    percent: float
    earned: bool
    earned_at: datetime | None


class XPEventResponse(BaseModel):
    rule_code: str
    source_type: str
    amount: int
    created_at: datetime


class LeaderboardRow(BaseModel):
    rank: int
    handle: str | None
    display_name: str | None
    is_you: bool
    season_xp: int
    lifetime_xp: int
    bake_count: int
    longest_streak: int
    average_crumb: float | None
    achievement_count: int
    tier: str


class LeaderboardPage(BaseModel):
    season_id: uuid.UUID
    season_name: str
    category: str
    rows: list[LeaderboardRow]
    refreshed_at: datetime | None


class MyRankResponse(BaseModel):
    season_name: str
    rank: int | None
    total_ranked: int
    neighbours: list[LeaderboardRow]


class RefreshResponse(BaseModel):
    season_name: str
    users_ranked: int
