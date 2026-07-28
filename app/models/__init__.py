"""SQLAlchemy models.

Every model module must be imported here so Alembic autogenerate sees the full
metadata. Later phases append to this list.
"""

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey
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
    "Base",
    "EmailVerification",
    "Feeding",
    "PasswordReset",
    "RefreshToken",
    "SoftDeletable",
    "Starter",
    "StarterObservation",
    "StarterState",
    "Timestamped",
    "UUIDPrimaryKey",
    "User",
    "UserProfile",
    "UserRole",
]
