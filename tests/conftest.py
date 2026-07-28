import re
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db import dispose_engine
from app.main import create_app
from app.queue import dispose_arq_pool
from app.services import security


@pytest.fixture(autouse=True)
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Disable rate limits and use cheap argon2 parameters.

    Production cost parameters would add ~50ms to every password operation and
    the limiter would reject the repeated signups these tests perform.
    """
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    monkeypatch.setenv("ARGON2_MEMORY_COST", "8192")
    monkeypatch.setenv("ARGON2_PARALLELISM", "1")
    get_settings.cache_clear()
    security.reset_caches()
    yield
    get_settings.cache_clear()
    security.reset_caches()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the ASGI app, with connection pools torn down after.

    The engine and ARQ pool are process-global and lazily created, but each test
    gets its own event loop. Without disposal the next test inherits connections
    bound to a closed loop and fails with `Event loop is closed`.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()
    await dispose_arq_pool()


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Capture email that would be enqueued, as (to, subject, body)."""
    sent: list[tuple[str, str, str]] = []

    async def fake_enqueue(function: str, *args: object) -> None:
        if function == "send_email":
            to, subject, body = (str(a) for a in args)
            sent.append((to, subject, body))

    monkeypatch.setattr("app.api.v1.auth.enqueue", fake_enqueue)
    return sent


def token_from_email(body: str) -> str:
    """Pull the ?token=... value out of a link in an email body."""
    match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert match, f"no token found in email body:\n{body}"
    return match.group(1)


def unique_account() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:12]
    return {
        "email": f"baker-{suffix}@example.com",
        "password": "a-long-enough-password",
        "handle": f"baker_{suffix}",
        "display_name": "Test Baker",
    }
