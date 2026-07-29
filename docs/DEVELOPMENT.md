# Development

Working on the codebase: running it, testing it, and the specific recipes for
the changes you are most likely to make.

---

## Setup

Everything runs in Docker; you do not need a local Python.

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec api alembic upgrade head
docker compose exec api sdt seed-achievements
```

`app/`, `tests/`, `migrations/` and `pyproject.toml` are **bind-mounted** into
the container, so edits apply immediately — uvicorn reloads, and lint/type/test
config changes take effect without a rebuild. Only a **dependency change**
requires `docker compose build`.

Prefer a local environment? You need **Python 3.12** specifically (`3.11` is too
old for the syntax used, `3.14` has wheel gaps in the dependency set):

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export POSTGRES_HOST=localhost REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload
```

---

## The loop

```bash
docker compose exec api ruff format app tests
docker compose exec api ruff check . --fix
docker compose exec api mypy app
docker compose exec api pytest -q                 # unit only, ~1s
docker compose exec api pytest -q -m integration  # needs the live stack, ~18s
```

All four must pass before a change is done. CI runs exactly these plus a Docker
build.

### Test layers

| | Count | Speed | Touches |
|---|---|---|---|
| Unit | 152 | <1 s | Nothing — pure functions |
| Integration | 159 | ~18 s | Postgres, Redis, MinIO |

Integration tests are marked and **deselected by default** (`addopts = -m 'not
integration'`). They are not mocked: email really lands in Mailhog, uploads
really go to MinIO and are read back byte-for-byte.

**Write the maths as a pure function and test it there.** That is why
`test_fermentation.py` has 34 tests running in 60 ms. Reach for an integration
test when the behaviour *is* the wiring — ownership checks, status codes,
transaction boundaries.

> **Known limitation.** Integration tests share one database and never truncate.
> Anything asserting on a globally-shared listing (leaderboards, public recipes)
> must scope to its own data — use a `uuid4()` suffix, or `/leaderboard/me`
> instead of paging the board. Three tests had to be rewritten after the shared
> database grew past a thousand accounts. Per-test isolation is Phase 10 work.

---

## Layout

```
app/
  api/v1/      HTTP only — auth, validation, status codes
  schemas/     Pydantic contracts
  services/    Business logic; pure functions wherever the maths allows
  models/      SQLAlchemy tables
  worker/      Background tasks and the beat schedule
```

The rule: **if it is arithmetic rather than I/O, it belongs in `services/` as a
pure function** taking plain values, not ORM objects or sessions. See
[ARCHITECTURE.md](ARCHITECTURE.md#2-layers).

---

## Recipes

### Adding an endpoint

1. Schemas in `app/schemas/<area>.py`. Use `Annotated` aliases for shared
   constraints — **never share a `Field()` instance between models**, pydantic v2
   can mutate it during model construction.
2. Route in `app/api/v1/<area>.py`. Use `CurrentUser` for reads, `VerifiedUser`
   for writes.
3. Fetch owned rows through an `_get_owned(...)` helper that filters on
   `user_id` and raises **404** (not 403) when it misses.
4. Register the router in `app/api/v1/router.py`.
5. **Declare literal paths before parameterised ones** — `/starters/schedule`
   must precede `/starters/{starter_id}`. There are tests asserting this for
   `/schedule`, `/active` and `/public`; add one for any new literal route.

### Adding a migration

```bash
docker compose exec api alembic revision --autogenerate -m "what changed"
docker compose exec api alembic upgrade head
docker compose exec api alembic check          # must report no drift
```

Read the generated file before committing — autogenerate misses partial index
predicates and server defaults often enough to matter. Then prove it reverses:

```bash
docker compose exec api sh -c "alembic downgrade -1 && alembic upgrade head"
```

New models must be imported in `app/models/__init__.py` or autogenerate will not
see them and will cheerfully generate a migration that drops nothing.

**Gotchas that have already bitten:**

- `SmallInteger` caps at 32767 — wrong for byte counts. Use `Integer`.
- Descending index expressions need `text("col DESC")`; a mapped attribute's
  `.desc()` inside `__table_args__` is not reliable.
- Partial unique indexes need `postgresql_where=text("deleted_at IS NULL")`.

### Adding an achievement

Definitions in `app/services/achievements/definitions.py` are **authoritative**;
the `achievement` table is a projection.

```python
AchievementDef(
    "code_name", "Display Name", "What the baker did.",
    Cat.baking, Rarity.rare, 250, "🥖",
    Metric.bakes_completed, 100,          # metric and target
    (E.bake_completed,),                  # events that could move it
    requires_photo=False,
)
```

Then:

```bash
docker compose exec api sdt seed-achievements
docker compose exec api pytest -q tests/test_gamification_logic.py
```

Those unit tests enforce catalogue integrity: every achievement must have an
implemented metric, be reachable from at least one event, and never pay less than
an easier target for the same metric. A badge failing any of those is unearnable
or unbalanced.

Need a metric that does not exist? Add an aggregate to
`app/services/achievements/metrics.py` and register it in `METRIC_FUNCTIONS`. It
must be a **plain aggregate over the user's own rows** — the whole point is that
a badge is derivable from first principles rather than from an incremented
counter.

### Adding a domain event

1. Add the member to `DomainEvent` in `app/services/events.py`.
2. Give it a rate in `BASE_XP` and, if it pays, a cap in `DAILY_CAPS` — a unit
   test fails if a paying event is uncapped.
3. Call `publish(...)` from the router after the row is flushed.
4. **Add it to `app/services/replay.py:_timeline`**, or `sdt recompute-xp` will
   silently under-award it. This is the easiest step to forget.

### Recomputing the XP ledger

```bash
docker compose exec api sdt recompute-xp --yes
```

Deletes every `xp_event`, `user_achievement` and `leaderboard_entry`, then
replays each user's history chronologically through the same `award()` used
live — backdated, so events land in the right season and daily bucket.

It is **destructive and idempotent**. Use it after rebalancing rates, changing
targets, or adding achievements that existing history should already satisfy.
Daily caps are per UTC calendar day rather than a rolling window *specifically*
so this reproduces them exactly.

---

## Conventions

**Comments explain *why*.** The code already says what. A comment that restates
the line is noise; one that records the trade-off is the reason the file can be
changed safely a year later.

**Ownership is 404, never 403.** A 403 confirms the row exists.

**Derive, do not store.** Streaks, hydration, stock on hand, achievement
progress. If you are about to add a counter column, check whether the rows that
would increment it already exist. See
[ARCHITECTURE.md](ARCHITECTURE.md#derived-never-stored).

**Soft delete for anything that grants XP**, with a partial unique index so the
name is freed but the history survives.

**Timestamps are UTC** on the wire and in the database. `fed_at`-style fields are
bounded: no future beyond 5 minutes of skew, no more than 30 days back.

**Line length 100.** ruff formats; do not hand-wrap.

---

## Debugging

```bash
docker compose logs -f api
docker compose logs -f worker                     # background work lives here
docker compose exec postgres psql -U sourdough -d sourdough
docker compose exec redis redis-cli
docker compose exec redis redis-cli --scan --pattern "ratelimit:*"
```

**Rate-limited yourself out of testing?**

```bash
docker compose exec redis redis-cli flushdb
```

**`MissingGreenlet: greenlet_spawn has not been called`** — a lazy relationship
load in async context. A freshly-inserted row has no loaded relationships;
`selectin` only applies to rows fetched by a query. Fix with
`await db.refresh(obj, attribute_names=[...])`.

**`Event loop is closed` in tests** — the process-global engine outlived a test's
event loop. The `client` fixture disposes the engine and ARQ pool on teardown;
anything creating its own session must do the same.

**Emails not arriving in dev** — they are sent by the worker, not the API. Check
`docker compose logs worker`, and confirm the worker is running the same image
as the API.
