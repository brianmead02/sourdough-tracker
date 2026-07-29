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


@app.command("vapid-keys")
def vapid_keys() -> None:
    """Generate a VAPID keypair for Web Push, ready to paste into .env."""
    import base64

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid01

    vapid = Vapid01()
    vapid.generate_keys()

    def b64(raw: bytes) -> str:
        """VAPID keys are base64url without padding."""
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    private_numbers = vapid.private_key.private_numbers()
    public = vapid.public_key.public_bytes(
        encoding=Encoding.X962, format=PublicFormat.UncompressedPoint
    )
    typer.echo("# Paste into .env — the private key is a secret, the public one is not.")
    typer.echo(f"VAPID_PUBLIC_KEY={b64(public)}")
    typer.echo(f"VAPID_PRIVATE_KEY={b64(private_numbers.private_value.to_bytes(32, 'big'))}")
    typer.echo("VAPID_SUBJECT=mailto:admin@your-domain.example")


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


@app.command("seed-demo")
def seed_demo(
    email: str = typer.Option("demo@example.com"),
    password: str = typer.Option("a-long-enough-password"),
    days: int = typer.Option(21, help="How much history to fabricate."),
) -> None:
    """Create a demo account with a plausible history.

    For screenshots, manual testing and showing someone what the thing does
    without asking them to spend three weeks feeding a starter first. Refuses to
    run when ENVIRONMENT=prod: fabricated bakes on a real leaderboard would be
    indistinguishable from cheating.
    """

    async def _seed() -> None:
        import random
        from datetime import UTC, datetime, timedelta

        from app.config import get_settings
        from app.db import dispose_engine, get_session_factory
        from app.models.bake import Bake, BakeRating, BakeStatus
        from app.models.proofing import ProofSession, ProofStage, ProofStatus
        from app.models.recipe import IngredientKind, Recipe, RecipeIngredient
        from app.models.starter import Feeding, Starter
        from app.services import auth as auth_service
        from app.services.leaderboard import refresh
        from app.services.replay import replay_user

        if get_settings().environment == "prod":
            typer.secho("refusing to seed demo data in production", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        # Deterministic, so repeated runs and screenshots look the same.
        rng = random.Random(20260729)
        now = datetime.now(UTC)

        async with get_session_factory()() as session:
            if await auth_service.get_user_by_email(session, email) is not None:
                typer.secho(f"{email} already exists — nothing to do", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)

            user = await auth_service.create_user(
                session,
                email=email,
                password=password,
                handle="demo_baker",
                display_name="Demo Baker",
                timezone="America/Chicago",
            )
            user.email_verified_at = now

            starter = Starter(
                user_id=user.id,
                name="Gerald",
                flour_type="rye",
                ratio_starter=1,
                ratio_flour=5,
                ratio_water=5,
                feed_interval_hours=24,
            )
            session.add(starter)
            await session.flush()

            # A daily feeding streak, drifting a little so it looks human.
            for day in range(days, 0, -1):
                session.add(
                    Feeding(
                        starter_id=starter.id,
                        fed_at=now - timedelta(days=day, hours=rng.uniform(-2, 2)),
                        starter_g=20,
                        flour_g=100,
                        water_g=100,
                        ambient_temp_c=round(rng.uniform(19, 24), 1),
                    )
                )

            recipe = Recipe(
                owner_id=user.id,
                name="Everyday Country Loaf",
                description="70% hydration, overnight retard.",
                is_public=True,
                tags=["rye", "everyday"],
                default_dough_weight_g=1800,
            )
            recipe.ingredients = [
                RecipeIngredient(name="bread flour", kind=IngredientKind.flour, percentage=90),
                RecipeIngredient(
                    name="whole rye", kind=IngredientKind.flour, percentage=10, sort_order=1
                ),
                RecipeIngredient(
                    name="water", kind=IngredientKind.liquid, percentage=70, sort_order=2
                ),
                RecipeIngredient(name="salt", kind=IngredientKind.salt, percentage=2, sort_order=3),
                RecipeIngredient(
                    name="levain", kind=IngredientKind.starter, percentage=20, sort_order=4
                ),
            ]
            session.add(recipe)
            await session.flush()

            for index, day in enumerate(range(days, 0, -3)):
                started = now - timedelta(days=day)
                bake = Bake(
                    user_id=user.id,
                    recipe_id=recipe.id,
                    title=f"Saturday loaf #{index + 1}",
                    status=BakeStatus.done,
                    started_at=started,
                    finished_at=started + timedelta(hours=6),
                    total_flour_g=1000,
                    hydration_pct=round(rng.uniform(68, 78), 1),
                    salt_pct=2,
                    starter_pct=20,
                    loaf_count=2,
                    flour_blend={"bread flour": 90, "whole rye": 10},
                    oven_temp_c=245,
                    bake_time_minutes=42,
                    vessel="dutch oven",
                )
                session.add(bake)
                await session.flush()
                bake.rating = BakeRating(
                    overall=rng.randint(3, 5),
                    crumb=rng.randint(3, 5),
                    oven_spring=rng.randint(3, 5),
                    crust=rng.randint(3, 5),
                )
                session.add(
                    ProofSession(
                        user_id=user.id,
                        starter_id=starter.id,
                        bake_id=bake.id,
                        stage=ProofStage.bulk,
                        status=ProofStatus.done,
                        started_at=started,
                        actual_end_at=started + timedelta(hours=5),
                        dough_temp_c=24,
                        starter_pct=20,
                        target_rise_pct=75,
                        predicted_end_at=started + timedelta(hours=5),
                        window_start_at=started + timedelta(hours=4),
                        window_end_at=started + timedelta(hours=6),
                    )
                )

            await session.flush()
            # Derive XP and achievements from the history, exactly as a real
            # account would have earned them.
            await replay_user(session, user.id)
            await refresh(session)
            await session.commit()

        typer.secho(f"seeded {email} / {password}", fg=typer.colors.GREEN)
        typer.echo(f"  {days} feedings, {len(range(days, 0, -3))} bakes, 1 public recipe")
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
