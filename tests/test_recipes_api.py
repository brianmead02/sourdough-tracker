"""Recipe endpoints against live Postgres and Redis."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]

COUNTRY: dict[str, Any] = {
    "name": "Country Loaf",
    "description": "Everyday bread",
    "starter_hydration_pct": 100,
    "ingredients": [
        {"name": "bread flour", "kind": "flour", "percentage": 90},
        {"name": "whole wheat", "kind": "flour", "percentage": 10},
        {"name": "water", "kind": "liquid", "percentage": 70},
        {"name": "salt", "kind": "salt", "percentage": 2},
        {"name": "levain", "kind": "starter", "percentage": 20},
    ],
}


async def create_recipe(client: AsyncClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/recipes", json=COUNTRY | overrides, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# --- CRUD ---------------------------------------------------------------------


async def test_create_recipe_keeps_ingredient_order(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers)
    assert [i["name"] for i in recipe["ingredients"]] == [
        "bread flour",
        "whole wheat",
        "water",
        "salt",
        "levain",
    ]
    assert recipe["version"] == 1


async def test_flour_must_sum_to_100(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/recipes",
        json=COUNTRY | {"ingredients": [{"name": "flour", "kind": "flour", "percentage": 80}]},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "sum to 100" in resp.text


async def test_duplicate_name_is_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    await create_recipe(client, headers)
    dupe = await client.post("/api/v1/recipes", json=COUNTRY, headers=headers)
    assert dupe.status_code == 409


async def test_updating_ingredients_bumps_the_version(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers)

    renamed = await client.patch(
        f"/api/v1/recipes/{recipe['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert renamed.json()["version"] == 1, "metadata edits are not formula changes"

    reformulated = await client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "ingredients": [
                {"name": "bread flour", "kind": "flour", "percentage": 100},
                {"name": "water", "kind": "liquid", "percentage": 75},
                {"name": "salt", "kind": "salt", "percentage": 2},
            ]
        },
        headers=headers,
    )
    assert reformulated.json()["version"] == 2
    assert len(reformulated.json()["ingredients"]) == 3


async def test_update_rejects_a_broken_formula(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers)
    resp = await client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={"ingredients": [{"name": "flour", "kind": "flour", "percentage": 60}]},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_tags_are_normalised_and_deduplicated(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers, tags=[" Rye ", "rye", "SOURDOUGH"])
    assert recipe["tags"] == ["rye", "sourdough"]


async def test_delete_unpublishes(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers, is_public=True)
    await client.delete(f"/api/v1/recipes/{recipe['id']}", headers=headers)

    assert (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=headers)).status_code == 404
    public = await client.get("/api/v1/recipes/public", headers=headers)
    assert all(r["id"] != recipe["id"] for r in public.json())


# --- scaling ------------------------------------------------------------------


async def test_scale_defaults_to_the_recipes_own_batch_size(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers, default_dough_weight_g=1920)
    scaled = (await client.get(f"/api/v1/recipes/{recipe['id']}/scale", headers=headers)).json()
    assert scaled["total_dough_g"] == pytest.approx(1920, abs=1)


async def test_scale_reports_both_hydrations(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers)
    scaled = (
        await client.get(f"/api/v1/recipes/{recipe['id']}/scale?flour_g=1000", headers=headers)
    ).json()

    assert scaled["stated_hydration_pct"] == 70.0
    assert scaled["true_hydration_pct"] == pytest.approx(72.7, abs=0.1)
    assert scaled["total_dough_g"] == 1920.0


async def test_scale_by_loaf_count(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers)
    scaled = (
        await client.get(
            f"/api/v1/recipes/{recipe['id']}/scale?dough_weight_g=1800&loaf_count=2",
            headers=headers,
        )
    ).json()
    assert scaled["loaf_weight_g"] == pytest.approx(900, abs=1)


# --- visibility ---------------------------------------------------------------


async def test_private_recipes_are_invisible_to_others(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    other, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, owner)

    assert (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=other)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/recipes/{recipe['id']}", json={"name": "Mine now"}, headers=other
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/recipes/{recipe['id']}", headers=other)
    ).status_code == 404


async def test_public_recipes_are_readable_by_others(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    other, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, owner, is_public=True)

    resp = await client.get(f"/api/v1/recipes/{recipe['id']}", headers=other)
    assert resp.status_code == 200
    # Readable is not writable.
    assert (
        await client.patch(
            f"/api/v1/recipes/{recipe['id']}", json={"name": "Hijacked"}, headers=other
        )
    ).status_code == 404


async def test_public_browse_filters_and_sorts(client: AsyncClient, outbox: Outbox) -> None:
    """The public listing spans every user, so this test namespaces its own data."""
    owner, _ = await register_user(client, outbox)
    reader, _ = await register_user(client, outbox)
    run = uuid.uuid4().hex[:8]

    await create_recipe(client, owner, name=f"Rye {run}", is_public=True, tags=[f"rye{run}"])
    await create_recipe(
        client, owner, name=f"Focaccia {run}", is_public=True, tags=[f"italian{run}"]
    )
    await create_recipe(client, owner, name=f"Secret {run}", is_public=False)

    listing = (await client.get("/api/v1/recipes/public", headers=reader)).json()
    assert all("owner_handle" in r for r in listing)

    by_tag = (await client.get(f"/api/v1/recipes/public?tag=rye{run}", headers=reader)).json()
    assert [r["name"] for r in by_tag] == [f"Rye {run}"]

    by_search = (
        await client.get(f"/api/v1/recipes/public?q=focaccia+{run}", headers=reader)
    ).json()
    assert [r["name"] for r in by_search] == [f"Focaccia {run}"]

    # Unpublished recipes never appear, however the listing is filtered.
    everything = (await client.get(f"/api/v1/recipes/public?q={run}", headers=reader)).json()
    names = {r["name"] for r in everything}
    assert names == {f"Rye {run}", f"Focaccia {run}"}


async def test_public_route_is_not_shadowed_by_the_id_route(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    assert (await client.get("/api/v1/recipes/public", headers=headers)).status_code == 200


# --- forking ------------------------------------------------------------------


async def test_fork_copies_the_formula_and_credits_the_source(
    client: AsyncClient, outbox: Outbox
) -> None:
    owner, _ = await register_user(client, outbox)
    forker, _ = await register_user(client, outbox)
    source = await create_recipe(client, owner, is_public=True)

    fork = await client.post(f"/api/v1/recipes/{source['id']}/fork", headers=forker)
    assert fork.status_code == 201, fork.text
    body = fork.json()

    assert body["forked_from_id"] == source["id"]
    assert body["is_public"] is False, "a fork starts private"
    assert body["version"] == 1
    assert [i["percentage"] for i in body["ingredients"]] == [
        i["percentage"] for i in source["ingredients"]
    ]

    refreshed = (await client.get(f"/api/v1/recipes/{source['id']}", headers=owner)).json()
    assert refreshed["fork_count"] == 1


async def test_fork_is_a_copy_not_a_link(client: AsyncClient, outbox: Outbox) -> None:
    """Editing the parent must not change the fork."""
    owner, _ = await register_user(client, outbox)
    forker, _ = await register_user(client, outbox)
    source = await create_recipe(client, owner, is_public=True)
    fork = (await client.post(f"/api/v1/recipes/{source['id']}/fork", headers=forker)).json()

    await client.patch(
        f"/api/v1/recipes/{source['id']}",
        json={
            "ingredients": [
                {"name": "rye", "kind": "flour", "percentage": 100},
                {"name": "water", "kind": "liquid", "percentage": 90},
            ]
        },
        headers=owner,
    )

    unchanged = (await client.get(f"/api/v1/recipes/{fork['id']}", headers=forker)).json()
    assert len(unchanged["ingredients"]) == 5


async def test_forking_your_own_recipe_avoids_a_name_clash(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    source = await create_recipe(client, headers)
    fork = (await client.post(f"/api/v1/recipes/{source['id']}/fork", headers=headers)).json()
    assert fork["name"] == "Country Loaf (fork)"

    refreshed = (await client.get(f"/api/v1/recipes/{source['id']}", headers=headers)).json()
    assert refreshed["fork_count"] == 0, "forking your own recipe is not a credit"


async def test_private_recipes_cannot_be_forked(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    forker, _ = await register_user(client, outbox)
    source = await create_recipe(client, owner)
    assert (
        await client.post(f"/api/v1/recipes/{source['id']}/fork", headers=forker)
    ).status_code == 404


# --- stars --------------------------------------------------------------------


async def test_star_and_unstar_are_idempotent(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    fan, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, owner, is_public=True)

    for _ in range(3):
        assert (
            await client.post(f"/api/v1/recipes/{recipe['id']}/star", headers=fan)
        ).status_code == 204

    starred = (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=owner)).json()
    assert starred["star_count"] == 1

    for _ in range(3):
        assert (
            await client.delete(f"/api/v1/recipes/{recipe['id']}/star", headers=fan)
        ).status_code == 204

    unstarred = (await client.get(f"/api/v1/recipes/{recipe['id']}", headers=owner)).json()
    assert unstarred["star_count"] == 0


async def test_you_cannot_star_your_own_recipe(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    recipe = await create_recipe(client, headers, is_public=True)
    resp = await client.post(f"/api/v1/recipes/{recipe['id']}/star", headers=headers)
    assert resp.status_code == 409
