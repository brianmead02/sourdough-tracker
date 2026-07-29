"""SQLAlchemy models.

Every model module must be imported here so Alembic autogenerate sees the full
metadata. Later phases append to this list.
"""

from app.models.bake import Bake, BakePhoto, BakeRating, BakeStatus, PhotoKind
from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey
from app.models.gamification import (
    Achievement,
    AchievementCategory,
    LeaderboardEntry,
    Rarity,
    Season,
    UserAchievement,
    XPEvent,
)
from app.models.inventory import (
    InventoryItem,
    InventoryTransaction,
    ItemKind,
    TransactionKind,
)
from app.models.notification import (
    ChannelKind,
    DeliveryStatus,
    InAppNotification,
    NotificationChannel,
    NotificationEvent,
    NotificationLog,
    NotificationSettings,
    ScheduledNotification,
)
from app.models.proofing import (
    PokeTest,
    ProofCheck,
    ProofSession,
    ProofStage,
    ProofStatus,
)
from app.models.recipe import IngredientKind, Recipe, RecipeIngredient, RecipeStar
from app.models.starter import (
    Aroma,
    Feeding,
    Starter,
    StarterObservation,
    StarterState,
)
from app.models.user import (
    EmailVerification,
    PasswordReset,
    RefreshToken,
    User,
    UserProfile,
    UserRole,
)

__all__ = [
    "Achievement",
    "AchievementCategory",
    "Aroma",
    "Bake",
    "BakePhoto",
    "BakeRating",
    "BakeStatus",
    "Base",
    "ChannelKind",
    "DeliveryStatus",
    "EmailVerification",
    "Feeding",
    "InAppNotification",
    "IngredientKind",
    "InventoryItem",
    "InventoryTransaction",
    "ItemKind",
    "LeaderboardEntry",
    "NotificationChannel",
    "NotificationEvent",
    "NotificationLog",
    "NotificationSettings",
    "PasswordReset",
    "PhotoKind",
    "PokeTest",
    "ProofCheck",
    "ProofSession",
    "ProofStage",
    "ProofStatus",
    "Rarity",
    "Recipe",
    "RecipeIngredient",
    "RecipeStar",
    "RefreshToken",
    "ScheduledNotification",
    "Season",
    "SoftDeletable",
    "Starter",
    "StarterObservation",
    "StarterState",
    "Timestamped",
    "TransactionKind",
    "UUIDPrimaryKey",
    "User",
    "UserAchievement",
    "UserProfile",
    "UserRole",
    "XPEvent",
]
