# Sourdough Tracker

Multi-tenant sourdough service: starter management, live proofing predictions, bake logs,
shareable recipes, flour inventory/costing, and XP + achievements + seasonal leaderboards —
with reminders over Web Push, email, ntfy and in-app.

Full design: [docs/PLAN.md](docs/PLAN.md). **Current state: Phase 0 (scaffold) complete.**

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
