"""Flour stock as an append-only ledger.

There is deliberately **no `quantity_on_hand` column**. On-hand is the sum of the
ledger, exactly as a streak is derived from feedings (Phase 2): a stored counter
and a transaction history are two sources of truth that will eventually disagree,
and when they do the counter is the one that is wrong.

Everything is grams. Water comes from the tap and is not inventoried; flour,
salt, seeds and other inclusions are all weighed, so a single unit keeps the
arithmetic — and the cost report — honest.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeletable, Timestamped, UUIDPrimaryKey


class ItemKind(enum.StrEnum):
    flour = "flour"
    salt = "salt"
    inclusion = "inclusion"
    other = "other"


class TransactionKind(enum.StrEnum):
    purchase = "purchase"
    consume = "consume"
    adjust = "adjust"


def _enum_column(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        name=name,
    )


class InventoryItem(Base, UUIDPrimaryKey, Timestamped, SoftDeletable):
    __tablename__ = "inventory_item"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[ItemKind] = mapped_column(
        _enum_column(ItemKind, "item_kind"), default=ItemKind.flour, nullable=False
    )
    low_threshold_g: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))

    transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index(
            "uq_inventory_item_user_name_live",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class InventoryTransaction(Base, UUIDPrimaryKey, Timestamped):
    """One movement of stock. Append-only: corrections are new `adjust` rows.

    `unit_cost_per_kg` is stamped on **consume** rows as well as purchases, using
    the weighted average at that moment. Without it, buying cheaper flour next
    month would silently rewrite what last month's loaves cost.
    """

    __tablename__ = "inventory_transaction"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_item.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[TransactionKind] = mapped_column(
        _enum_column(TransactionKind, "transaction_kind"), nullable=False
    )
    # Signed: purchases add, consumption subtracts, adjustments do either.
    delta_g: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost_per_kg: Mapped[float | None] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))

    # Set when a bake consumed this stock, so a cost can be traced to its loaf.
    bake_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bake.id", ondelete="SET NULL"), index=True
    )

    item: Mapped[InventoryItem] = relationship(back_populates="transactions")

    __table_args__ = (Index("ix_inventory_transaction_item_time", "item_id", "occurred_at"),)
