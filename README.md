# Sourdough Tracker

Multi-tenant sourdough service: starter management, live proofing predictions, bake logs,
shareable recipes, flour inventory/costing, and XP + achievements + seasonal leaderboards —
with reminders over Web Push, email, ntfy and in-app.

Full design: [docs/PLAN.md](docs/PLAN.md). **Current state: Phase 6 (gamification) complete —
the server is feature-complete apart from notifications.**

## Quick start

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec api alembic upgrade head
curl localhost:8000/api/v1/health
```

| Service | URL |
|---|---|
| API + docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |
| Mailhog | http://localhost:8025 |
| ntfy | http://localhost:8081 |

Every dev-published port is overridable in `.env` (`API_DEV_PORT`, `POSTGRES_DEV_PORT`, …) —
this stack is expected to run alongside services that already own the default ports. Nothing
inside the stack depends on them; containers talk over the compose network.

Production adds Caddy (TLS, static, reverse proxy) and drops the published database ports:

```bash
docker compose --profile prod up -d --build
```

## Local development without Docker

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate elsewhere
pip install -e ".[dev]"
# point the app at the containerised datastores
export POSTGRES_HOST=localhost REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload
```

## `sdt` CLI

```
sdt version              # application version
sdt config               # resolved settings, secrets masked
sdt check                # verify Postgres + Redis connectivity
sdt create-admin         # create a pre-verified administrator account
sdt seed-achievements    # project the code catalogue into the achievement table
sdt recompute-xp --yes   # rebuild the whole XP ledger from the underlying data
sdt refresh-leaderboard  # rebuild the leaderboard rollup now
sdt db upgrade [rev]     # apply migrations (default: head)
sdt db downgrade <rev>
sdt db revision -m "..." # autogenerate a migration from model changes
sdt db current
```

## Tests

```bash
pytest                  # unit tests, no external services
pytest -m integration   # requires live Postgres + Redis
ruff check . && ruff format --check . && mypy app
```

## Architecture notes

- **`api` / `worker` / `beat` are the same image**, different commands. `beat` decides what is
  due and enqueues onto `arq:work`; `worker` does the work. See [docs/PLAN.md](docs/PLAN.md) §6.
  They deliberately use **separate queues** — arq registers cron functions under a `cron:`
  prefix in the defining process only, so a worker sharing beat's queue would claim jobs it
  cannot resolve (`tests/test_worker_config.py` guards this).
- **Migrations are never auto-applied on boot** — run `alembic upgrade head` deliberately so a
  rolling deploy can't race itself.
- **Media never passes through the API.** Clients presign against MinIO and upload directly.

## Identity model (Phase 1)

Endpoints live under `/api/v1/auth` and `/api/v1/profiles`; see `/docs` for the full schema.
The properties worth knowing before changing this code:

- **Access tokens are short-lived JWTs (15 min); refresh tokens are opaque, stored as SHA-256
  hashes, and rotate on every use.** Replaying a spent refresh token revokes its entire
  `family_id` — the legitimate client is signed out too, because the token demonstrably leaked.
  That revocation is committed explicitly, since the request ends in a 401 and the session
  dependency rolls back on exception.
- **Registration never reveals whether an email is already in use.** Same status, same body
  either way; the real owner instead receives a "someone tried to sign up" email. Handle
  collisions *do* return 409 — handles are public. Login spends a dummy argon2 hash when no
  user matches, so timing does not leak either.
- **Suspension is checked per request**, not baked into the token, so it takes effect before
  the current access token would expire.
- **Profiles are private until published** (`is_public`); a private profile 404s exactly like a
  missing one. Public profiles never include the email address.
- **Rate limits** are Redis fixed-window, keyed by scope + client IP, and **fail open** — a
  Redis outage must not lock everyone out of logging in.
- `JWT_SECRET` must be ≥32 characters, and the app refuses to boot in `prod` with the shipped
  dev default.

## Starters (Phase 2)

`/api/v1/starters` — CRUD plus `/feedings`, `/observations`, `/streak`, `/suggested-feed`, and a
cross-starter `/starters/schedule`. Reads need a login; writes additionally need a confirmed
email address. The modelling decisions:

- **The feed ratio (starter:flour:water) is the source of truth; `hydration_pct` is derived
  from it.** Storing both would let them disagree.
- **Streaks are counted in scheduled intervals, not calendar days.** That is what makes a
  fridge-kept starter work: set its interval to a week and a weekly feed sustains the streak,
  while a daily starter still has to be fed daily. A feed may be up to `GRACE_FACTOR` (1.5×)
  late and still count.
- **Streaks are derived from the feeding rows on read, never stored as a counter** — so they
  cannot drift, and a corrected feeding retroactively corrects the streak.
- **`overdue` on the schedule and a broken streak are the same instant, by construction.**
  A unit test asserts the two agree, so the dashboard can never contradict the streak page.
- **Anti-cheat:** `fed_at` may not be in the future (5 min skew allowed) or more than 30 days
  back, and a second feeding within 30 minutes of an existing one is a 409 rather than a
  silent no-op.
- **Deletes are soft, and the unique index on (user, name) is partial** (`WHERE deleted_at IS
  NULL`) — retiring "Bubbles" frees the name, but the feeding history survives, so
  delete-and-recreate cannot farm achievements later.
- Another user's starter returns **404, not 403** — existence is not disclosed.

## Proofing (Phase 3)

`/api/v1/proofing` — `POST /estimate` (preview without committing), session start/complete/abort,
`POST /sessions/{id}/checks`, and `GET /sessions/active` for live countdowns. The model lives in
[app/services/fermentation.py](app/services/fermentation.py) as pure functions.

    rate = base_rate * Q10^((T - T_ref)/10) * (inoculation/ref)^k * vigour
    eta  = target_rise_fraction / rate

- **Every coefficient is configuration, not a constant** (`FERMENT_*` in `.env`). The model is
  wrong until calibrated against real data, so tuning must not require a code change.
- **Q10 is piecewise — steeper below 15°C — and continuous at the threshold.** A single Q10
  across 4–30°C badly under-predicts retard; with the split, a 4°C fridge runs ~13× slower than
  24°C, which matches how an overnight retard actually behaves.
- **Rise is modelled as linear in time.** Real dough accelerates then plateaus. The
  approximation holds over one proof window, and every check re-fits it — which is what
  actually keeps a long proof honest.
- **Checks blend observation with the model**, weighted `n/(n+1)` toward the dough as checks
  accumulate. A check inside the first 15 minutes is ignored for rate purposes: dough barely
  moves early, so an inferred rate would be noise.
- **Predictions are a window, never a bare timestamp.** The spread starts at ±35% and narrows
  with checks but never reaches zero — the model does not earn certainty because someone looked
  at the dough four times. Note the window is a fraction of *remaining* time, so it tightens
  largely because less time is left, not because confidence spiked.
- **Vigour is measured, not asserted.** It comes from the starter's own peak observations
  (median of the last 8, temperature-normalised so a hot kitchen isn't mistaken for a lively
  starter), clamped to 0.5–2.0, and snapshotted onto the session as `vigour_used` so an old
  prediction stays explicable.
- **`autolyse` is time-based, not predicted.** A rest has a fixed length; its window has zero
  spread rather than fake precision.
- `predicted_end_at` is the single field **Phase 7 will schedule the "dough is ready" reminder
  from**, and re-fits update it in place so rescheduling has one thing to watch.

## Recipes, bakes and photos (Phase 4)

`/api/v1/recipes` (CRUD, `/public` browse, `/scale`, `/fork`, `/star`), `/api/v1/bakes`
(CRUD, `/complete`, `/rating`, `/photos`, `/proof-sessions`) and `/api/v1/media`.

- **Recipes are stored as baker's percentages only; grams are never persisted.** Weight is a
  function of the batch size the baker picks, so storing it would create a second source of
  truth that drifts the first time a recipe is scaled. The flour must sum to exactly 100%
  (±0.5, so `33.3/33.3/33.4` is accepted) — that invariant is what makes every other
  percentage meaningful.
- **Both hydrations are reported.** A recipe written at 70% with a 20% levain is really at
  72.7%, because the levain is flour and water too. `stated_hydration_pct` is what the recipe
  says; `true_hydration_pct` splits the starter using `starter_hydration_pct` and counts it.
- **A fork is a copy, not a link.** It starts private at version 1 and remembers its parent;
  editing the parent afterwards does not touch it. `version` bumps only when the *formula*
  changes, so a fork can tell whether the original has moved on. Forking your own recipe does
  not increment `fork_count`.
- **A bake snapshots the formula it was baked with** rather than referencing the live recipe,
  and survives the recipe's deletion (`ON DELETE SET NULL`). Editing a recipe must not rewrite
  what you actually baked last month.
- **The API never handles image bytes.** Clients get a presigned **POST** (not PUT — only POST
  supports a `content-length-range` condition, so the 10 MB cap is enforced by storage rather
  than trusted from the client) and upload straight to MinIO.
- **Object keys embed the owner id** (`u/{user_id}/{purpose}/{uuid}.ext`) and are checked
  before attachment, so one user cannot attach another's upload. Attaching also HEADs the
  object, so a fabricated key for an upload that never happened is rejected. Objects are
  private; reads go through time-limited signed URLs.
- `MINIO_PUBLIC_ENDPOINT` must be set in any real deployment — presigned URLs are handed to
  browsers and phones, which cannot resolve the compose-internal `minio` hostname.

## Inventory and costing (Phase 5)

`/api/v1/inventory` — items, a per-item transaction ledger, `/low-stock` and `/cost-report`.
Completing a bake draws its flour from stock and costs it.

- **There is no `quantity_on_hand` column.** On-hand is the sum of the ledger, the same way a
  streak is derived from feedings: a stored counter and a transaction history are two sources
  of truth that eventually disagree, and when they do it is the counter that is wrong.
- **Valuation is weighted average, and the average is stamped onto each consumption.** Without
  the stamp, buying cheaper flour next month would silently rewrite what last month's loaves
  cost. FIFO would be more precise but needs lot tracking, for a difference smaller than the
  scale error on a home baker's balance.
- **Quantities are always positive magnitudes; the sign comes from the transaction kind**, so
  a negative "consume" cannot quietly become a stock increase. Only `adjust` may go either way
  (via `decrease`), because a stock count can correct in both directions.
- **Consumption prices are never accepted from the client** — a purchase requires a price, a
  consumption refuses one.
- **Partial costs are reported as no cost at all.** If a blend names a flour with no matching
  inventory item, that flour appears in `unmatched` and `flour_cost` stays null. A figure that
  quietly excludes 20% of the flour reads as the real cost and is worse than nothing.
- **Stock may go negative, and a bake is never blocked by inventory.** The bread was baked
  whether or not the ledger agrees; the ledger is the thing that is wrong.
- **Only flours are consumed.** Salt and inclusions are a rounding error against flour, and
  guessing which item a recipe meant by "seeds" would produce a confidently wrong number —
  hence `flour_cost`, not `ingredient_cost`.
- `inventory_consumed_at` on the bake makes consumption single-shot, so a replay cannot
  double-draw stock.
- Everything is grams and cost-per-kg. Water comes from the tap and is not inventoried.

## Gamification (Phase 6)

`/api/v1/gamification` (tier, achievements, XP history) and `/api/v1/leaderboard`
(six category boards, `/me`, admin `/refresh`). 44 achievements across 19 metrics.

- **XP is an append-only ledger, unique on `(user, rule, source_type, source_id)`.** That one
  constraint buys idempotence — a retry, a replay or a double-tap awards once, and two
  concurrent requests cannot both pass a check and both insert, because the insert *is* the
  check. It also buys recomputability: `sdt recompute-xp` throws the ledger away and re-derives
  it from the underlying bakes, feedings and proofs.
- **Replay is faithful, not approximate.** Events replay in chronological order through the same
  `award()` as live play, backdated so they land in the season and daily bucket they belong to.
  Caps are per **UTC calendar day** rather than a rolling 24 hours precisely so replay can
  reproduce them exactly — a sliding window could not.
- **Achievements are declarative**: a metric, a target, and the events that could move it.
  Listing the events keeps the engine cheap (logging a feeding does not re-evaluate 44 badges),
  and every metric is a plain aggregate, so a badge is always derivable from first principles
  rather than from a counter someone remembered to increment. Unit tests assert every
  achievement has a working metric and is reachable from some event.
- **The engine runs a second pass after any award**, because "earn 10 badges" is itself a badge
  and would otherwise sit unearned until an unrelated event happened along.
- **Anti-cheat**: daily caps per rule (set above a plausible baking day — the action still
  succeeds, it just stops paying); the flagship hydration badges require a photo, not just a
  typed number; hydration badges also require the loaf to have been rated 4+, so claiming 95%
  on a brick earns nothing; suspended and deleted accounts never appear on a board.
- **Tiers are lifetime XP; seasons are quarterly and derived from the calendar**, so a season can
  never fail to exist because nobody rolled it over, and a newcomer can win a board without
  facing three years of accumulated total.
- **A private profile still ranks, but anonymously.** Opting out of a public profile is not
  opting out of competing, and must not leak a name the user chose not to publish.
- **Leaderboards read one periodically-refreshed rollup** (beat cron, every 5 minutes) rather
  than aggregating history per page view. The plan floated a Redis sorted set in front of it;
  that is deliberately not built — the rollup is already a cache, and a second one would be a
  third copy of the truth for no gain at this size.
