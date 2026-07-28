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
