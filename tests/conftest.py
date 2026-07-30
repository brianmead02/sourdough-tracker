import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db import dispose_engine, get_session_factory
from app.main import create_app
from app.queue import dispose_arq_pool
from app.services import security

# Integration tests empty every table between tests, so they must never point at
# a database anyone cares about. They used to run against POSTGRES_DB directly,
# which meant a single `pytest -m integration` silently deleted every account in
# the dev database — including the one you were logged in with.
DEFAULT_TEST_DB = "sourdough_test"
TEST_DB = os.environ.get("TEST_POSTGRES_DB", DEFAULT_TEST_DB)

# Any database the suite is allowed to truncate must be named like this. A guard,
# not a convention: the failure mode it prevents is destroying real data.
TEST_DB_MARKER = "test"


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[None]:
    """Point the whole session at a dedicated database, creating it if needed.

    Runs before any function-scoped fixture, so the engine — which is lazy and
    process-global — is first built against the test URL and never against the
    developer's database.
    """
    previous = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = TEST_DB
    get_settings.cache_clear()

    asyncio.run(_provision_test_database())

    yield

    if previous is None:
        os.environ.pop("POSTGRES_DB", None)
    else:
        os.environ["POSTGRES_DB"] = previous
    get_settings.cache_clear()


async def _provision_test_database() -> None:
    """CREATE DATABASE if absent, migrate to head, seed reference data."""
    settings = get_settings()

    # CREATE DATABASE cannot run inside a transaction, and cannot run from a
    # connection to the database being created — hence the maintenance database
    # and AUTOCOMMIT.
    admin_url = (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    finally:
        await admin.dispose()

    # Alembic reads get_settings().database_url, which now resolves to the test
    # database, so this migrates the right target without extra wiring.
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = Config(os.path.join(root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(root, "migrations"))
    await asyncio.to_thread(command.upgrade, config, "head")

    # `achievement` is preserved across truncations, so seed it once per session.
    from app.services.achievements import seed_catalogue

    async with get_session_factory()() as session:
        await seed_catalogue(session)
    await dispose_engine()


@pytest.fixture(autouse=True)
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Disable rate limits and use cheap argon2 parameters.

    Production cost parameters would add ~50ms to every password operation and
    the limiter would reject the repeated signups these tests perform.
    """
    monkeypatch.setenv("POSTGRES_DB", TEST_DB)
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
        # Refuse to empty anything that is not demonstrably a test database. This
        # check is the reason the guard exists rather than the naming convention:
        # a misconfigured POSTGRES_DB previously turned the whole suite into a
        # `DELETE FROM` against real data, and it failed silently.
        name = await session.scalar(text("SELECT current_database()"))
        if TEST_DB_MARKER not in str(name):
            raise RuntimeError(
                f"refusing to truncate database {name!r}: the name does not contain "
                f"{TEST_DB_MARKER!r}. Integration tests empty every table, so they "
                f"must run against a dedicated database. Unset TEST_POSTGRES_DB to use "
                f"the default {DEFAULT_TEST_DB!r}, or set it to a name containing "
                f"{TEST_DB_MARKER!r}."
            )
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
