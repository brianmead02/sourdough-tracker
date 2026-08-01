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

**All ten phases are built and verified.** A feature-complete server, an
installable web app at `/`, an Android app that builds to a real APK, and the
operational surface — moderation, backups, data export and erasure — to run it
for other people.

| Phase | State |
|---|---|
| 0 · Scaffold | ✅ Compose stack, migrations, CI, `sdt` CLI |
| 1 · Identity | ✅ Registration, rotating refresh tokens, roles, rate limiting |
| 2 · Starters | ✅ Starters, feedings, observations, schedule, derived streaks |
| 3 · Proofing | ✅ Sessions, checks, fermentation model, live ETAs |
| 4 · Recipes & bakes | ✅ Baker's percentages, scaling, fork/star, ratings, photos |
| 5 · Inventory | ✅ Transaction ledger, bake consumption, per-loaf costing |
| 6 · Gamification | ✅ XP ledger, tiers, 44 achievements, seasons, leaderboards |
| 7 · Notifications | ✅ Scheduler + Web Push / email / ntfy / in-app |
| 8 · PWA | ✅ Installable web app, offline outbox, Web Push; redesigned (see [WEB-REDESIGN-PLAN.md](WEB-REDESIGN-PLAN.md)) |
| 9 · Flutter Android | ✅ Builds a real APK; analyze + 16 tests green |
| 10 · Hardening | ✅ Admin & moderation API, backup script, export + erasure, load test, per-test DB isolation |

Open **http://localhost:8000** for the app, or `/docs` for the API.

## By the numbers

| | |
|---|---|
| Endpoints | 101 |
| Database tables | 28 |
| Migrations | 7 |
| Achievements | 44 across 19 metrics |
| Tests | 288 unit + 262 integration + 27 browser-logic + 16 Dart |
| Lines of Python | ~15,600 including tests |
| PWA payload | ~108 KB uncompressed, no build step |

## Verification

Nothing in these documents is asserted from memory. Endpoint and table counts
come from the running service; the Quickstart's numbers are produced by a script
that walks it end to end; the Android app is confirmed by `flutter analyze`, its
tests, and a real APK build.

What is **not** verified, and is flagged where it matters: the visual rendering
of either client, the PWA install prompt, and a push notification arriving on a
physical device.

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
