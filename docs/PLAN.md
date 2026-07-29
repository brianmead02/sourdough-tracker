# Sourdough Tracker — Build Plan

A public, multi-tenant sourdough service: starter management, live proofing, bake logs,
recipe sharing, flour inventory/costing, XP + achievements + seasonal leaderboards, and
reminders over four channels. Deployed as a `docker-compose` stack, consumed by a PWA and
a Flutter Android app.

> **Scope note:** the request said "a python script." What's actually needed here is a
> service — an HTTP API, a background worker, a scheduler, and two clients. The plan below
> builds that, and folds the "script" instinct into a single `sdt` CLI (Typer) for admin
> and batch operations (`sdt seed-achievements`, `sdt recompute-xp`, `sdt create-admin`).

---

## 1. Decisions locked in

| Question | Answer |
|---|---|
| Audience | Public multi-tenant, open signup, service-wide ranking |
| Domain | Starters, **proofing (first-class)**, bakes, recipes, inventory/costs |
| Clients | PWA **and** Flutter Android, both in scope |
| Reminders | Web Push (VAPID), Email (SMTP), ntfy, In-app — all four |
| Ranking | XP + lifetime tiers + seasonal leaderboards + achievements |
| Media | MinIO in-stack, S3-compatible, presigned uploads |
| Auth | Email + password (JWT), plus admin/moderator roles |
| Social | Public profiles + forkable public recipes (no feed/comments in v1) |

## 2. Stack

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg, Alembic.
**Data** — PostgreSQL 16 (primary), Redis 7 (queue, leaderboard cache, rate limits).
**Jobs** — ARQ (async-native, Redis-backed) for the worker; a 60-second beat tick that drains
a `scheduled_notification` table. See §6 for why a table beats an in-process scheduler.
**Media** — MinIO, presigned `PUT` direct from client, API never touches image bytes.
**Web** — Alpine.js + Tailwind, no build step, ES modules, **vendored locally** in `web/vendor/`
(no CDN dependency — matches the offline-dependency approach used elsewhere). PWA manifest +
service worker + Web Push.
**Mobile** — Flutter (Riverpod, dio). Dart API client generated from the OpenAPI schema so it
can't drift from the backend.
**Edge** — Caddy for TLS + static + reverse proxy.

### Repo layout

```
app/
  main.py                 FastAPI app factory, lifespan, middleware
  config.py               pydantic-settings, env-driven
  db.py                   engine, session, base
  cli.py                  Typer entrypoint  ->  `sdt ...`
  models/                 SQLAlchemy: user, starter, proof, bake, recipe, inventory, gamify, notify
  schemas/                Pydantic request/response
  api/v1/                 routers: auth, starters, proofing, bakes, recipes, inventory,
                          gamification, leaderboard, notifications, media, admin
  services/               business logic, kept out of routers
    fermentation.py       proof ETA model  (§5)
    achievements/         rule registry + rule classes
    xp.py                 ledger, tiers, season rollover
    notify/               Notifier ABC + webpush/email/ntfy/inapp backends
    storage.py            Storage ABC + MinIO/S3 impl
    events.py             domain event bus -> achievement + notification hooks
  worker/                 ARQ settings, task functions, beat tick
migrations/               Alembic
web/                      PWA (index.html, js/, css/, vendor/, sw.js, manifest.json)
mobile/                   Flutter app
docker/                   Dockerfiles, Caddyfile, minio-init
tests/
docker-compose.yml  docker-compose.dev.yml  .env.example
```

## 3. Data model

Every user-owned table carries `user_id` and is filtered by a dependency-injected current
user — multi-tenancy is enforced in one place, not per-query. Soft delete (`deleted_at`) on
user content so achievements/XP can't be farmed by create-delete loops.

**Identity** — `user`, `user_profile` (display name, bio, avatar, public flag, timezone),
`refresh_token` (rotating), `email_verification`, `password_reset`, `role` (user/moderator/admin).

**Starters**
- `starter` — name, flour type, birthday, hydration %, feed ratio (e.g. 1:5:5), feed interval
  hours, state (`active` / `fridge` / `dormant` / `retired`), avatar photo.
- `feeding` — fed_at, flour_g, water_g, starter_g, flour blend (JSONB), ambient temp, notes.
- `starter_observation` — peak time, rise multiple, float test, aroma, photo.
- Streaks are **derived** from `feeding`, not stored as a mutable counter (recomputable, harder to cheat).

**Proofing** (the piece that makes this more than a diary)
- `proof_session` — stage (`levain` / `autolyse` / `bulk` / `shaped` / `retard`), started_at,
  dough temp, ambient temp, starter %, hydration %, target rise %, `predicted_end_at`,
  actual_end_at, status (`running` / `done` / `aborted`), optional `bake_id`.
- `proof_check` — timestamp, observed rise %, dough temp, poke-test result, photo. Each check
  re-fits the ETA (§5) and reschedules the reminder.

**Bakes**
- `bake` — recipe ref, title, timeline of steps (JSONB), total flour, hydration/salt/starter %,
  flour blend, oven temp, bake minutes, vessel, scoring.
- `bake_rating` — crumb, oven spring, crust, sourness, overall (1–5), notes.
- `bake_photo` — object key, kind (`crumb` / `crust` / `shaped` / `proof`), sort order.

**Recipes**
- `recipe` — owner, name, description, `is_public`, `forked_from_id`, version, default dough
  weight, tags, star count.
- `recipe_ingredient` — name, kind (`flour` / `liquid` / `salt` / `starter` / `inclusion`),
  baker's percentage, `is_flour` (percentage base = total flour weight).
- Scaling is computed, never stored: choose a dough weight or loaf count → gram quantities.

**Inventory**
- `inventory_item` — name, kind, unit, qty on hand, low threshold, average cost/kg.
- `inventory_transaction` — append-only delta ledger (`purchase` / `consume` / `adjust`),
  unit cost, optional source bake. On-hand quantity is the ledger sum, so cost basis and
  history are auditable. Completing a bake consumes against the recipe's flour blend and
  stamps a per-loaf cost.

**Gamification**
- `achievement` — code, name, description, category, rarity, XP award, icon, criteria (JSONB), seasonal flag.
- `user_achievement` — earned_at, progress (JSONB) so partially-complete badges show a bar.
- `xp_event` — append-only ledger: user, source type/id, rule code, amount, season.
  **Unique on (user_id, rule_code, source_type, source_id)** → awards are idempotent and the
  whole ledger can be recomputed from scratch after a rule change.
- `season` — name, starts_at, ends_at.
- `leaderboard_entry` — (season_id, user_id, xp, rank), refreshed by the worker; Redis sorted
  set fronts it for reads.

**Notifications** — `notification_channel`, `notification_preference`,
`scheduled_notification`, `notification_log`. Detail in §6.

## 4. API surface (`/api/v1`)

```
auth/         register, verify-email, login, refresh, logout, forgot/reset password, me
starters/     CRUD, POST feedings, GET schedule, POST observations, GET streak
proofing/     POST sessions (start), POST checks, POST complete/abort, GET active
bakes/        CRUD, POST rating, POST photos:presign, POST complete
recipes/      CRUD, GET public (search/filter), POST fork, POST star, GET scale?dough_g=
inventory/    items CRUD, POST transactions, GET low-stock, GET cost-report
gamification/ GET achievements (all + mine + progress), GET xp/history, GET tier
leaderboard/  GET ?season=&category=, GET me (rank + neighbours)
profiles/     GET {handle} (public), PATCH me
notifications/ channels CRUD, prefs, GET inbox, POST read, POST webpush/subscribe, POST test
media/        POST presign-upload, POST confirm
admin/        users (suspend/ban), moderation queue, achievement seed/recompute, season control
```

OpenAPI drives the generated Dart client; the PWA calls the same endpoints, so there is
exactly one API contract to keep honest.

## 5. Fermentation / proofing model

The differentiator. A proof session predicts when dough will be ready and pushes a
notification at the right moment.

Base rate is temperature-driven with a Q10-style factor, adjusted for inoculation and
starter vigour:

```
rate  = base_rate * 2^((T_dough - T_ref) / 10)
        * (starter_pct / ref_starter_pct)^k
        * starter_vigour                      # from recent peak times on that starter
eta   = target_rise_fraction / rate
```

- All coefficients live in config, not code constants — they get tuned.
- Every `proof_check` refits `starter_vigour` and the remaining time, then **reschedules the
  pending reminder** rather than adding a second one.
- Retard (fridge) stages use the same curve at low temperature, which naturally yields the
  long flat times bakers expect.
- Confidence widens when a session has no checks; the UI shows a window, not a false-precision
  timestamp.
- Long-term: per-user calibration from completed sessions (observed vs predicted) — a stored
  per-starter multiplier, no ML needed.

## 6. Notifications & scheduling

**Why a table, not APScheduler:** per-user reminders are dynamic (a proof check moves the ETA),
must survive restarts, must not double-fire across replicas, and need an audit trail.

1. Anything that needs a future nudge writes a `scheduled_notification` row with `due_at` and a
   **`dedupe_key`** (unique) — e.g. `proof:{session_id}:ready`. Rescheduling updates the row.
2. A beat task runs every 60s and claims due rows with
   `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` → safe with multiple workers.
3. Each claimed row fans out to the user's enabled channels through a `Notifier` ABC:
   `WebPushNotifier` (pywebpush/VAPID), `EmailNotifier` (SMTP), `NtfyNotifier` (per-user topic
   + token), `InAppNotifier` (inbox row). Failures retry with backoff and land in
   `notification_log`.
4. Per-user timezone and quiet hours shift non-urgent sends; time-critical ones (proof ready,
   oven timer) ignore quiet hours by design, flagged per event type.

**Reminder catalogue:** starter feed due · starter peak expected · bulk proof ready ·
shaped proof ready · remove from retard · preheat oven · bake timer · streak about to break ·
inventory low · achievement unlocked · season ending · weekly digest.

**Android push caveat:** FCM requires a Firebase project and a Google dependency. Since ntfy is
already in the stack, the Flutter app subscribes to a per-user ntfy topic (opaque token) —
no Firebase, works on de-Googled devices. FCM stays available as a config-gated alternative.

## 7. Gamification design

**XP ledger, not a counter.** Every award is an `xp_event` row keyed to its source, so rules can
be changed and the whole ledger rebuilt (`sdt recompute-xp`) without inventing history.

- **Tiers** (lifetime XP): Novice → Home Baker → Levain Keeper → Crumb Chaser → Artisan → Master Baker.
- **Seasons** (quarterly): season XP resets, lifetime doesn't, so new users can win a board.
- **Category boards**: longest starter streak, bakes logged, average crumb rating, most-forked recipe.
- **Achievements** as a rule registry — each rule is a class with `event_types`, `evaluate(ctx)`,
  and `progress(ctx)`. Domain events (`bake.completed`, `feeding.logged`, `proof.completed`,
  `recipe.forked`) publish to the bus in `services/events.py`; the engine evaluates only rules
  subscribed to that event. Seed set of ~40: *First Loaf, Century Club (100 bakes), Unbroken
  (60-day feed streak), Hydration Hero (85%+ success), Rye Devotee, Fork Lift (recipe forked 10×),
  Night Owl, Sub-Zero (retard 24h+), Golden Ratio, Season Champion*, etc.

**Anti-cheat** — this is a public board, so it needs to survive bad-faith users:
backdating window limits, minimum plausible intervals (two feedings 5 minutes apart award once),
rate limits per endpoint, soft-delete so create/delete farming is a no-op, photo-required
achievements for the high-value badges, moderator flag + admin recompute.

## 8. Docker Compose stack

```
caddy        TLS, serves /web, proxies /api  (prod profile)
api          FastAPI (uvicorn), N replicas
worker       ARQ worker
beat         ARQ cron/beat tick
postgres     16, named volume, healthcheck
redis        7, appendonly
minio        S3 API + console, named volume
minio-init   one-shot: create bucket, set policy
mailhog      dev profile only — catches SMTP
ntfy         push server
```

Compose profiles split `dev` (hot reload, mailhog, exposed ports) from `prod` (Caddy, no
direct exposure, restart policies). All config via `.env` — DB creds, JWT secret, VAPID
keypair, SMTP, MinIO keys, ntfy base URL. `.env.example` documents every key.

## 9. Clients

**PWA** — installable, offline shell, background sync for logs written without a connection,
Web Push. Screens: Dashboard (active proofs with live countdowns, starters due today,
XP/tier strip) · Starters · Proofing · Bakes · Recipes (mine / public / forked) · Inventory ·
Achievements · Leaderboard · Profile · Settings. iOS caveat: Web Push needs iOS 16.4+ **and**
home-screen install — documented, not worked around.

**Flutter Android** — same feature set, generated Dart client, camera capture straight to
presigned MinIO upload, local notifications for timers plus ntfy for server-side pushes,
offline queue via Drift, biometric unlock for the stored refresh token.

## 10. Phases

| # | Phase | Deliverable | Est. |
|---|---|---|---|
| 0 | Scaffold | ✅ Compose stack up, FastAPI health, Alembic, CI (ruff/mypy/pytest), `sdt` CLI | 1 d |
| 1 | Identity | ✅ Register/verify/login/refresh/reset, roles, rate limiting, profiles | 2 d |
| 2 | Starters | ✅ Starters + feedings + observations, schedule, derived streaks | 2 d |
| 3 | Proofing | ✅ Sessions, checks, fermentation model, live ETA (reminder scheduling lands in Phase 7) | 2–3 d |
| 4 | Recipes & Bakes | Recipes, baker's %, scaling, fork/star, bakes, ratings, MinIO photos | 3–4 d |
| 5 | Inventory | Items, transaction ledger, bake consumption, per-loaf cost report | 2 d |
| 6 | Gamification | XP ledger, tiers, achievement registry + ~40 rules, seasons, leaderboards, anti-cheat | 3–4 d |
| 7 | Notifications | Scheduler table + beat, four notifiers, prefs, quiet hours, digests | 3 d |
| 8 | PWA | All screens, service worker, Web Push, offline queue, vendored deps | 4–5 d |
| 9 | Flutter | Generated client, all screens, camera, ntfy push, offline queue | 5–6 d |
| 10 | Hardening | Admin/moderation UI, backups, data export (GDPR), load test, docs, seed data | 2–3 d |

**~30–35 working days** for one developer at full scope. Phases 0–7 (server complete, API
usable) land around day 18.

## 11. Risks & call-outs

- **Public multi-tenancy is the expensive choice.** Email deliverability, abuse, moderation,
  and data-export obligations are all real work — most of Phase 10 exists because of it.
- **Fermentation model accuracy.** It will be wrong before it's tuned. Ship it as a window with
  confidence, collect observed-vs-predicted, calibrate per starter. Don't present it as exact.
- **XP balance** needs a live tuning pass; the recomputable ledger is what makes that safe.
- **Photo moderation** on a public service — v1 gate: photos are private until the user marks a
  bake public, and public photos enter a moderation queue.
- **iOS Web Push** and **Android-without-Firebase** both have the constraints noted above.
- **Timezones** — store UTC, render in `user_profile.timezone`; every reminder respects it.
- Two clients doubles UI work. If the timeline matters more than Android-native, Phase 9 is the
  one to defer — the PWA already installs on Android.

## 12. Open items (assumed, not asked)

1. **Deployment target** — assumed self-hosted Linux + Docker, Caddy handling TLS from a real
   domain. If this goes on a homelab behind a tunnel, Web Push still needs a valid certificate.
2. **Units** — assumed metric (g, °C) with a display-level toggle to imperial. Storage is always metric.
3. **Public recipe licensing** — forking others' recipes implies a content licence in the ToS.
4. **LLM features** — none planned (no crumb photo analysis, no recipe suggestions). Easy to add later.
