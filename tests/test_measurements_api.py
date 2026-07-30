"""Integration tests for the measurements API and the `display` sibling fields.

The behaviours worth defending here are the ones a client would otherwise have to
guess at:

* a refusal comes back **inside** a 200 batch, per item, so one bad line does not
  fail the other forty
* `display` is a sibling — every pre-existing gram field is still present and
  unchanged, so no client breaks
* `?units=` beats the profile, because a shared recipe should read in the units
  of whoever is looking at it
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration


async def _auth(client: AsyncClient, outbox: list[tuple[str, str, str]]) -> dict[str, str]:
    headers, _ = await register_user(client, outbox)
    return headers


# --- unit catalogue ---------------------------------------------------------


async def test_unit_catalogue_lists_exact_ratios(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/measurements/units")
    assert resp.status_code == 200
    body = resp.json()
    by_unit = {u["unit"]: u for u in body["units"]}

    assert by_unit["oz"]["grams"] == pytest.approx(28.349523125)
    assert by_unit["lb"]["grams"] == pytest.approx(453.59237)
    assert by_unit["cup"]["millilitres"] == pytest.approx(236.5882365)
    # Volume units have no gram figure because they genuinely do not have one.
    assert by_unit["cup"]["grams"] is None
    assert by_unit["c"]["grams"] is None and by_unit["c"]["millilitres"] is None
    assert "cocoa" in body["note"]


async def test_unit_catalogue_needs_no_auth(client: AsyncClient) -> None:
    """It is a table of physical constants. Gating it would be theatre."""
    assert (await client.get("/api/v1/measurements/units")).status_code == 200


# --- ingredient catalogue ---------------------------------------------------


async def test_ingredient_catalogue_is_seeded_and_filterable(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)

    everything = await client.get("/api/v1/measurements/ingredients", headers=headers)
    assert everything.status_code == 200
    assert len(everything.json()) >= 30

    flours = await client.get("/api/v1/measurements/ingredients?kind=flour", headers=headers)
    assert flours.status_code == 200
    assert flours.json()
    assert all(row["kind"] == "flour" for row in flours.json())

    by_slug = {row["slug"]: row for row in everything.json()}
    assert by_slug["bread-flour"]["grams_per_cup"] == 120
    assert by_slug["water"]["grams_per_cup"] == pytest.approx(236.588, abs=0.01)
    # A named salt converts; it is the bare word "salt" that refuses, during
    # resolution rather than in the catalogue.
    assert by_slug["table-salt"]["volume_allowed"] is True
    assert by_slug["starter"]["volume_allowed"] is False
    # Provenance travels with the number so it can be checked, not argued about.
    assert all(row["source"] for row in everything.json())


# --- conversion -------------------------------------------------------------


async def test_mass_conversion_is_exact_and_needs_no_ingredient(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={"items": [{"value": 1, "from": "lb", "to": "g"}]},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["value"] == pytest.approx(453.59237)
    assert result["basis"] == "exact"
    assert result["approximate"] is False


async def test_volume_to_mass_uses_the_named_ingredient(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={
            "items": [
                {"value": 1, "from": "cup", "to": "g", "ingredient": "bread flour"},
                {"value": 1, "from": "cup", "to": "g", "ingredient": "water"},
            ]
        },
    )
    first, second = resp.json()["results"]
    assert first["value"] == pytest.approx(120.0)
    assert first["basis"] == "catalogue"
    assert first["approximate"] is True
    assert first["source_slug"] == "bread-flour"
    # The same cup, nearly twice the mass. This is why a density table exists.
    assert second["value"] == pytest.approx(236.588, abs=0.01)


async def test_temperature_converts_and_does_not_cross_families(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={
            "items": [
                {"value": 24, "from": "c", "to": "f"},
                {"value": 75.2, "from": "f", "to": "c"},
                {"value": 20, "from": "c", "to": "g"},
            ]
        },
    )
    assert resp.status_code == 200
    warm, cool, nonsense = resp.json()["results"]
    assert warm["value"] == pytest.approx(75.2)
    assert cool["value"] == pytest.approx(24.0)
    assert nonsense["value"] is None
    assert nonsense["error"]


async def test_a_refusal_is_a_result_not_a_failed_request(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """One unconvertible line must not take the batch down with it."""
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={
            "items": [
                {"value": 1, "from": "tsp", "to": "g", "ingredient": "salt", "kind": "salt"},
                {"value": 1, "from": "cup", "to": "g", "ingredient": "levain", "kind": "starter"},
                {"value": 1, "from": "cup", "to": "g", "ingredient": "bread flour"},
            ]
        },
    )
    assert resp.status_code == 200
    salt, starter, flour = resp.json()["results"]

    assert salt["value"] is None
    assert "2.25" in salt["error"]
    assert starter["value"] is None
    assert "gas" in starter["error"]
    # The good line still converted.
    assert flour["value"] == pytest.approx(120.0)


async def test_volume_to_mass_without_an_ingredient_explains_itself(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={"items": [{"value": 1, "from": "cup", "to": "g"}]},
    )
    result = resp.json()["results"][0]
    assert result["value"] is None
    assert "ingredient" in result["error"]


async def test_unmatched_name_with_a_kind_falls_back_and_flags_it(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.post(
        "/api/v1/measurements/convert",
        headers=headers,
        json={
            "items": [
                {
                    "value": 1,
                    "from": "cup",
                    "to": "g",
                    "ingredient": "unobtainium flour",
                    "kind": "flour",
                }
            ]
        },
    )
    result = resp.json()["results"][0]
    assert result["basis"] == "kind_default"
    assert result["approximate"] is True


# --- overrides --------------------------------------------------------------


async def test_an_override_changes_conversion_for_that_baker_only(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    mine = await _auth(client, outbox)
    theirs = await _auth(client, outbox)

    body = {"grams_per_cup": 96.0, "note": "my local mill, weighed three times"}
    saved = await client.put(
        "/api/v1/measurements/ingredients/rye-flour/override", headers=mine, json=body
    )
    assert saved.status_code == 200
    assert saved.json()["grams_per_cup"] == 96.0
    assert saved.json()["overridden"] is True

    payload = {"items": [{"value": 1, "from": "cup", "to": "g", "ingredient": "rye flour"}]}
    ours = await client.post("/api/v1/measurements/convert", headers=mine, json=payload)
    assert ours.json()["results"][0]["value"] == pytest.approx(96.0)
    assert ours.json()["results"][0]["basis"] == "user_override"

    unaffected = await client.post("/api/v1/measurements/convert", headers=theirs, json=payload)
    assert unaffected.json()["results"][0]["value"] == pytest.approx(106.0)
    assert unaffected.json()["results"][0]["basis"] == "catalogue"


async def test_setting_an_override_twice_is_not_an_error(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    url = "/api/v1/measurements/ingredients/spelt-flour/override"
    assert (await client.put(url, headers=headers, json={"grams_per_cup": 100})).status_code == 200
    second = await client.put(url, headers=headers, json={"grams_per_cup": 105})
    assert second.status_code == 200
    assert second.json()["grams_per_cup"] == 105


async def test_clearing_an_override_restores_the_published_value(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    url = "/api/v1/measurements/ingredients/rye-flour/override"
    await client.put(url, headers=headers, json={"grams_per_cup": 96.0})

    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.delete(url, headers=headers)).status_code == 404

    payload = {"items": [{"value": 1, "from": "cup", "to": "g", "ingredient": "rye flour"}]}
    back = await client.post("/api/v1/measurements/convert", headers=headers, json=payload)
    assert back.json()["results"][0]["value"] == pytest.approx(106.0)


async def test_an_override_cannot_be_set_on_an_ingredient_that_refuses_volume(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """No amount of careful weighing makes a peaked levain's volume meaningful."""
    headers = await _auth(client, outbox)
    resp = await client.put(
        "/api/v1/measurements/ingredients/starter/override",
        headers=headers,
        json={"grams_per_cup": 240.0},
    )
    assert resp.status_code == 409

    # A named salt is a different matter: its density is knowable, so a baker who
    # weighed their own may say so.
    allowed = await client.put(
        "/api/v1/measurements/ingredients/table-salt/override",
        headers=headers,
        json={"grams_per_cup": 292.0},
    )
    assert allowed.status_code == 200


async def test_an_override_on_an_unknown_ingredient_is_a_404(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    resp = await client.put(
        "/api/v1/measurements/ingredients/unobtainium/override",
        headers=await _auth(client, outbox),
        json={"grams_per_cup": 100.0},
    )
    assert resp.status_code == 404


async def test_an_implausible_density_is_rejected(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    for bad in (0, -5, 5000):
        resp = await client.put(
            "/api/v1/measurements/ingredients/rye-flour/override",
            headers=headers,
            json={"grams_per_cup": bad},
        )
        assert resp.status_code == 422, bad


# --- display sibling fields -------------------------------------------------


async def _recipe_with_flour(client: AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "name": "Plain white",
            "default_dough_weight_g": 1000,
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "percentage": 100},
                {"name": "water", "kind": "liquid", "percentage": 70},
                {"name": "salt", "kind": "salt", "percentage": 2},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def test_scale_adds_display_without_touching_grams(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    recipe_id = await _recipe_with_flour(client, headers)

    metric = await client.get(f"/api/v1/recipes/{recipe_id}/scale", headers=headers)
    assert metric.status_code == 200
    lines = {line["name"]: line for line in metric.json()["ingredients"]}

    # Every pre-existing field is still there and still a number.
    assert lines["bread flour"]["grams"] > 0
    assert lines["bread flour"]["percentage"] == 100
    assert metric.json()["total_dough_g"] > 0

    # Metric is the profile default and is exact.
    assert lines["bread flour"]["display"]["system"] == "metric"
    assert lines["bread flour"]["display"]["approximate"] is False
    assert lines["bread flour"]["display"]["text"].endswith(("g", "kg"))


async def test_units_query_overrides_the_profile_default(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    """A shared recipe should read in the units of whoever is looking at it."""
    headers = await _auth(client, outbox)
    recipe_id = await _recipe_with_flour(client, headers)

    us = await client.get(f"/api/v1/recipes/{recipe_id}/scale?units=us", headers=headers)
    assert us.status_code == 200
    lines = {line["name"]: line for line in us.json()["ingredients"]}

    flour = lines["bread flour"]["display"]
    assert flour["system"] == "us"
    assert "cup" in flour["text"]
    assert flour["basis"] == "catalogue"
    assert flour["approximate"] is True
    # The rendering knows how far off it is, and the number stays small.
    assert abs(flour["drift_pct"]) < 2.0
    assert flour["grams"] == pytest.approx(lines["bread flour"]["grams"], rel=0.02)

    # Salt refuses volume, so it falls back to exact mass rather than erroring.
    salt = lines["salt"]["display"]
    assert salt["approximate"] is False
    assert salt["basis"] == "exact"
    assert "cup" not in salt["text"] and "tsp" not in salt["text"]


async def test_display_respects_a_saved_override(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    await client.put(
        "/api/v1/measurements/ingredients/bread-flour/override",
        headers=headers,
        json={"grams_per_cup": 145.0},
    )
    recipe_id = await _recipe_with_flour(client, headers)

    us = await client.get(f"/api/v1/recipes/{recipe_id}/scale?units=us", headers=headers)
    flour = next(line for line in us.json()["ingredients"] if line["name"] == "bread flour")
    assert flour["display"]["basis"] == "user_override"


async def test_inventory_stock_is_rendered_in_the_requested_units(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    item = await client.post(
        "/api/v1/inventory/items",
        headers=headers,
        json={"name": "bread flour", "kind": "flour", "low_threshold_g": 500},
    )
    assert item.status_code == 201, item.text
    await client.post(
        f"/api/v1/inventory/items/{item.json()['id']}/transactions",
        headers=headers,
        json={"kind": "purchase", "quantity_g": 2000, "unit_cost_per_kg": 2.0},
    )

    listing = await client.get("/api/v1/inventory/items?units=us", headers=headers)
    assert listing.status_code == 200
    row = listing.json()[0]
    assert row["on_hand_g"] == pytest.approx(2000.0)
    assert "cup" in row["on_hand_display"]["text"]
    assert row["on_hand_display"]["basis"] == "catalogue"


async def test_suggested_feed_renders_flour_and_water_but_weighs_the_starter(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    starter = await client.post(
        "/api/v1/starters",
        headers=headers,
        json={"name": "Gerald", "flour_type": "rye flour"},
    )
    assert starter.status_code == 201, starter.text

    resp = await client.post(
        f"/api/v1/starters/{starter.json()['id']}/suggested-feed?units=us",
        headers=headers,
        json={"starter_g": 20},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["flour_g"] > 0 and body["water_g"] > 0
    assert body["flour_display"]["basis"] == "catalogue"
    assert body["water_display"]["basis"] == "catalogue"
    # Starter is refused by design and comes back as an exact mass.
    assert body["starter_display"]["approximate"] is False
    assert body["starter_display"]["basis"] == "exact"


async def test_an_unknown_units_value_is_rejected_rather_than_guessed(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    headers = await _auth(client, outbox)
    resp = await client.get("/api/v1/inventory/items?units=imperial", headers=headers)
    assert resp.status_code == 422
