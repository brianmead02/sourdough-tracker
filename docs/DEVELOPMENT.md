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

**Backend** — all four must pass before a change is done:

```bash
docker compose exec api ruff format app tests
docker compose exec api ruff check . --fix
docker compose exec api mypy app
docker compose exec api pytest -q                 # unit only, ~1s
docker compose exec api pytest -q -m integration  # needs the live stack, ~65s
```

Working on a client and want something to look at? Seed a populated account
rather than clicking through a fresh one:

```bash
docker compose exec api sdt seed-demo
```

It prints the credentials and builds three weeks of plausible history — a
21-feed streak, seven completed bakes, 825 XP, nine badges, a stocked pantry.
The history is generated from a fixed seed, so two runs produce the same numbers
and a screenshot stays reproducible. It refuses to run a second time over an
existing `demo@example.com` (pass `--email` for another), and refuses outright
when `ENVIRONMENT=prod` — fabricated bakes on a real leaderboard would be
indistinguishable from cheating.

**Web app** — no build step, no `node_modules`; node is only for the tests:

```bash
node --test web/test/app.test.mjs                 # 27 tests, browser globals stubbed
python scripts/check_contrast.py                  # WCAG AA on every declared pair
python scripts/check_shell_size.py                # offline shell transfer budget
```

The two Python checks exist because both problems they catch had already
happened. `check_contrast.py` parses the custom properties out of `app.css` and
fails under 4.5:1 — the dark-mode primary button shipped at 2.15:1, which is
below even the large-text floor. `check_shell_size.py` budgets *compressed*
transfer size and also fails if any `SHELL` entry in `sw.js` does not exist,
since `cache.addAll()` rejects on a single 404 and silently leaves every client
with no offline support at all.

Changing the vendored font is a deliberate act, not an edit:

```bash
pip install fonttools brotli
python scripts/build_font.py            # download, subset, write web/vendor/
python scripts/build_font.py --check    # verify the committed file is reproducible
```

So is changing an image. Sources live in `images/`; nothing reads them at
runtime. `web/img/` holds the WebP the app actually serves, and the crop
coordinates live in the `Asset` record so a framing decision is reviewable:

```bash
pip install pillow
python scripts/build_images.py          # crop, resize, write web/img/
python scripts/build_images.py --check  # verify the committed files are reproducible
```

**Bump `VERSION` in `web/sw.js` after any change under `web/`.** The shell is
cached cache-first, so without it a redesign ships to nobody — including to you,
which is worth knowing before you spend an hour wondering why your CSS has no
effect.

**Android app** — needs Flutter 3.41+:

```bash
cd mobile
dart format lib test
flutter analyze
flutter test                                      # 16 tests
```

CI runs all of these, plus a Docker build.

### Test layers

| Layer | Count | Speed | Touches |
|---|---|---|---|
| Python unit | 288 | ~3 s | Nothing — pure functions and static assets |
| Python integration | 262 | ~75 s | Postgres, Redis, MinIO, ntfy |
| Browser logic | 27 | <1 s | node, with browser globals stubbed |
| Dart | 16 | ~2 s | `flutter test` |

Integration tests are marked and **deselected by default** (`addopts = -m 'not
integration'`). They are not mocked: email really lands in Mailhog, uploads
really go to MinIO and are read back byte-for-byte.

**Write the maths as a pure function and test it there.** That is why
`test_fermentation.py` has 34 tests running in 60 ms. Reach for an integration
test when the behaviour *is* the wiring — ownership checks, status codes,
transaction boundaries.

### The test database

**Integration tests run against `sourdough_test`, never your dev database.** The
session-scoped `test_database` fixture creates it if absent, migrates it to head
and seeds the achievement catalogue, then points `POSTGRES_DB` at it for the whole
run. Override with `TEST_POSTGRES_DB` if you need a different name.

This is not cosmetic separation. The suite empties every table between tests, and
it originally did that to whatever `POSTGRES_DB` pointed at — so a single
`pytest -m integration` deleted every account in the dev database, including the
one you were logged in as, and said nothing about it. `truncate_all()` now
refuses to run unless the current database name contains `test`:

```
RuntimeError: refusing to truncate database 'sourdough': the name does not
contain 'test'.
```

Lost your dev data to this? `docker compose exec api sdt seed-demo` rebuilds a
populated account in seconds.

**Every integration test starts on an empty database.** The `client` fixture
calls `truncate_all()`, which issues one
`TRUNCATE ... RESTART IDENTITY CASCADE` across every table except
`alembic_version` and `achievement` — the migration bookmark and the seeded
badge catalogue, both of which are fixtures rather than test data. The table
list is discovered once and the statement cached, so the cost is a few
milliseconds per test rather than a query round-trip.

This is why assertions can be exact. Tests written before isolation existed had
to scope themselves to their own data (a `uuid4()` suffix, `/leaderboard/me`
instead of paging the board) because a shared database had grown past a thousand
accounts. If you find a test doing that defensively, it can now assert on the
real thing.

The cost is that tests **cannot run in parallel** against one database — `-n
auto` would have workers truncating each other's rows. If that becomes worth
having, give each worker its own database rather than dropping the truncate.

---

## Layout

```
app/           FastAPI service
  api/v1/      HTTP only — auth, validation, status codes
  schemas/     Pydantic contracts
  services/    Business logic; pure functions wherever the maths allows
  models/      SQLAlchemy tables
  worker/      Background tasks and the beat schedule
web/           The PWA — no build step, Alpine vendored in web/vendor/
mobile/        Flutter Android app; lib/api/models.dart is generated
scripts/       build_font.py, build_images.py, check_contrast.py,
               check_shell_size.py, generate_dart_models.py, backup.sh,
               loadtest.py
tests/         Python tests (integration ones are marked)
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

### Changing the web app

Edit files in `web/` and reload — `docker-compose.dev.yml` mounts the directory
into the API, which serves it. Things to keep true:

* **Nothing from a CDN.** Vendor it into `web/vendor/` instead; a test asserts
  the shell contains no external URLs.
* **Add new files to the `SHELL` precache list in `sw.js`.** A precache entry
  that 404s makes `install` reject and the service worker never activates —
  `tests/test_pwa_assets.py` checks every entry resolves.
* **Bump `VERSION` in `sw.js`** when shell assets change, or clients keep the
  old cache.
* Alpine fails *silently* on a missing handler, so the same test file asserts
  every `@click`, `x-text` and `x-model` binding resolves to something that
  exists on the component.

### Changing the Android app

```bash
cd mobile && flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`lib/api/models.dart` is **generated** — never hand-edit it. After changing any
response schema:

```bash
python scripts/generate_dart_models.py     # with the stack running
cd mobile && flutter analyze
```

That is the drift check: if the API changed shape incompatibly, the app stops
compiling rather than failing at runtime on a user's phone.

Android specifics worth knowing before debugging for an hour:

* `10.0.2.2` is the host from inside the emulator; `localhost` is the emulator.
* Cleartext HTTP is permitted **only** for `10.0.2.2` and `localhost`
  (`android/app/src/main/res/xml/network_security_config.xml`). Anything else
  must be HTTPS.
* `INTERNET` lives in the **main** manifest. `flutter create` only puts it in
  the debug one, which makes release builds silently unable to reach anything.

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

**Line length 100** in Python; ruff formats, do not hand-wrap. Dart uses
`dart format` defaults (80).

**The two clients must behave the same on a bad network.** The web outbox
(`web/js/db.js`) and the Dart one (`mobile/lib/api/outbox.dart`) implement the
same drain policy — keep on network/5xx/401, drop on any other 4xx — and both
have tests for both directions. If you change one, change the other.

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

**Reminders not arriving** — they are queued in `scheduled_notification` and
delivered by the beat tick every 60 seconds, so nothing is instant. Look at the
queue first:

```bash
docker compose exec -T postgres psql -U sourdough -d sourdough -c "SELECT event, status, due_at, attempts, last_error FROM scheduled_notification ORDER BY created_at DESC LIMIT 10;"
docker compose logs beat --since 10m | grep drain
```

To drain by hand instead of waiting for the tick, pipe a script into the
container rather than fighting nested quoting:

```bash
docker compose exec -T api python - <<'PY'
import asyncio
from app.db import get_session_factory
from app.services.notifications import drain

async def go():
    async with get_session_factory()() as session:
        print(await drain(session))
        await session.commit()

asyncio.run(go())
PY
```

[HOWTO.md](HOWTO.md) explains what each status means.

**A dependency change did nothing** — `pyproject.toml` is mounted, but installed
packages come from the image. Rebuild *and recreate*:
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.
Building without recreating leaves the old containers running, which has caused
two separate bugs in this project.
