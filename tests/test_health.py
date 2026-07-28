import pytest
from httpx import AsyncClient


async def test_ping(client: AsyncClient) -> None:
    """Liveness must not depend on Postgres or Redis."""
    resp = await client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_openapi_schema(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/ping" in resp.json()["paths"]


@pytest.mark.integration
async def test_health_reports_backing_services(client: AsyncClient) -> None:
    """Readiness against live Postgres + Redis. Run with `pytest -m integration`."""
    resp = await client.get("/api/v1/health")
    body = resp.json()
    assert resp.status_code == 200, body
    assert body["status"] == "ok"
    assert body["checks"] == {"postgres": "ok", "redis": "ok"}
