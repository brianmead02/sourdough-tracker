"""SQLAlchemy models.

Every model module must be imported here so Alembic autogenerate sees the full
metadata. Phase 1 onward appends to this list.
"""

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey

__all__ = ["Base", "SoftDeletable", "Timestamped", "UUIDPrimaryKey"]
