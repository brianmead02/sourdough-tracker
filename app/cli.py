"""`sdt` — admin and batch operations.

Later phases add: seed-achievements, recompute-xp, create-admin, backfill.
"""

import asyncio

import typer

app = typer.Typer(help="Sourdough Tracker admin CLI", no_args_is_help=True)
db_app = typer.Typer(help="Database and migration helpers", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.command()
def version() -> None:
    """Print the application version."""
    typer.echo("sourdough-tracker 0.1.0")


@app.command()
def config() -> None:
    """Show the resolved configuration (secrets masked)."""
    from app.config import get_settings

    settings = get_settings()
    secret_markers = ("password", "secret", "key")
    for name, value in settings.model_dump().items():
        masked = "***" if any(m in name for m in secret_markers) and value else value
        typer.echo(f"{name:24} {masked}")


@app.command()
def check() -> None:
    """Verify Postgres and Redis are reachable with the current configuration."""

    async def _check() -> int:
        import redis.asyncio as aioredis
        from sqlalchemy import text

        from app.config import get_settings
        from app.db import dispose_engine, get_engine

        settings = get_settings()
        failures = 0

        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            typer.secho("postgres  ok", fg=typer.colors.GREEN)
        except Exception as exc:  # noqa: BLE001
            typer.secho(f"postgres  FAILED: {exc}", fg=typer.colors.RED)
            failures += 1
        finally:
            await dispose_engine()

        client = aioredis.from_url(settings.redis_url)
        try:
            await client.ping()
            typer.secho("redis     ok", fg=typer.colors.GREEN)
        except Exception as exc:  # noqa: BLE001
            typer.secho(f"redis     FAILED: {exc}", fg=typer.colors.RED)
            failures += 1
        finally:
            await client.aclose()

        return failures

    if asyncio.run(_check()) > 0:
        raise typer.Exit(code=1)


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., prompt=True),
    handle: str = typer.Option(..., prompt=True),
    display_name: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Create a pre-verified administrator account."""

    async def _create() -> None:
        from datetime import UTC, datetime

        from app.db import dispose_engine, get_session_factory
        from app.models.user import UserRole
        from app.schemas.validators import validate_handle, validate_password
        from app.services import auth as auth_service

        clean_handle = validate_handle(handle)
        validate_password(password)

        async with get_session_factory()() as session:
            if await auth_service.get_user_by_email(session, email) is not None:
                typer.secho(f"a user with email {email} already exists", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            if await auth_service.handle_taken(session, clean_handle):
                typer.secho(f"handle @{clean_handle} is taken", fg=typer.colors.RED)
                raise typer.Exit(code=1)

            user = await auth_service.create_user(
                session,
                email=email,
                password=password,
                handle=clean_handle,
                display_name=display_name,
                role=UserRole.admin,
            )
            # Created out-of-band by an operator, so no email round-trip is needed.
            user.email_verified_at = datetime.now(UTC)
            await session.commit()
            typer.secho(f"created admin @{clean_handle} ({email})", fg=typer.colors.GREEN)

        await dispose_engine()

    try:
        asyncio.run(_create())
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@app.command("seed-achievements")
def seed_achievements() -> None:
    """Project the code catalogue into the achievement table."""

    async def _seed() -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.db import dispose_engine, get_session_factory
        from app.models.gamification import Achievement
        from app.services.achievements import ACHIEVEMENTS

        async with get_session_factory()() as session:
            for definition in ACHIEVEMENTS:
                values = {
                    "code": definition.code,
                    "name": definition.name,
                    "description": definition.description,
                    "category": definition.category,
                    "rarity": definition.rarity,
                    "xp_award": definition.xp_award,
                    "icon": definition.icon,
                    "target": definition.target,
                    "criteria": {"metric": definition.metric.value, **definition.criteria},
                    "requires_photo": definition.requires_photo,
                }
                await session.execute(
                    insert(Achievement)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["code"],
                        set_={k: v for k, v in values.items() if k != "code"},
                    )
                )
            await session.commit()
        typer.secho(f"seeded {len(ACHIEVEMENTS)} achievements", fg=typer.colors.GREEN)
        await dispose_engine()

    asyncio.run(_seed())


@app.command("recompute-xp")
def recompute_xp(
    confirm: bool = typer.Option(False, "--yes", help="Required: this rewrites the ledger."),
) -> None:
    """Rebuild the XP ledger and achievements from the underlying data.

    This is what the append-only, source-keyed ledger buys: a rule can be
    rebalanced and history rebuilt, rather than patched.
    """
    if not confirm:
        typer.secho("refusing to rewrite the ledger without --yes", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    async def _recompute() -> None:
        from app.db import dispose_engine, get_session_factory
        from app.services.leaderboard import refresh
        from app.services.replay import replay_all

        async with get_session_factory()() as session:
            result = await replay_all(session)
            await refresh(session)
            await session.commit()

        typer.secho(
            f"replayed {result.events} events for {result.users} users: "
            f"{result.xp} XP, {result.achievements} achievements",
            fg=typer.colors.GREEN,
        )
        await dispose_engine()

    asyncio.run(_recompute())


@app.command("refresh-leaderboard")
def refresh_leaderboard_command() -> None:
    """Rebuild the leaderboard rollup now."""

    async def _refresh() -> None:
        from app.db import dispose_engine, get_session_factory
        from app.services.leaderboard import refresh

        async with get_session_factory()() as session:
            result = await refresh(session)
            await session.commit()
        typer.secho(
            f"{result.season_name}: ranked {result.users_ranked} users", fg=typer.colors.GREEN
        )
        await dispose_engine()

    asyncio.run(_refresh())


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Apply migrations up to REVISION."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), revision)


@db_app.command("downgrade")
def db_downgrade(revision: str = typer.Argument(...)) -> None:
    """Roll migrations back to REVISION."""
    from alembic import command
    from alembic.config import Config

    command.downgrade(Config("alembic.ini"), revision)


@db_app.command("revision")
def db_revision(
    message: str = typer.Option(..., "-m", "--message"),
    autogenerate: bool = typer.Option(True, "--autogenerate/--empty"),
) -> None:
    """Create a new migration revision."""
    from alembic import command
    from alembic.config import Config

    command.revision(Config("alembic.ini"), message=message, autogenerate=autogenerate)


@db_app.command("current")
def db_current() -> None:
    """Show the revision currently applied to the database."""
    from alembic import command
    from alembic.config import Config

    command.current(Config("alembic.ini"), verbose=True)


if __name__ == "__main__":
    app()
