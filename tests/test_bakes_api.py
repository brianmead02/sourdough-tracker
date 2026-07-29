"""Bake endpoints, including a real round trip through MinIO."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from tests.conftest import register_user

pytestmark = pytest.mark.integration

Outbox = list[tuple[str, str, str]]
Headers = dict[str, str]

# A 1x1 PNG — the smallest thing MinIO will accept as a real object.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ago(**kwargs: float) -> datetime:
    return datetime.now(UTC) - timedelta(**kwargs)


async def create_bake(client: AsyncClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"title": "Saturday loaf"} | overrides
    resp = await client.post("/api/v1/bakes", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def upload_photo(client: AsyncClient, headers: Headers) -> str:
    """Presign, upload the bytes straight to MinIO, return the object key."""
    grant = await client.post(
        "/api/v1/media/presign-upload",
        json={"content_type": "image/png", "purpose": "bake_photo"},
        headers=headers,
    )
    assert grant.status_code == 200, grant.text
    body = grant.json()

    async with httpx.AsyncClient(timeout=30) as raw:
        upload = await raw.post(
            body["url"],
            data=body["fields"],
            files={"file": ("photo.png", PNG_BYTES, "image/png")},
        )
    assert upload.status_code in (200, 204), upload.text
    return str(body["object_key"])


# --- CRUD ---------------------------------------------------------------------


async def test_create_and_complete_a_bake(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(
        client, headers, started_at=iso(ago(hours=8)), total_flour_g=1000, hydration_pct=72
    )
    assert bake["status"] == "in_progress"

    done = await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"oven_temp_c": 245, "bake_time_minutes": 45},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert done.json()["oven_temp_c"] == 245
    assert done.json()["finished_at"] is not None


async def test_completing_twice_is_a_conflict(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    again = await client.post(f"/api/v1/bakes/{bake['id']}/complete", json={}, headers=headers)
    assert again.status_code == 409


async def test_finishing_before_starting_is_rejected(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers, started_at=iso(ago(hours=2)))
    resp = await client.post(
        f"/api/v1/bakes/{bake['id']}/complete",
        json={"finished_at": iso(ago(hours=5))},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_flour_blend_must_sum_to_100(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/bakes",
        json={"title": "Bad blend", "flour_blend": {"rye": 40, "bread": 40}},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_bakes_are_isolated_between_users(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    bake = await create_bake(client, owner)
    bid = bake["id"]

    assert (await client.get(f"/api/v1/bakes/{bid}", headers=intruder)).status_code == 404
    assert (
        await client.patch(f"/api/v1/bakes/{bid}", json={"title": "Mine"}, headers=intruder)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/bakes/{bid}", headers=intruder)).status_code == 404
    assert (
        await client.put(f"/api/v1/bakes/{bid}/rating", json={"overall": 5}, headers=intruder)
    ).status_code == 404


async def test_deleted_bakes_disappear(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    assert (await client.delete(f"/api/v1/bakes/{bake['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/bakes/{bake['id']}", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/bakes", headers=headers)).json() == []


# --- recipe linkage -----------------------------------------------------------


async def test_bake_can_reference_a_readable_recipe(client: AsyncClient, outbox: Outbox) -> None:
    owner, _ = await register_user(client, outbox)
    baker, _ = await register_user(client, outbox)
    recipe = (
        await client.post(
            "/api/v1/recipes",
            json={
                "name": "Shared",
                "is_public": True,
                "ingredients": [
                    {"name": "flour", "kind": "flour", "percentage": 100},
                    {"name": "water", "kind": "liquid", "percentage": 70},
                ],
            },
            headers=owner,
        )
    ).json()

    bake = await create_bake(client, baker, recipe_id=recipe["id"])
    assert bake["recipe_id"] == recipe["id"]


async def test_bake_cannot_reference_a_private_recipe_of_another_user(
    client: AsyncClient, outbox: Outbox
) -> None:
    owner, _ = await register_user(client, outbox)
    baker, _ = await register_user(client, outbox)
    recipe = (
        await client.post(
            "/api/v1/recipes",
            json={
                "name": "Private",
                "ingredients": [
                    {"name": "flour", "kind": "flour", "percentage": 100},
                    {"name": "water", "kind": "liquid", "percentage": 70},
                ],
            },
            headers=owner,
        )
    ).json()

    resp = await client.post(
        "/api/v1/bakes", json={"title": "x", "recipe_id": recipe["id"]}, headers=baker
    )
    assert resp.status_code == 404


async def test_proof_sessions_can_be_attached_to_a_bake(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)

    proof = await client.post(
        "/api/v1/proofing/sessions",
        json={"stage": "bulk", "dough_temp_c": 24, "bake_id": bake["id"]},
        headers=headers,
    )
    assert proof.status_code == 201, proof.text
    assert proof.json()["bake_id"] == bake["id"]

    linked = await client.get(f"/api/v1/bakes/{bake['id']}/proof-sessions", headers=headers)
    assert [s["id"] for s in linked.json()] == [proof.json()["id"]]


async def test_cannot_attach_a_proof_to_someone_elses_bake(
    client: AsyncClient, outbox: Outbox
) -> None:
    owner, _ = await register_user(client, outbox)
    intruder, _ = await register_user(client, outbox)
    bake = await create_bake(client, owner)

    resp = await client.post(
        "/api/v1/proofing/sessions",
        json={"stage": "bulk", "dough_temp_c": 24, "bake_id": bake["id"]},
        headers=intruder,
    )
    assert resp.status_code == 404


# --- ratings ------------------------------------------------------------------


async def test_rating_is_an_upsert(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)

    first = await client.put(
        f"/api/v1/bakes/{bake['id']}/rating",
        json={"overall": 3, "crumb": 2, "notes": "gummy"},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["crumb"] == 2

    revised = await client.put(
        f"/api/v1/bakes/{bake['id']}/rating",
        json={"overall": 5, "crumb": 5, "oven_spring": 4},
        headers=headers,
    )
    assert revised.json()["overall"] == 5
    assert revised.json()["notes"] is None, "an upsert replaces, it does not merge"

    detail = (await client.get(f"/api/v1/bakes/{bake['id']}", headers=headers)).json()
    assert detail["rating"]["overall"] == 5


async def test_scores_are_bounded(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    resp = await client.put(
        f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 11}, headers=headers
    )
    assert resp.status_code == 422


async def test_rating_can_be_removed(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    await client.put(f"/api/v1/bakes/{bake['id']}/rating", json={"overall": 4}, headers=headers)
    assert (
        await client.delete(f"/api/v1/bakes/{bake['id']}/rating", headers=headers)
    ).status_code == 204
    detail = (await client.get(f"/api/v1/bakes/{bake['id']}", headers=headers)).json()
    assert detail["rating"] is None


# --- photos: a real upload to MinIO -------------------------------------------


async def test_photo_round_trip(client: AsyncClient, outbox: Outbox) -> None:
    """Presign, upload straight to storage, confirm, attach, read back."""
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    key = await upload_photo(client, headers)

    confirmed = await client.post(
        "/api/v1/media/confirm", json={"object_key": key}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["size_bytes"] == len(PNG_BYTES)
    assert confirmed.json()["content_type"] == "image/png"

    attached = await client.post(
        f"/api/v1/bakes/{bake['id']}/photos",
        json={"object_key": key, "kind": "crumb", "caption": "open crumb"},
        headers=headers,
    )
    assert attached.status_code == 201, attached.text
    assert attached.json()["kind"] == "crumb"
    assert attached.json()["size_bytes"] == len(PNG_BYTES)

    # The returned URL actually serves the bytes back.
    async with httpx.AsyncClient(timeout=30) as raw:
        fetched = await raw.get(attached.json()["url"])
    assert fetched.status_code == 200
    assert fetched.content == PNG_BYTES

    detail = (await client.get(f"/api/v1/bakes/{bake['id']}", headers=headers)).json()
    assert detail["photo_count"] == 1


async def test_photos_are_private_without_a_signed_url(client: AsyncClient, outbox: Outbox) -> None:
    """The bucket must not serve objects anonymously."""
    headers, _ = await register_user(client, outbox)
    key = await upload_photo(client, headers)
    grant = (
        await client.post("/api/v1/media/confirm", json={"object_key": key}, headers=headers)
    ).json()

    unsigned = grant["url"].split("?")[0]
    async with httpx.AsyncClient(timeout=30) as raw:
        resp = await raw.get(unsigned)
    assert resp.status_code in (401, 403)


async def test_cannot_attach_another_users_upload(client: AsyncClient, outbox: Outbox) -> None:
    """The owner id is embedded in the key and checked on attach."""
    owner, _ = await register_user(client, outbox)
    thief, _ = await register_user(client, outbox)
    key = await upload_photo(client, owner)
    bake = await create_bake(client, thief)

    resp = await client.post(
        f"/api/v1/bakes/{bake['id']}/photos", json={"object_key": key}, headers=thief
    )
    assert resp.status_code == 404


async def test_cannot_attach_a_key_that_was_never_uploaded(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    fabricated = f"u/{me['id']}/bake_photo/{uuid.uuid4()}.png"

    resp = await client.post(
        f"/api/v1/bakes/{bake['id']}/photos", json={"object_key": fabricated}, headers=headers
    )
    assert resp.status_code == 404


async def test_the_same_upload_cannot_be_attached_twice(
    client: AsyncClient, outbox: Outbox
) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    key = await upload_photo(client, headers)

    assert (
        await client.post(
            f"/api/v1/bakes/{bake['id']}/photos", json={"object_key": key}, headers=headers
        )
    ).status_code == 201
    again = await client.post(
        f"/api/v1/bakes/{bake['id']}/photos", json={"object_key": key}, headers=headers
    )
    assert again.status_code == 409


async def test_deleting_a_photo_removes_the_object(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    bake = await create_bake(client, headers)
    key = await upload_photo(client, headers)
    photo = (
        await client.post(
            f"/api/v1/bakes/{bake['id']}/photos", json={"object_key": key}, headers=headers
        )
    ).json()

    assert (
        await client.delete(f"/api/v1/bakes/{bake['id']}/photos/{photo['id']}", headers=headers)
    ).status_code == 204

    gone = await client.post("/api/v1/media/confirm", json={"object_key": key}, headers=headers)
    assert gone.status_code == 404


async def test_upload_grant_rejects_unsupported_types(client: AsyncClient, outbox: Outbox) -> None:
    headers, _ = await register_user(client, outbox)
    resp = await client.post(
        "/api/v1/media/presign-upload",
        json={"content_type": "application/x-msdownload"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_upload_grant_enforces_a_size_limit(client: AsyncClient, outbox: Outbox) -> None:
    """The size cap is a storage-side condition, not a promise the client keeps."""
    headers, _ = await register_user(client, outbox)
    grant = (
        await client.post(
            "/api/v1/media/presign-upload",
            json={"content_type": "image/png"},
            headers=headers,
        )
    ).json()

    oversized = b"\x00" * (grant["max_bytes"] + 1024)
    async with httpx.AsyncClient(timeout=60) as raw:
        resp = await raw.post(
            grant["url"],
            data=grant["fields"],
            files={"file": ("big.png", oversized, "image/png")},
        )
    assert resp.status_code >= 400
