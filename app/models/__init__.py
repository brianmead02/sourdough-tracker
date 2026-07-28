"""SQLAlchemy models.

Every model module must be imported here so Alembic autogenerate sees the full
metadata. Later phases append to this list.
"""

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey
from app.models.user import (
    EmailVerification,
    PasswordReset,
    RefreshToken,
    User,
    UserProfile,
    UserRole,
)

__all__ = [
    "Base",
    "EmailVerification",
    "PasswordReset",
    "RefreshToken",
    "SoftDeletable",
    "Timestamped",
    "UUIDPrimaryKey",
    "User",
    "UserProfile",
    "UserRole",
]
