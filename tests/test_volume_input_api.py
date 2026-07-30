"""Volume and Fahrenheit on the way in.

Grams and Celsius remain the only things stored, so every test here is really
asking the same question: did the conversion happen at the edge, and did anything
non-metric survive past validation?

The temperature cases matter most. `dough_temp_c` feeds the Q10 fermentation
model, and a Fahrenheit value reaching it would not raise — it would quietly
predict a proof that is hours wrong.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration


async def _auth(client: AsyncClient, outbox: list[tuple[str, str, str]]) -> dict[str, str]:
    headers, _ = await register_user(client, outbox)
    return headers


# --- temperature ------------------------------------------------------------


async def test_a_proof_can_be_started_in_fahrenheit(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/proofing/sessions",
        headers=headers,
        json={"stage": "bulk", "dough_temp_f": 75.2, "ambient_temp_f": 68.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Stored in Celsius. Nothing downstream ever sees Fahrenheit.
    assert body["dough_temp_c"] == pytest.approx(24.0)
    assert body["ambient_temp_c"] == pytest.approx(20.0)
    assert "dough_temp_f" not in body


async def test_fahrenheit_and_celsius_predict_the_same_proof(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """The whole point of normalising at the edge: identical inputs, identical maths."""
    headers = await _auth(client, outbox)
    in_c = await client.post(
        "/api/v1/proofing/estimate", headers=headers, json={"stage": "bulk", "dough_temp_c": 24}
    )
    started_f = await client.post(
        "/api/v1/proofing/sessions",
        headers=headers,
        json={"stage": "bulk", "dough_temp_f": 75.2},
    )
    assert in_c.status_code == 200, in_c.text
    assert started_f.status_code == 201, started_f.text
    assert started_f.json()["dough_temp_c"] == pytest.approx(24.0)


async def test_giving_both_scales_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/proofing/sessions",
        headers=await _auth(client, outbox),
        json={"stage": "bulk", "dough_temp_c": 24, "dough_temp_f": 75.2},
    )
    assert resp.status_code == 422
    assert "not both" in resp.text


async def test_giving_neither_scale_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/proofing/sessions", headers=await _auth(client, outbox), json={"stage": "bulk"}
    )
    assert resp.status_code == 422
    assert "required" in resp.text


async def test_a_fahrenheit_value_in_the_celsius_field_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """The trap this design exists to close.

    A baker who types 75 meaning Fahrenheit must get an error, not a dough the
    model believes is at 75 degrees Celsius.
    """
    resp = await client.post(
        "/api/v1/proofing/sessions",
        headers=await _auth(client, outbox),
        json={"stage": "bulk", "dough_temp_c": 75},
    )
    assert resp.status_code == 422


async def test_fahrenheit_bounds_are_the_celsius_bounds_converted(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    # 0-45 C is 32-113 F. Either end is fine; past it is not.
    for value, ok in [(32.0, True), (113.0, True), (31.0, False), (250.0, False)]:
        resp = await client.post(
            "/api/v1/proofing/sessions",
            headers=headers,
            json={"stage": "bulk", "dough_temp_f": value},
        )
        assert (resp.status_code == 201) is ok, f"{value} F: {resp.status_code}"


async def test_a_check_in_can_report_fahrenheit(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    session = await client.post(
        "/api/v1/proofing/sessions", headers=headers, json={"stage": "bulk", "dough_temp_c": 24}
    )
    resp = await client.post(
        f"/api/v1/proofing/sessions/{session.json()['id']}/checks",
        headers=headers,
        json={"rise_pct": 30, "dough_temp_f": 77.0},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["dough_temp_c"] == pytest.approx(25.0)


# --- recipes entered as quantities ------------------------------------------


async def test_a_recipe_can_be_entered_as_amounts(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """Cups in, baker's percentages out.

    500 g of flour (at 120 g/cup) with 350 g of water is 70% hydration, and the
    baker never had to work that out.
    """
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "name": "Cups recipe",
            "default_dough_weight_g": 1000,
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "amount": 4, "unit": "cup"},
                {"name": "water", "kind": "liquid", "amount": 1.5, "unit": "cup"},
                {"name": "table salt", "kind": "salt", "amount": 2, "unit": "tsp"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    by_name = {line["name"]: line for line in resp.json()["ingredients"]}

    # Flour is the 100% reference by definition.
    assert by_name["bread flour"]["percentage"] == pytest.approx(100.0)
    # 1.5 cups of water is 354.9 g against 480 g of flour.
    assert by_name["water"]["percentage"] == pytest.approx(73.9, abs=0.5)
    # 2 tsp of table salt is 12 g, a shade over 2%.
    assert by_name["table salt"]["percentage"] == pytest.approx(2.5, abs=0.3)


async def test_amounts_and_percentages_cannot_be_mixed(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """A mixed recipe has no single sensible reading, so it is refused."""
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Mixed",
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "amount": 4, "unit": "cup"},
                {"name": "water", "kind": "liquid", "percentage": 70},
            ],
        },
    )
    assert resp.status_code == 422
    assert "not a mix" in resp.text


async def test_an_amount_needs_its_unit(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "No unit",
            "ingredients": [{"name": "bread flour", "kind": "flour", "amount": 4}],
        },
    )
    assert resp.status_code == 422
    assert "together" in resp.text


async def test_neither_percentage_nor_amount_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={"name": "Empty line", "ingredients": [{"name": "flour", "kind": "flour"}]},
    )
    assert resp.status_code == 422


async def test_a_recipe_of_amounts_still_needs_flour(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """Baker's percentage is relative to flour, so without flour there is no scale."""
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Flourless",
            "ingredients": [{"name": "water", "kind": "liquid", "amount": 1, "unit": "cup"}],
        },
    )
    assert resp.status_code == 422
    assert "flour" in resp.text


async def test_a_cup_of_starter_is_refused_on_the_way_in(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """On a write there is nothing to fall back to, so this is a 422 that names it.

    Read paths render starter in ounces instead; storing a wrong number is a
    different kind of harm from displaying an imprecise one.
    """
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Starter by volume",
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "amount": 4, "unit": "cup"},
                {"name": "levain", "kind": "starter", "amount": 1, "unit": "cup"},
            ],
        },
    )
    assert resp.status_code == 422
    assert "gas" in resp.text


async def test_an_unnamed_salt_by_volume_is_refused_on_the_way_in(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Vague salt",
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "amount": 4, "unit": "cup"},
                {"name": "salt", "kind": "salt", "amount": 2, "unit": "tsp"},
            ],
        },
    )
    assert resp.status_code == 422
    assert "2.25" in resp.text


async def test_an_ingredient_cannot_be_measured_in_degrees(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Degrees",
            "ingredients": [{"name": "bread flour", "kind": "flour", "amount": 4, "unit": "c"}],
        },
    )
    assert resp.status_code == 422
    assert "degrees" in resp.text


async def test_percentage_entry_still_works_untouched(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """The native form must be unaffected by any of this."""
    resp = await client.post(
        "/api/v1/recipes",
        headers=await _auth(client, outbox),
        json={
            "name": "Percentages",
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "percentage": 100},
                {"name": "water", "kind": "liquid", "percentage": 70},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ingredients"][0]["percentage"] == 100.0


async def test_an_override_changes_how_amounts_convert(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """A baker's own density must apply on the way in, not only on the way out."""
    headers = await _auth(client, outbox)
    await client.put(
        "/api/v1/measurements/ingredients/bread-flour/override",
        headers=headers,
        json={"grams_per_cup": 145.0},
    )
    resp = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "name": "Scooped flour",
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "amount": 4, "unit": "cup"},
                {"name": "water", "kind": "liquid", "amount": 2, "unit": "cup"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    water = next(i for i in resp.json()["ingredients"] if i["name"] == "water")
    # 2 cups water (473 g) against 4 cups of *scooped* flour (580 g) is 81.6%.
    # At the catalogue's 120 g/cup it would have been 98.6%.
    assert water["percentage"] == pytest.approx(81.6, abs=1.0)


# --- inventory in volume ----------------------------------------------------


async def _flour_item(client: AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post(
        "/api/v1/inventory/items",
        headers=headers,
        json={"name": "bread flour", "kind": "flour", "low_threshold_g": 500},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def test_stock_can_be_added_in_cups(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item_id = await _flour_item(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity": 10, "unit": "cup", "unit_cost_per_kg": 2.0},
    )
    assert resp.status_code == 201, resp.text

    listing = await client.get("/api/v1/inventory/items", headers=headers)
    # 10 cups of bread flour at 120 g/cup.
    assert listing.json()[0]["on_hand_g"] == pytest.approx(1200.0)


async def test_stock_can_be_added_in_pounds(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """Mass needs no density, so this is exact whatever the ingredient."""
    headers = await _auth(client, outbox)
    item_id = await _flour_item(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity": 5, "unit": "lb", "unit_cost_per_kg": 2.0},
    )
    assert resp.status_code == 201, resp.text

    listing = await client.get("/api/v1/inventory/items", headers=headers)
    assert listing.json()[0]["on_hand_g"] == pytest.approx(2267.96, abs=0.01)


async def test_consuming_in_volume_subtracts(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item_id = await _flour_item(client, headers)
    await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity_g": 2000, "unit_cost_per_kg": 2.0},
    )
    resp = await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={"kind": "consume", "quantity": 4, "unit": "cup"},
    )
    assert resp.status_code == 201, resp.text

    listing = await client.get("/api/v1/inventory/items", headers=headers)
    assert listing.json()[0]["on_hand_g"] == pytest.approx(2000 - 480, abs=0.5)


async def test_grams_and_volume_together_are_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item_id = await _flour_item(client, headers)
    resp = await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={
            "kind": "purchase",
            "quantity_g": 1000,
            "quantity": 4,
            "unit": "cup",
            "unit_cost_per_kg": 2.0,
        },
    )
    assert resp.status_code == 422
    assert "either" in resp.text


async def test_neither_grams_nor_volume_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item_id = await _flour_item(client, headers)
    resp = await client.post(
        f"/api/v1/inventory/items/{item_id}/transactions",
        headers=headers,
        json={"kind": "purchase", "unit_cost_per_kg": 2.0},
    )
    assert resp.status_code == 422


async def test_salt_stock_cannot_be_added_by_volume(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item = await client.post(
        "/api/v1/inventory/items",
        headers=headers,
        json={"name": "salt", "kind": "salt", "low_threshold_g": 100},
    )
    resp = await client.post(
        f"/api/v1/inventory/items/{item.json()['id']}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity": 2, "unit": "cup", "unit_cost_per_kg": 1.0},
    )
    assert resp.status_code == 422
    assert "2.25" in resp.text


async def test_naming_the_salt_lets_it_be_added_by_volume(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """The item's name resolves the density, so a specific salt converts."""
    headers = await _auth(client, outbox)
    item = await client.post(
        "/api/v1/inventory/items",
        headers=headers,
        json={"name": "diamond crystal", "kind": "salt", "low_threshold_g": 100},
    )
    resp = await client.post(
        f"/api/v1/inventory/items/{item.json()['id']}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity": 2, "unit": "cup", "unit_cost_per_kg": 1.0},
    )
    assert resp.status_code == 201, resp.text
    listing = await client.get("/api/v1/inventory/items", headers=headers)
    assert listing.json()[0]["on_hand_g"] == pytest.approx(256.0)
