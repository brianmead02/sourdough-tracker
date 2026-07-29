import re
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import get_settings
from app.db import dispose_engine, get_session_factory
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


# Reference data, not test data. `achievement` is a projection of the code
# catalogue seeded once by `sdt seed-achievements`; wiping it would break the
# foreign key from user_achievement and force a re-seed on every single test.
PRESERVED_TABLES = {"alembic_version", "achievement"}

# Built once per session — the schema does not change mid-run.
_truncate_statement: str | None = None


async def truncate_all() -> None:
    """Empty every table of test data.

    Integration tests used to share one accumulating database, which made
    anything asserting on a global listing — leaderboards, public recipes —
    order-dependent and quietly wrong once a few hundred accounts had built up.
    Three tests had to be weakened to work around it. Truncating per test is
    cheap (the tables are almost always empty) and removes the whole class of
    problem.
    """
    global _truncate_statement
    async with get_session_factory()() as session:
        if _truncate_statement is None:
            rows = await session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            tables = [t for (t,) in rows.all() if t not in PRESERVED_TABLES]
            quoted = ", ".join(f'"{name}"' for name in tables)
            _truncate_statement = f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"
        await session.execute(text(_truncate_statement))
        await session.commit()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the ASGI app, against a freshly emptied database.

    The engine and ARQ pool are process-global and lazily created, but each test
    gets its own event loop. Without disposal the next test inherits connections
    bound to a closed loop and fails with `Event loop is closed`.
    """
    await truncate_all()
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


async def register_user(
    client: AsyncClient, outbox: list[tuple[str, str, str]], *, verify: bool = True
) -> tuple[dict[str, str], dict[str, str]]:
    """Register, optionally confirm the email, log in. Returns (auth headers, account)."""
    account = unique_account()
    first_email = len(outbox)
    resp = await client.post("/api/v1/auth/register", json=account)
    assert resp.status_code == 202, resp.text

    if verify:
        token = token_from_email(outbox[first_email][2])
        confirmed = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert confirmed.status_code == 200, confirmed.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, account


def unique_account() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:12]
    return {
        "email": f"baker-{suffix}@example.com",
        "password": "a-long-enough-password",
        "handle": f"baker_{suffix}",
        "display_name": "Test Baker",
    }
