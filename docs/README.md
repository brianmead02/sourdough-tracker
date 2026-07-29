# Documentation

| Document | Read it when |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | You want it running, with real data in it, in five minutes |
| [ARCHITECTURE.md](ARCHITECTURE.md) | You want to know how it works — and why it works that way |
| [API.md](API.md) | You are writing a client and need the semantics a schema cannot express |
| [HOWTO.md](HOWTO.md) | You have a specific task: promote an admin, tune the model, cost a loaf |
| [DEPLOYMENT.md](DEPLOYMENT.md) | You are putting it on the internet |
| [DEVELOPMENT.md](DEVELOPMENT.md) | You are changing the code |
| [PLAN.md](PLAN.md) | You want the original phased plan and estimates |

## Where things stand

Phases 0–6 are built and verified. The server is feature-complete **except for
notifications**, and there is **no user interface yet**.

| Phase | State |
|---|---|
| 0 · Scaffold | ✅ Compose stack, migrations, CI, `sdt` CLI |
| 1 · Identity | ✅ Registration, rotating refresh tokens, roles, rate limiting |
| 2 · Starters | ✅ Starters, feedings, observations, schedule, derived streaks |
| 3 · Proofing | ✅ Sessions, checks, fermentation model, live ETAs |
| 4 · Recipes & bakes | ✅ Baker's percentages, scaling, fork/star, ratings, photos |
| 5 · Inventory | ✅ Transaction ledger, bake consumption, per-loaf costing |
| 6 · Gamification | ✅ XP ledger, tiers, 44 achievements, seasons, leaderboards |
| 7 · Notifications | ⬜ Scheduler + Web Push / email / ntfy / in-app |
| 8 · PWA | ⬜ The web interface |
| 9 · Flutter Android | ⬜ |
| 10 · Hardening | ⬜ Admin & moderation, backups, data export, load testing |

**Today the only way to use the service is the API** — via Swagger at
`/docs`, or an HTTP client.

## By the numbers

| | |
|---|---|
| Endpoints | 75 |
| Database tables | 23 |
| Migrations | 6 |
| Achievements | 44 across 19 metrics |
| Tests | 152 unit (no I/O) + 159 integration (live Postgres, Redis, MinIO) |
| Lines of Python | ~12,600 including tests |

## The five ideas worth knowing

If you read nothing else, these explain most of the codebase:

1. **Derive, do not store.** Streaks, hydration, gram weights, stock on hand and
   achievement progress are all computed from the rows that cause them. A counter
   and a history eventually disagree, and the counter is always the one that is
   wrong.
2. **One unique constraint carries the XP system.**
   `(user, rule, source_type, source_id)` makes awards idempotent *and* makes the
   whole ledger rebuildable from scratch, so rules can be rebalanced without
   inventing history.
3. **Ownership returns 404, never 403.** A 403 confirms the row exists.
4. **The API never touches image bytes.** Clients upload straight to object
   storage with a presigned POST, so the size cap is enforced by storage rather
   than trusted from the client.
5. **Predictions are windows, not timestamps.** The fermentation model is wrong
   until it is calibrated, so it says so — and every coefficient is configuration,
   not a constant.
