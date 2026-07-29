"""Inventory: stock items, the transaction ledger, low stock and cost reporting."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.bake import Bake
from app.models.inventory import InventoryItem, InventoryTransaction, TransactionKind
from app.schemas.inventory import (
    CostReport,
    ItemCreate,
    ItemResponse,
    ItemUpdate,
    TransactionCreate,
    TransactionResponse,
)
from app.services import inventory as inventory_service
from app.services.starters import CLOCK_SKEW_ALLOWANCE, MAX_BACKDATE

router = APIRouter(prefix="/inventory", tags=["inventory"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _get_owned(item_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> InventoryItem:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.user_id == user_id,
            InventoryItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


async def _to_responses(db: AsyncSession, items: list[InventoryItem]) -> list[ItemResponse]:
    stock = await inventory_service.item_stock(db, [i.id for i in items])
    return [
        ItemResponse(
            **{
                field: getattr(item, field)
                for field in ("id", "name", "kind", "low_threshold_g", "notes", "created_at")
            },
            **asdict(stock[item.id]),
        )
        for item in items
    ]


# --- items ------------------------------------------------------------------


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, user: VerifiedUser, db: SessionDep) -> ItemResponse:
    item = InventoryItem(user_id=user.id, **payload.model_dump())
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an inventory item with that name",
        ) from exc
    return (await _to_responses(db, [item]))[0]


@router.get("/items", response_model=list[ItemResponse])
async def list_items(user: CurrentUser, db: SessionDep) -> list[ItemResponse]:
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None))
        .order_by(InventoryItem.name)
    )
    return await _to_responses(db, list(result.scalars().all()))


@router.get("/low-stock", response_model=list[ItemResponse])
async def low_stock(user: CurrentUser, db: SessionDep) -> list[ItemResponse]:
    """Items at or below their threshold, emptiest first."""
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
        )
    )
    responses = await _to_responses(db, list(result.scalars().all()))
    return sorted((r for r in responses if r.is_low), key=lambda r: r.on_hand_g)


@router.get("/cost-report", response_model=CostReport)
async def cost_report(
    user: CurrentUser,
    db: SessionDep,
    from_date: Annotated[datetime | None, Query()] = None,
    to_date: Annotated[datetime | None, Query()] = None,
) -> CostReport:
    """What was bought, what was used, and what a loaf actually costs."""
    owned_items = select(InventoryItem.id).where(
        InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
    )

    conditions: list[Any] = [InventoryTransaction.item_id.in_(owned_items)]
    if from_date is not None:
        conditions.append(InventoryTransaction.occurred_at >= from_date)
    if to_date is not None:
        conditions.append(InventoryTransaction.occurred_at <= to_date)

    cost_expression = (
        InventoryTransaction.delta_g
        / inventory_service.GRAMS_PER_KG
        * func.coalesce(InventoryTransaction.unit_cost_per_kg, 0.0)
    )
    totals = await db.execute(
        select(
            InventoryTransaction.kind,
            func.sum(InventoryTransaction.delta_g),
            func.sum(cost_expression),
        )
        .where(*conditions)
        .group_by(InventoryTransaction.kind)
    )
    by_kind = {row[0]: (float(row[1] or 0.0), float(row[2] or 0.0)) for row in totals.all()}
    purchased_g, purchased_cost = by_kind.get(TransactionKind.purchase, (0.0, 0.0))
    consumed_g, consumed_cost = by_kind.get(TransactionKind.consume, (0.0, 0.0))

    bake_conditions: list[Any] = [
        Bake.user_id == user.id,
        Bake.deleted_at.is_(None),
        Bake.flour_cost.is_not(None),
    ]
    if from_date is not None:
        bake_conditions.append(Bake.started_at >= from_date)
    if to_date is not None:
        bake_conditions.append(Bake.started_at <= to_date)

    bake_totals = await db.execute(
        select(func.count(), func.sum(Bake.flour_cost), func.sum(Bake.loaf_count)).where(
            *bake_conditions
        )
    )
    bake_count, bake_cost, loaves = bake_totals.one()
    bake_count = int(bake_count or 0)
    bake_cost = float(bake_cost or 0.0)
    loaves = int(loaves or 0)

    items = await db.execute(owned_items)
    stock = await inventory_service.item_stock(db, [row[0] for row in items.all()])

    return CostReport(
        from_date=from_date,
        to_date=to_date,
        total_purchased_cost=round(purchased_cost, 2),
        total_purchased_g=round(purchased_g, 2),
        # Consumption deltas are negative; report the magnitude spent.
        total_consumed_cost=round(abs(consumed_cost), 2),
        total_consumed_g=round(abs(consumed_g), 2),
        current_stock_value=round(sum(s.stock_value or 0.0 for s in stock.values()), 2),
        bakes_costed=bake_count,
        average_cost_per_bake=round(bake_cost / bake_count, 2) if bake_count else None,
        average_cost_per_loaf=round(bake_cost / loaves, 2) if loaves else None,
    )


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> ItemResponse:
    item = await _get_owned(item_id, user.id, db)
    return (await _to_responses(db, [item]))[0]


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: uuid.UUID, payload: ItemUpdate, user: VerifiedUser, db: SessionDep
) -> ItemResponse:
    item = await _get_owned(item_id, user.id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an inventory item with that name",
        ) from exc
    return (await _to_responses(db, [item]))[0]


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    """Soft delete — the ledger stays, so past bake costs remain explicable."""
    item = await _get_owned(item_id, user.id, db)
    item.deleted_at = datetime.now(UTC)


# --- ledger -----------------------------------------------------------------


@router.post(
    "/items/{item_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_transaction(
    item_id: uuid.UUID, payload: TransactionCreate, user: VerifiedUser, db: SessionDep
) -> TransactionResponse:
    item = await _get_owned(item_id, user.id, db)

    now = datetime.now(UTC)
    occurred_at = payload.occurred_at or now
    if occurred_at > now + CLOCK_SKEW_ALLOWANCE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="occurred_at cannot be in the future",
        )
    if occurred_at < now - MAX_BACKDATE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"occurred_at cannot be more than {MAX_BACKDATE.days} days in the past",
        )

    if payload.kind is TransactionKind.purchase:
        delta = payload.quantity_g
        unit_cost = payload.unit_cost_per_kg
    elif payload.kind is TransactionKind.consume:
        delta = -payload.quantity_g
        # Valued at the average paid, stamped now so later purchases cannot
        # retroactively change what this cost.
        unit_cost = await inventory_service.average_cost_per_kg(db, item.id)
    else:
        delta = -payload.quantity_g if payload.decrease else payload.quantity_g
        unit_cost = None

    transaction = InventoryTransaction(
        item_id=item.id,
        kind=payload.kind,
        delta_g=delta,
        unit_cost_per_kg=unit_cost,
        occurred_at=occurred_at,
        note=payload.note,
    )
    db.add(transaction)
    await db.flush()
    return TransactionResponse.model_validate(transaction)


@router.get("/items/{item_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    item_id: uuid.UUID,
    user: CurrentUser,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionResponse]:
    item = await _get_owned(item_id, user.id, db)
    result = await db.execute(
        select(InventoryTransaction)
        .where(InventoryTransaction.item_id == item.id)
        .order_by(InventoryTransaction.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [TransactionResponse.model_validate(t) for t in result.scalars().all()]
