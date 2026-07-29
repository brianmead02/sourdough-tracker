"""Recipes expressed in baker's percentages, and the stars/forks on them."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey


class IngredientKind(enum.StrEnum):
    flour = "flour"
    liquid = "liquid"
    salt = "salt"
    starter = "starter"
    inclusion = "inclusion"


class Recipe(Base, UUIDPrimaryKey, Timestamped, SoftDeletable):
    __tablename__ = "recipe"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    forked_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    default_dough_weight_g: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    # Hydration of the starter this recipe assumes, needed to split the starter
    # into its flour and water halves when computing true hydration.
    starter_hydration_pct: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    steps: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)

    # Denormalised counters, maintained in the same transaction as the row that
    # causes them. Cheap listing and sorting; `sdt` can recompute them if they
    # ever drift.
    star_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fork_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RecipeIngredient.sort_order",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "uq_recipe_owner_name_live",
            "owner_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_recipe_public_stars",
            "is_public",
            text("star_count DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class RecipeIngredient(Base, UUIDPrimaryKey):
    """One line of a recipe, as a percentage of total flour.

    Grams are never stored — they are a function of the batch size the baker
    chooses, so storing them would create a second source of truth that drifts
    the moment a recipe is scaled.
    """

    __tablename__ = "recipe_ingredient"

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[IngredientKind] = mapped_column(
        SAEnum(
            IngredientKind,
            native_enum=False,
            length=16,
            values_callable=lambda e: [m.value for m in e],
            name="ingredient_kind",
        ),
        nullable=False,
    )
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")

    __table_args__ = (Index("ix_recipe_ingredient_recipe", "recipe_id", "sort_order"),)


class RecipeStar(Base):
    """A user's star on a public recipe. Composite key makes double-starring impossible."""

    __tablename__ = "recipe_star"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
