"""Inventory endpoints and bake costing against live Postgres."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]


async def create_item(client: AsyncClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    body = {"name": "bread flour", "kind": "flour", "low_threshold_g": 1000} | overrides
    resp = await client.post("/api/v1/inventory/items", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def purchase(
    client: AsyncClient, headers: Headers, item_id: str, grams: float, cost_per_kg: float
) -> Any:
    return await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        json={"kind": "purchase", "quantity_g": grams, "unit_cost_per_kg": cost_per_kg},
        headers=headers,
    )


async def get_item(client: AsyncClient, headers: Headers, item_id: str) -> dict[str, Any]:
    resp = await client.get(f"/api/v1/inventory/items/{item_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


# --- items and the ledger -----------------------------------------------------


async def test_new_item_starts_empty(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)
    assert item["on_hand_g"] == 0.0
    assert item["average_cost_per_kg"] is None
    assert item["stock_value"] is None
    assert item["is_low"] is True


async def test_on_hand_is_the_sum_of_the_ledger(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)

    assert (await purchase(client, headers, item["id"], 5000, 2.0)).status_code == 201
    assert (await purchase(client, headers, item["id"], 3000, 2.0)).status_code == 201
    await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "consume", "quantity_g": 1200},
        headers=headers,
    )

    assert (await get_item(client, headers, item["id"]))["on_hand_g"] == 6800.0


async def test_adjustment_can_go_either_way(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)
    await purchase(client, headers, item["id"], 2000, 1.0)

    await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "adjust", "quantity_g": 150, "decrease": True, "note": "spilled"},
        headers=headers,
    )
    assert (await get_item(client, headers, item["id"]))["on_hand_g"] == 1850.0

    await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "adjust", "quantity_g": 50, "note": "recount"},
        headers=headers,
    )
    assert (await get_item(client, headers, item["id"]))["on_hand_g"] == 1900.0


async def test_purchase_requires_a_price(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)
    resp = await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "purchase", "quantity_g": 1000},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_consumption_price_cannot_be_dictated(client: AsyncClient, outbox: Outbox) -> None:
    """Consumption is valued from the ledger, not from whatever the client claims."""
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)
    resp = await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "consume", "quantity_g": 500, "unit_cost_per_kg": 0.01},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_quantities_are_always_positive_magnitudes(
    client: AsyncClient, outbox: Outbox
) -> None:
    """A negative "consume" must not become a stock increase."""
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)
    resp = await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "consume", "quantity_g": -5000},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_duplicate_item_names_are_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await create_item(client, headers)
    dupe = await client.post(
        "/api/v1/inventory/items", json={"name": "bread flour"}, headers=headers
    )
    assert dupe.status_code == 409


async def test_inventory_is_isolated_between_users(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    item = await create_item(client, owner)
    iid = item["id"]

    assert (await client.get(f"/api/v1/inventory/items/{iid}", headers=intruder)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/inventory/items/{iid}", json={"name": "mine"}, headers=intruder
        )
    ).status_code == 404
    assert (await purchase(client, intruder, iid, 1000, 1.0)).status_code == 404
    assert (await client.get("/api/v1/inventory/items", headers=intruder)).json() == []


# --- valuation ----------------------------------------------------------------


async def test_average_cost_is_weighted_across_purchases(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)

    await purchase(client, headers, item["id"], 9000, 1.0)
    await purchase(client, headers, item["id"], 1000, 11.0)

    stock = await get_item(client, headers, item["id"])
    assert stock["average_cost_per_kg"] == 2.0
    assert stock["stock_value"] == 20.0  # 10 kg at £2


async def test_a_later_cheaper_purchase_does_not_rewrite_past_costs(
    client: AsyncClient, outbox: Outbox
) -> None:
    """The whole reason cost is stamped onto the consume row."""
    headers, _ = await register_user(client, outbox)
    item = await create_item(client, headers)

    await purchase(client, headers, item["id"], 1000, 10.0)
    await client.post(
        f"/api/v1/inventory/items/{item['id']}/transactions",
        json={"kind": "consume", "quantity_g": 500},
        headers=headers,
    )
    await purchase(client, headers, item["id"], 9000, 1.0)

    ledger = (
        await client.get(f"/api/v1/inventory/items/{item['id']}/transactions", headers=headers)
    ).json()
    consumed = next(t for t in ledger if t["kind"] == "consume")
    assert consumed["unit_cost_per_kg"] == 10.0, "valued at what it cost then, not now"


# --- low stock ----------------------------------------------------------------


async def test_low_stock_lists_only_what_is_low(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    plenty = await create_item(client, headers, name="bread flour", low_threshold_g=1000)
    scarce = await create_item(client, headers, name="rye", low_threshold_g=1000)

    await purchase(client, headers, plenty["id"], 5000, 2.0)
    await purchase(client, headers, scarce["id"], 400, 3.0)

    low = (await client.get("/api/v1/inventory/low-stock", headers=headers)).json()
    assert [i["name"] for i in low] == ["rye"]


async def test_low_stock_is_ordered_emptiest_first(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    a = await create_item(client, headers, name="rye", low_threshold_g=5000)
    b = await create_item(client, headers, name="spelt", low_threshold_g=5000)
    await purchase(client, headers, a["id"], 900, 1.0)
    await purchase(client, headers, b["id"], 200, 1.0)

    low = (await client.get("/api/v1/inventory/low-stock", headers=headers)).json()
    assert [i["name"] for i in low] == ["spelt", "rye"]


async def test_low_stock_route_is_not_shadowed(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    assert (await client.get("/api/v1/inventory/low-stock", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/inventory/cost-report", headers=headers)).status_code == 200


# --- bake consumption ---------------------------------------------------------


async def bake_with_blend(
    client: AsyncClient, headers: Headers, **overrides: Any
) -> dict[str, Any]:
    body = {
        "title": "Costed loaf",
        "total_flour_g": 1000,
        "loaf_count": 2,
        "flour_blend": {"bread flour": 80, "rye": 20},
    } | overrides
    resp = await client.post("/api/v1/bakes", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def test_completing_a_bake_draws_stock_and_costs_it(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    rye = await create_item(client, headers, name="rye")
    await purchase(client, headers, bread["id"], 10_000, 2.0)  # £2/kg
    await purchase(client, headers, rye["id"], 5_000, 4.0)  # £4/kg

    bake = await bake_with_blend(client, headers)
    done = await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    assert done.status_code == 200, done.text
    body = done.json()

    # 800 g at £2/kg = £1.60, 200 g at £4/kg = £0.80.
    assert body["inventory"]["total_cost"] == pytest.approx(2.40)
    assert body["inventory"]["cost_per_loaf"] == pytest.approx(1.20)
    assert body["flour_cost"] == pytest.approx(2.40)
    assert body["flour_cost_per_loaf"] == pytest.approx(1.20)
    assert body["inventory"]["unmatched"] == []

    assert (await get_item(client, headers, bread["id"]))["on_hand_g"] == 9200.0
    assert (await get_item(client, headers, rye["id"]))["on_hand_g"] == 4800.0


async def test_consumption_is_traceable_to_the_bake(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    await create_item(client, headers, name="rye")
    await purchase(client, headers, bread["id"], 10_000, 2.0)

    bake = await bake_with_blend(client, headers)
    await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)

    ledger = (
        await client.get(f"/api/v1/inventory/items/{bread['id']}/transactions", headers=headers)
    ).json()
    consumed = next(t for t in ledger if t["kind"] == "consume")
    assert consumed["bake_id"] == bake["id"]
    assert consumed["delta_g"] == -800.0


async def test_completion_can_opt_out_of_consuming_stock(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    await purchase(client, headers, bread["id"], 10_000, 2.0)

    bake = await bake_with_blend(client, headers)
    done = await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"consume_inventory": False},
        headers=headers,
    )
    assert done.json()["inventory"] is None
    assert (await get_item(client, headers, bread["id"]))["on_hand_g"] == 10_000.0


async def test_unmatched_flours_are_reported_not_silently_dropped(
    client: AsyncClient, outbox: Outbox
) -> None:
    """A cost that quietly excludes 20% of the flour would read as the real cost."""
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    await purchase(client, headers, bread["id"], 10_000, 2.0)

    bake = await bake_with_blend(client, headers)  # blend also names "rye"
    body = (
        await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    ).json()

    assert body["inventory"]["unmatched"] == ["rye"]
    assert body["inventory"]["total_cost"] is None
    assert body["flour_cost"] is None


async def test_unpriced_stock_yields_no_cost(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    rye = await create_item(client, headers, name="rye")
    # Stock arrives by adjustment, so nothing was ever priced.
    for item in (bread, rye):
        await client.post(
            f"/api/v1/inventory/items/{item['id']}/transactions",
            json={"kind": "adjust", "quantity_g": 5000, "note": "opening count"},
            headers=headers,
        )

    bake = await bake_with_blend(client, headers)
    body = (
        await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    ).json()

    assert body["inventory"]["total_cost"] is None
    assert (await get_item(client, headers, bread["id"]))["on_hand_g"] == 4200.0


async def test_a_bake_without_a_blend_is_skipped_with_a_reason(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await bake_with_blend(client, headers, flour_blend=None)
    body = (
        await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    ).json()
    assert "flour_blend" in body["inventory"]["skipped_reason"]


async def test_stock_is_never_double_consumed(client: AsyncClient, outbox: Outbox) -> None:
    """Completion is guarded, but the marker is what makes replay safe."""
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    rye = await create_item(client, headers, name="rye")
    await purchase(client, headers, bread["id"], 10_000, 2.0)
    await purchase(client, headers, rye["id"], 5_000, 4.0)

    bake = await bake_with_blend(client, headers)
    await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    again = await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    assert again.status_code == 409

    assert (await get_item(client, headers, bread["id"]))["on_hand_g"] == 9200.0


async def test_stock_may_go_negative_rather_than_block_a_bake(
    client: AsyncClient, outbox: Outbox
) -> None:
    """The bread was baked whether or not the ledger agrees; report it, don't refuse it."""
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    rye = await create_item(client, headers, name="rye")
    await purchase(client, headers, bread["id"], 100, 2.0)
    await purchase(client, headers, rye["id"], 100, 4.0)

    bake = await bake_with_blend(client, headers)
    done = await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    assert done.status_code == 200
    assert (await get_item(client, headers, bread["id"]))["on_hand_g"] == -700.0


# --- cost report --------------------------------------------------------------


async def test_cost_report_summarises_spend_and_loaf_cost(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bread = await create_item(client, headers, name="bread flour")
    rye = await create_item(client, headers, name="rye")
    await purchase(client, headers, bread["id"], 10_000, 2.0)  # £20
    await purchase(client, headers, rye["id"], 5_000, 4.0)  # £20

    bake = await bake_with_blend(client, headers)
    await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)

    report = (await client.get("/api/v1/inventory/cost-report", headers=headers)).json()
    assert report["total_purchased_cost"] == pytest.approx(40.0)
    assert report["total_purchased_g"] == 15_000.0
    assert report["total_consumed_cost"] == pytest.approx(2.40)
    assert report["total_consumed_g"] == 1000.0
    assert report["bakes_costed"] == 1
    assert report["average_cost_per_bake"] == pytest.approx(2.40)
    assert report["average_cost_per_loaf"] == pytest.approx(1.20)
    assert report["current_stock_value"] == pytest.approx(40.0 - 2.40)


async def test_empty_cost_report_is_zeroed_not_null(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    report = (await client.get("/api/v1/inventory/cost-report", headers=headers)).json()
    assert report["total_purchased_cost"] == 0.0
    assert report["bakes_costed"] == 0
    assert report["average_cost_per_loaf"] is None
