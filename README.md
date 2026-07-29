# Sourdough Tracker

Multi-tenant sourdough service: starter management, live proofing predictions, bake logs,
shareable recipes, flour inventory/costing, and XP + achievements + seasonal leaderboards —
with reminders over Web Push, email, ntfy and in-app.

Full design: [docs/PLAN.md](docs/PLAN.md). **Current state: Phase 3 (proofing) complete.**

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
