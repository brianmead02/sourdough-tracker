"""Request/response models for inventory."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.inventory import ItemKind, TransactionKind

Grams = Annotated[float, Field(gt=0, le=1_000_000)]
CostPerKg = Annotated[float, Field(ge=0, le=10_000)]


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: ItemKind = ItemKind.flour
    low_threshold_g: float = Field(default=1000.0, ge=0, le=1_000_000)
    notes: str | None = Field(default=None, max_length=500)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: ItemKind | None = None
    low_threshold_g: float | None = Field(default=None, ge=0, le=1_000_000)
    notes: str | None = Field(default=None, max_length=500)


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: ItemKind
    low_threshold_g: float
    notes: str | None
    created_at: datetime
    # Derived from the ledger, never stored.
    on_hand_g: float
    average_cost_per_kg: float | None
    stock_value: float | None
    is_low: bool


class TransactionCreate(BaseModel):
    kind: TransactionKind
    # Always a positive magnitude; the sign is decided by `kind`, so a client
    # cannot accidentally add stock by "consuming" a negative amount.
    quantity_g: Grams
    unit_cost_per_kg: CostPerKg | None = None
    occurred_at: datetime | None = None
    note: str | None = Field(default=None, max_length=200)
    # Only meaningful for `adjust`: a stock count can go either way.
    decrease: bool = False

    @model_validator(mode="after")
    def _cost_belongs_to_purchases(self) -> "TransactionCreate":
        if self.kind is TransactionKind.purchase and self.unit_cost_per_kg is None:
            raise ValueError("a purchase needs unit_cost_per_kg, or the stock cannot be valued")
        if self.kind is TransactionKind.consume and self.unit_cost_per_kg is not None:
            raise ValueError(
                "consumption is valued from the weighted average, not from a supplied cost"
            )
        return self


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    kind: TransactionKind
    delta_g: float
    unit_cost_per_kg: float | None
    occurred_at: datetime
    note: str | None
    bake_id: uuid.UUID | None


class ConsumedLineResponse(BaseModel):
    item_name: str
    grams: float
    cost: float | None


class ConsumptionResponse(BaseModel):
    consumed: list[ConsumedLineResponse]
    unmatched: list[str]
    total_cost: float | None
    cost_per_loaf: float | None
    skipped_reason: str | None


class CostReport(BaseModel):
    from_date: datetime | None
    to_date: datetime | None
    total_purchased_cost: float
    total_purchased_g: float
    total_consumed_cost: float
    total_consumed_g: float
    current_stock_value: float
    bakes_costed: int
    average_cost_per_bake: float | None
    average_cost_per_loaf: float | None
