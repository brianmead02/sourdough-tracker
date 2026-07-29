"""SQLAlchemy models.

Every model module must be imported here so Alembic autogenerate sees the full
metadata. Later phases append to this list.
"""

from app.models.bake import Bake, BakePhoto, BakeRating, BakeStatus, PhotoKind
from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey
from app.models.inventory import (
    InventoryItem,
    InventoryTransaction,
    ItemKind,
    TransactionKind,
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
    "Aroma",
    "Bake",
    "BakePhoto",
    "BakeRating",
    "BakeStatus",
    "Base",
    "EmailVerification",
    "Feeding",
    "IngredientKind",
    "InventoryItem",
    "InventoryTransaction",
    "ItemKind",
    "PasswordReset",
    "PhotoKind",
    "PokeTest",
    "ProofCheck",
    "ProofSession",
    "ProofStage",
    "ProofStatus",
    "Recipe",
    "RecipeIngredient",
    "RecipeStar",
    "RefreshToken",
    "SoftDeletable",
    "Starter",
    "StarterObservation",
    "StarterState",
    "Timestamped",
    "TransactionKind",
    "UUIDPrimaryKey",
    "User",
    "UserProfile",
    "UserRole",
]
