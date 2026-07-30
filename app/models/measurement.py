"""Ingredient densities: the catalogue projection and per-baker overrides.

`ingredient_measure` is a **projection of the code catalogue**, the same
arrangement as `achievement`: the numbers are authored and reviewed in
`app/services/measurements/catalogue.py`, and this table exists so clients can
list them and so an override has something to point a foreign key at. Refresh it
with `sdt seed-measurements`; never edit it by hand.

`user_ingredient_measure` is the opposite — real user data. A baker who weighs a
cup of their local mill's rye knows better than any published chart, and their
number outranks it.
"""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamped
from app.models.recipe import IngredientKind


class IngredientMeasureRow(Base, Timestamped):
    __tablename__ = "ingredient_measure"

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[IngredientKind] = mapped_column(String(20), nullable=False, index=True)
    grams_per_cup: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    """How the reference filled the cup. A density without this is unreproducible."""

    source: Mapped[str] = mapped_column(String(200), nullable=False)
    """Where the number came from, so it can be checked rather than argued about."""

    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    volume_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    """Why volume is refused — salt varies 2.25-fold by grind, starter is mostly gas."""


class UserIngredientMeasure(Base, Timestamped):
    """A baker's own measured density, overriding the catalogue for them alone."""

    __tablename__ = "user_ingredient_measure"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_user_ingredient_measure"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(
        String(60), ForeignKey("ingredient_measure.slug", ondelete="CASCADE"), nullable=False
    )
    grams_per_cup: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    """"my local mill's rye, weighed three times" — context for a future self."""

    catalogue_entry: Mapped[IngredientMeasureRow] = relationship(lazy="joined")
