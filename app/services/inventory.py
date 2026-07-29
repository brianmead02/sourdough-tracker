"""Stock arithmetic and bake costing.

Valuation is **weighted average**, not FIFO. FIFO would be more precise for
someone running a bakery, but it requires tracking individual lots through
partial consumption, and for a home baker topping up the same flour bin it would
add a lot of machinery for a difference smaller than the scale error. The
average is stamped onto each consumption at the time it happens, so buying
cheaper flour later never rewrites what an earlier loaf cost.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bake import Bake
from app.models.inventory import (
    InventoryItem,
    InventoryTransaction,
    ItemKind,
    TransactionKind,
)

GRAMS_PER_KG = 1000.0


@dataclass(slots=True)
class ItemStock:
    on_hand_g: float
    average_cost_per_kg: float | None
    stock_value: float | None
    is_low: bool


@dataclass(slots=True)
class ConsumedLine:
    item_name: str
    grams: float
    cost: float | None


@dataclass(slots=True)
class ConsumptionResult:
    consumed: list[ConsumedLine] = field(default_factory=list)
    # Blend components with no matching inventory item. Reported rather than
    # silently dropped: a cost that quietly excludes half the flour is worse
    # than no cost at all.
    unmatched: list[str] = field(default_factory=list)
    total_cost: float | None = None
    cost_per_loaf: float | None = None
    skipped_reason: str | None = None


def weighted_average_cost_per_kg(purchased_g: float, purchase_cost: float) -> float | None:
    """Average paid per kilogram across everything bought so far."""
    if purchased_g <= 0:
        return None
    return round(purchase_cost / (purchased_g / GRAMS_PER_KG), 4)


def cost_of(grams: float, cost_per_kg: float | None) -> float | None:
    if cost_per_kg is None:
        return None
    return round(grams / GRAMS_PER_KG * cost_per_kg, 4)


def split_blend(flour_blend: dict[str, float], total_flour_g: float) -> dict[str, float]:
    """Turn a percentage blend into grams per flour."""
    return {name: total_flour_g * pct / 100 for name, pct in flour_blend.items()}


async def item_stock(db: AsyncSession, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, ItemStock]:
    """On-hand and valuation for a set of items, in two aggregate queries."""
    if not item_ids:
        return {}

    balances = await db.execute(
        select(InventoryTransaction.item_id, func.sum(InventoryTransaction.delta_g))
        .where(InventoryTransaction.item_id.in_(item_ids))
        .group_by(InventoryTransaction.item_id)
    )
    on_hand = {row[0]: float(row[1] or 0.0) for row in balances.all()}

    purchases = await db.execute(
        select(
            InventoryTransaction.item_id,
            func.sum(InventoryTransaction.delta_g),
            func.sum(
                InventoryTransaction.delta_g
                / GRAMS_PER_KG
                * func.coalesce(InventoryTransaction.unit_cost_per_kg, 0.0)
            ),
        )
        .where(
            InventoryTransaction.item_id.in_(item_ids),
            InventoryTransaction.kind == TransactionKind.purchase,
            InventoryTransaction.unit_cost_per_kg.is_not(None),
        )
        .group_by(InventoryTransaction.item_id)
    )
    averages = {
        row[0]: weighted_average_cost_per_kg(float(row[1] or 0.0), float(row[2] or 0.0))
        for row in purchases.all()
    }

    thresholds = await db.execute(
        select(InventoryItem.id, InventoryItem.low_threshold_g).where(
            InventoryItem.id.in_(item_ids)
        )
    )
    threshold_by_id = {row[0]: float(row[1]) for row in thresholds.all()}

    result: dict[uuid.UUID, ItemStock] = {}
    for item_id in item_ids:
        quantity = on_hand.get(item_id, 0.0)
        average = averages.get(item_id)
        result[item_id] = ItemStock(
            on_hand_g=round(quantity, 2),
            average_cost_per_kg=average,
            stock_value=cost_of(quantity, average),
            is_low=quantity <= threshold_by_id.get(item_id, 0.0),
        )
    return result


async def average_cost_per_kg(db: AsyncSession, item_id: uuid.UUID) -> float | None:
    stock = await item_stock(db, [item_id])
    return stock[item_id].average_cost_per_kg


async def consume_for_bake(db: AsyncSession, bake: Bake) -> ConsumptionResult:
    """Draw a completed bake's flour from stock and cost it.

    Only flours are consumed. Salt and inclusions are usually a rounding error
    against flour, and guessing which item a recipe meant by "seeds" would
    produce a confidently wrong number.
    """
    if bake.inventory_consumed_at is not None:
        return ConsumptionResult(skipped_reason="inventory already consumed for this bake")
    if not bake.total_flour_g:
        return ConsumptionResult(skipped_reason="bake has no total_flour_g to draw against")
    if not bake.flour_blend:
        return ConsumptionResult(
            skipped_reason="bake has no flour_blend, so flour cannot be attributed to items"
        )

    wanted = split_blend(bake.flour_blend, bake.total_flour_g)

    rows = await db.execute(
        select(InventoryItem).where(
            InventoryItem.user_id == bake.user_id,
            InventoryItem.kind == ItemKind.flour,
            InventoryItem.deleted_at.is_(None),
        )
    )
    by_name = {item.name.strip().lower(): item for item in rows.scalars().all()}

    result = ConsumptionResult()
    now = datetime.now(UTC)
    total_cost = 0.0
    costed_everything = True

    for name, grams in wanted.items():
        item = by_name.get(name.strip().lower())
        if item is None:
            result.unmatched.append(name)
            costed_everything = False
            continue

        unit_cost = await average_cost_per_kg(db, item.id)
        line_cost = cost_of(grams, unit_cost)
        if line_cost is None:
            costed_everything = False
        else:
            total_cost += line_cost

        db.add(
            InventoryTransaction(
                item_id=item.id,
                kind=TransactionKind.consume,
                delta_g=-grams,
                unit_cost_per_kg=unit_cost,
                occurred_at=now,
                bake_id=bake.id,
                note=f"bake: {bake.title}"[:200],
            )
        )
        result.consumed.append(
            ConsumedLine(item_name=item.name, grams=round(grams, 2), cost=line_cost)
        )

    if result.consumed:
        bake.inventory_consumed_at = now
        # Only claim a cost when every gram was accounted for; a partial figure
        # reads as the real cost and is not.
        if costed_everything:
            result.total_cost = round(total_cost, 2)
            result.cost_per_loaf = round(total_cost / max(bake.loaf_count, 1), 2)
            bake.flour_cost = result.total_cost
            bake.flour_cost_per_loaf = result.cost_per_loaf

    if not result.consumed:
        result.skipped_reason = "no inventory items matched this bake's flour blend"

    await db.flush()
    await _warn_if_low(
        db,
        bake.user_id,
        [by_name[n.strip().lower()] for n in wanted if n.strip().lower() in by_name],
    )
    return result


async def _warn_if_low(db: AsyncSession, user_id: uuid.UUID, touched: list[InventoryItem]) -> None:
    """Queue a low-stock reminder for anything this bake pushed under its threshold.

    Keyed per item, so repeatedly baking against low stock nags once rather than
    once per bake — until the item is restocked and drops below again.
    """
    if not touched:
        return

    from app.models.notification import NotificationEvent
    from app.services.notifications import cancel_prefix, schedule

    stock = await item_stock(db, [item.id for item in touched])
    for item in touched:
        state = stock[item.id]
        key = f"inventory:{item.id}:low"
        if state.is_low:
            await schedule(
                db,
                user_id=user_id,
                event=NotificationEvent.inventory_low,
                due_at=datetime.now(UTC),
                dedupe_key=key,
                payload={
                    "item_name": item.name,
                    "on_hand_g": round(state.on_hand_g),
                    "item_id": str(item.id),
                },
            )
        else:
            # Back above the line: withdraw any warning that has not gone out.
            await cancel_prefix(db, key)
