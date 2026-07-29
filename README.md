# Sourdough Tracker

A multi-tenant sourdough service: starter management, **live proofing predictions**,
bake logs, shareable recipes, flour inventory with per-loaf costing, and XP,
achievements and seasonal leaderboards across the whole service.

Built as a `docker-compose` stack around a FastAPI backend.

**Status: phases 0–9 complete.** A feature-complete server, an installable web
app served at `/`, and an Android app that builds to a real APK. What remains is
Phase 10 — admin and moderation tooling, automated backups, data export and load
testing.

---

## Quickstart

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec api alembic upgrade head
docker compose exec api sdt seed-achievements
curl localhost:8000/api/v1/health
```

| Service | URL |
|---|---|
| **The app** | **http://localhost:8000** |
| API + interactive docs | http://localhost:8000/docs |
| Mailhog (catches all outbound email) | http://localhost:8025 |
| MinIO console (`minioadmin` / `minioadmin`) | http://localhost:9001 |
| ntfy | http://localhost:8081 |

Every published port is overridable in `.env` (`API_DEV_PORT`,
`POSTGRES_DEV_PORT`, …) — the stack is expected to run alongside services that
already own the defaults.

Registering, confirming an email, and logging your first bake:
**[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

Production, including the settings that must change:
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## Documentation

| Document | Read it when |
|---|---|
| [Quickstart](docs/QUICKSTART.md) | You want it running with real data in five minutes |
| [Architecture](docs/ARCHITECTURE.md) | You want to know how it works, and why it works that way |
| [API reference](docs/API.md) | You are writing a client |
| [How-to](docs/HOWTO.md) | You have a specific task, operator or baker |
| [Deployment](docs/DEPLOYMENT.md) | You are putting it on the internet |
| [Development](docs/DEVELOPMENT.md) | You are changing the code |
| [Plan](docs/PLAN.md) | You want the original phased plan |

---

## What it does

- **Starters** — feeding log, observations, and a schedule that understands
  fridge-kept starters. Streaks count *scheduled intervals*, not calendar days.
- **Proofing** — predicts when dough will be ready from temperature, inoculation
  and the measured vigour of your own starter, and re-fits the estimate every
  time you check on it.
- **Recipes** — baker's percentages, scaling to any batch size, forking, stars.
  Reports both *stated* and *true* hydration, the latter counting the levain.
- **Bakes** — the formula as baked, ratings, photos, and links to the proof
  sessions that produced them.
- **Inventory** — an append-only stock ledger with weighted-average costing, so
  completing a bake tells you what the loaf actually cost.
- **Gamification** — 44 achievements, XP, six leaderboard categories and
  quarterly seasons, with anti-cheat that assumes the internet is watching.
- **Two clients** — an installable PWA and an Android app, both with live proof
  countdowns, one-tap feeding, and an offline outbox so bad kitchen wifi never
  loses a feeding.
- **Reminders** — a scheduled-notification table drained every minute, delivering
  to Web Push, email, ntfy and an in-app inbox. Checking on a proof *moves* its
  reminder rather than queueing another; quiet hours defer housekeeping but never
  the dough.

## Stack

**Server** — Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 ·
Redis · ARQ · MinIO · Alembic · Caddy · ntfy

**Web** — Alpine.js, vendored. No build step, no `node_modules`, ~108 KB.

**Android** — Flutter 3.41, with the API client generated from the OpenAPI
schema so it cannot drift.

`api`, `worker` and `beat` are the same image with different commands — only
`api` declares the build, so they cannot drift apart.

## `sdt` CLI

```
sdt version | config | check          # version, resolved settings, connectivity
sdt create-admin                      # pre-verified administrator account
sdt seed-achievements                 # project the code catalogue into the DB
sdt recompute-xp --yes                # rebuild the entire XP ledger from history
sdt refresh-leaderboard               # rebuild the leaderboard rollup now
sdt vapid-keys                        # generate a Web Push keypair for .env
sdt db upgrade | downgrade | revision | current
```

## Tests

```bash
docker compose exec api pytest -q                 # 205 unit, no I/O, ~1s
docker compose exec api pytest -q -m integration  # 193 against live services
docker compose exec api sh -c "ruff check . && ruff format --check . && mypy app"
node --test web/test/app.test.mjs                 # 11 browser-logic tests
cd mobile && flutter analyze && flutter test      # 16 Dart tests
```

Integration tests are not mocked: email really lands in Mailhog, uploads really
go to MinIO and are read back byte-for-byte. The Android app is verified by
`flutter analyze`, its tests, and building an actual APK.

---

## Design in one screen

1. **Derive, do not store.** Streaks, hydration, gram weights, stock on hand and
   achievement progress are computed from the rows that cause them. A counter and
   a history eventually disagree, and the counter is always the one that is wrong.
2. **One unique constraint carries the XP system.**
   `(user, rule, source_type, source_id)` makes awards idempotent *and* the ledger
   rebuildable, so rules can be rebalanced without inventing history.
3. **Ownership returns 404, never 403.** A 403 confirms the row exists.
4. **The API never touches image bytes.** Presigned POST direct to storage, so the
   size limit is enforced by storage rather than trusted from the client.
5. **Predictions are windows, not timestamps.** The fermentation model is wrong
   until calibrated, so it says so — and every coefficient is configuration.

The reasoning behind each, and the places the implementation deliberately departs
from the original plan, is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
