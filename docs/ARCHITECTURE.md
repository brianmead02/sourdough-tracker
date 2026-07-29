# Architecture

How Sourdough Tracker is put together and, more importantly, **why**. Where a
decision could reasonably have gone the other way, the reasoning is recorded
here so it can be revisited deliberately rather than rediscovered by accident.

For the original phased plan see [PLAN.md](PLAN.md). For the endpoint catalogue
see [API.md](API.md).

---

## 1. Shape of the system

```
                    ┌──────────┐
   browser / phone  │  Caddy   │  TLS, static PWA, reverse proxy   (prod only)
        │           └────┬─────┘
        │                │ /api/*
        │                ▼
        │           ┌─────────┐         ┌──────────┐        ┌──────────┐
        │           │   api   │────────▶│ postgres │◀───────│  worker  │
        │           │ FastAPI │         └──────────┘        │   ARQ    │
        │           └────┬────┘                             └────▲─────┘
        │                │  enqueue                              │ consume
        │                ▼                                       │
        │           ┌─────────┐   arq:work                       │
        │           │  redis  │──────────────────────────────────┘
        │           └────▲────┘   arq:beat
        │                │
        │           ┌────┴─────┐
        │           │   beat   │  cron ticks only
        │           └──────────┘
        │
        └──────────▶┌──────────┐   presigned POST / GET
                    │  minio   │   (bytes never touch the API)
                    └──────────┘
```

`api`, `worker` and `beat` are **the same image with different commands**. Only
`api` declares the build, so the three can never drift apart — a rebuilt API
running against a stale worker is not a state this compose file can reach.

| Service | Role |
|---|---|
| `api` | FastAPI, stateless, horizontally scalable |
| `worker` | ARQ consumer on `arq:work` — email, leaderboard rollups, future sends |
| `beat` | ARQ cron on `arq:beat` — decides what is *due* and enqueues it |
| `postgres` | System of record |
| `redis` | Job queue and rate-limit counters |
| `minio` | S3-compatible object storage for photos |
| `ntfy` | Push server (wired up; used from Phase 7) |
| `mailhog` | Dev-only SMTP catcher |
| `caddy` | Prod-only edge: TLS, static PWA, reverse proxy |

### Why beat and worker are separate queues

arq registers cron functions under a `cron:` prefix **in the defining process
only**. If beat and the workers shared a queue, a worker could claim a cron job
it has no function for and fail with `function not found`. Beat therefore owns
`arq:beat` and explicitly enqueues real work onto `arq:work`. This is guarded by
`tests/test_worker_config.py` because it is the kind of thing that silently
regresses.

---

## 2. Layers

```
app/
  api/v1/*.py     HTTP only: auth, validation, status codes. No business rules.
  schemas/*.py    Pydantic request/response contracts + field validation.
  services/*.py   Business logic. Pure functions where the maths allows.
  models/*.py     SQLAlchemy. Tables, constraints, indexes.
  worker/         Background tasks and the beat schedule.
```

The rule that keeps this honest: **anything that is arithmetic rather than I/O
lives in `services/` as a pure function**, taking plain values instead of ORM
objects or sessions. That is why the fermentation model, streak counting,
baker's-percentage scaling and stock valuation can be tested exhaustively
without a database — and why those tests run in under a second.

| Pure module | What it decides |
|---|---|
| `services/fermentation.py` | Proof duration, temperature response, confidence windows, vigour |
| `services/starters.py` | Streaks, feeding schedule status, feed-ratio scaling |
| `services/recipes.py` | Baker's percentages, batch scaling, true vs stated hydration |
| `services/inventory.py` | Weighted-average valuation, blend splitting |
| `services/xp.py` | Tiers, quarter boundaries, award identity |

---

## 3. Data model

28 tables. Grouped by the phase that introduced them.

**Identity** — `user`, `user_profile`, `refresh_token`, `email_verification`,
`password_reset`

**Starters** — `starter`, `feeding`, `starter_observation`

**Proofing** — `proof_session`, `proof_check`

**Recipes & bakes** — `recipe`, `recipe_ingredient`, `recipe_star`, `bake`,
`bake_rating`, `bake_photo`

**Inventory** — `inventory_item`, `inventory_transaction`

**Gamification** — `achievement`, `user_achievement`, `xp_event`, `season`,
`leaderboard_entry`

**Notifications** — `notification_settings`, `notification_channel`,
`scheduled_notification`, `notification_log`, `inapp_notification`

### Derived, never stored

The single most repeated decision in this codebase. These values are computed on
read from the rows that cause them:

| Value | Derived from | Why not a column |
|---|---|---|
| Feeding streaks | `feeding.fed_at` | A counter and a history eventually disagree, and the counter is always the one that is wrong. Correcting a feeding retroactively corrects the streak. |
| Recipe gram weights | `recipe_ingredient.percentage` | Weight is a function of the batch size the baker chooses. Storing it creates a second truth that drifts the first time a recipe is scaled. |
| Recipe hydration | The feed/ingredient ratio | Storing both the ratio and the hydration lets them contradict each other. |
| Stock on hand | `inventory_transaction.delta_g` | Same argument as streaks; the ledger is also the audit trail. |
| Achievement progress | Metric aggregates | A badge must be derivable from first principles, not from a counter someone remembered to increment. |

The deliberate exceptions are `recipe.star_count` / `recipe.fork_count` (kept
denormalised so the public listing can sort without an aggregate) and
`leaderboard_entry` (a rollup, see §6). Both are rebuildable.

### Soft delete

`user`, `starter`, `recipe`, `bake` and `inventory_item` carry `deleted_at`.
Deleting hides the row but keeps the history, so delete-and-recreate cannot farm
XP later. Unique indexes on those tables are **partial** —
`WHERE deleted_at IS NULL` — so retiring a starter called "Bubbles" frees the
name without losing its feeding log.

### Tenant isolation

Every user-owned table carries `user_id`, and every read goes through an
ownership helper that filters on it. **Another user's row returns 404, not 403**:
a 403 confirms the row exists, which is itself a disclosure. Integration tests
assert this on every mutating route of every resource.

---

## 4. Request lifecycle

```
request
  → CORS middleware
  → route matched
  → RateLimiter dependency         (Redis fixed window, fails open)
  → get_current_user               (JWT → user, suspension checked per request)
  → get_verified_user              (writes only: confirmed email required)
  → schema validation              (Pydantic)
  → ownership check                (404 on someone else's row)
  → service call                   (business logic)
  → domain event published         (XP + achievements)
  → session commits on clean exit, rolls back on exception
```

Two subtleties worth knowing before editing:

**The session rolls back on any exception.** Anything that must survive an error
response has to commit itself first. The one place this matters is refresh-token
reuse detection: the family revocation is committed *before* the 401 is raised,
because otherwise the rollback would discard it and leave the stolen session
alive. This was a real bug, caught by a test.

**Suspension is checked per request, not baked into the token.** A ban must take
effect before the current 15-minute access token would have expired.

---

## 5. Authentication

- **Access tokens**: short-lived JWTs (15 min default), stateless.
- **Refresh tokens**: opaque, stored only as SHA-256 hashes, rotated on every
  use, grouped by `family_id`.
- **Reuse detection**: presenting an already-rotated refresh token means it
  leaked — the legitimate client already spent it. The whole family is revoked,
  signing out both parties.
- **No enumeration**: registration returns an identical response whether or not
  the email exists (the real owner instead gets a "someone tried to sign up"
  mail). Login spends a dummy argon2 hash when no user matches, so timing does
  not leak either.
- **Passwords**: argon2id, cost parameters in config, rehash-on-login when they
  change.
- `JWT_SECRET` must be ≥32 characters and the app refuses to boot in `prod` with
  the shipped default.

---

## 6. Gamification

The most intricate subsystem, and the one with the strongest structural
guarantee.

```
router → publish(event) → award base XP  (idempotent, daily-capped)
                        → evaluate achievements subscribed to that event
                        → second pass for "earn N badges" meta-achievements
```

**`xp_event` is append-only with a unique key on
`(user_id, rule_code, source_type, source_id)`.** That one constraint provides:

- *Idempotence* — the insert **is** the duplicate check, so two concurrent
  requests cannot both pass a check and both write.
- *Recomputability* — `sdt recompute-xp` deletes the ledger and re-derives it
  from the underlying bakes, feedings and proofs.

**Replay is faithful, not approximate.** Events replay in chronological order
through the same `award()` used live, backdated so each lands in the season and
daily bucket it belongs to. Daily caps are per **UTC calendar day** rather than a
rolling 24 hours *specifically* so replay can reproduce them exactly — a sliding
window could not, and replay would quietly pay more than normal play ever could.

**Achievements are declarative**: a metric, a target, and the events that could
move it. Listing the events keeps evaluation cheap (logging a feeding does not
re-check 44 badges about recipes). Unit tests assert that every achievement has
an implemented metric and is reachable from at least one event — a badge that
fails either is unearnable dead weight.

**Leaderboards read one rollup table**, refreshed by a beat cron every five
minutes, serving all six category boards from a single indexed scan. The plan
proposed a Redis sorted set in front of this; it is deliberately not built,
because the rollup is already a cache and a second one would be a third copy of
the truth for no measurable gain at this size. `services/leaderboard.py` is the
seam if a board ever gets slow.

### Anti-cheat

| Vector | Mitigation |
|---|---|
| Replaying the same action | Unique key on the XP ledger |
| Grinding distinct rows | Daily caps per rule, set above a plausible baking day |
| Backdating a streak | `fed_at` bounded: no future (5 min skew), no more than 30 days back |
| Double-tapping a feeding | Second feeding within 30 minutes is a 409, not a silent no-op |
| Delete/recreate farming | Soft delete keeps the history |
| Typing an impressive number | Flagship hydration badges require a photo **and** a 4+ rating |
| Suspended accounts on boards | Excluded from the rollup |

---

## 6a. Notifications

A **table drained by a beat tick**, not an in-process scheduler. Per-user
reminders move (a proof check changes the ETA), must survive restarts, must not
double-fire across replicas, and need an audit trail for "it never told me" —
none of which an in-memory scheduler gives you.

```
domain event → schedule(dedupe_key, due_at)        upsert: one row per reminder
                        ↓
beat, every 60s → claim FOR UPDATE SKIP LOCKED     safe with many drainers
                        ↓
                  quiet hours? → defer             routine only
                  too stale?   → drop
                        ↓
                  fan out to channels              independently
                        ↓
                  inapp · email · ntfy · webpush
```

**`dedupe_key` is the load-bearing idea.** One row per real-world reminder,
updated in place. A proof checked five times ends with *one* pending "dough is
ready" at the latest ETA — this is what the Phase 3 `predicted_end_at` seam was
built for. Completing or aborting a proof cancels it; feeding a starter moves its
next reminder.

**Urgency decides quiet hours.** Time-critical reminders (`proof.ready`,
`proof.retard_remove`) ignore them — dough that is ready at 3am is ready at 3am,
and deferring that delivers a useless message about a loaf that over-proofed
hours ago. Routine reminders (feed due, low stock, digest) defer to the end of
the window, judged in the user's own timezone.

**Stale reminders are dropped, not delivered late.** A "your dough is ready" six
hours after the fact is wrong, not merely late, and it teaches the baker to
distrust the next one.

**Channels are attempted independently** and a reminder counts as sent if any
succeeds — a dead Web Push subscription must not stop the inbox copy. Permanent
failures (404/410 from a push service: the browser discarded the subscription)
disable the channel rather than retrying forever; transient ones back off
exponentially over four attempts.

Two things bit during implementation and are worth knowing:

* **HTTP headers are ASCII.** ntfy carries the title in a header, and titles
  contain user text — a starter called "Gérald" or an emoji icon raises
  `UnicodeEncodeError` and loses the whole send. Titles are folded to ASCII and
  ntfy emoji are sent as *names* (`alarm_clock`), never characters.
* **Web Push imports lazily**, inside the send path, which keeps the cost off
  every request but hides a missing dependency until the first real push. A unit
  test asserts the library is importable.

---

## 7. Media

The API never touches image bytes. Clients receive a **presigned POST** and
upload straight to MinIO.

POST rather than PUT because only POST supports a `content-length-range`
condition — with PUT there is nothing preventing a 4 GB "photo". The 10 MB cap is
therefore enforced by storage, not trusted from the client, and there is a test
that uploads an oversized file and asserts the rejection.

Object keys embed the owner: `u/{user_id}/{purpose}/{uuid}.{ext}`. Attaching a
photo checks the key against the caller **and** HEADs the object, so neither
attaching someone else's upload nor fabricating a key for an upload that never
happened will work. Objects are private; reads go through time-limited signed
URLs.

> `MINIO_PUBLIC_ENDPOINT` **must** be set in any real deployment. Presigned URLs
> are handed to browsers and phones, which cannot resolve the compose-internal
> `minio` hostname.

---

## 7a. The web app

An installable PWA in `web/`, served by Caddy in production and by the API's own
static mount in development — so `docker compose up` gives a working app rather
than only an API. The mount is registered *after* the routers, so it can never
shadow `/api` or `/docs`.

**No build step, and nothing from a CDN.** Alpine.js is vendored (44 KB); the
whole shell is ~108 KB uncompressed. There is no bundler, no `node_modules`, and
no network dependency at runtime — which is what makes the offline story
possible at all.

**Hand-written CSS instead of Tailwind.** The plan specified the Tailwind browser
build, but that ships a ~400 KB runtime compiler that scans the DOM for class
names. For an app whose value is a small, instantly-cacheable shell — re-fetched
whenever the service worker version changes — that is the wrong trade. The
stylesheet is ~10 KB and does the same job. *(A deliberate deviation.)*

**Hash routing** (`#/starters`). It needs no server rewrite rule, so the app is
servable by anything, and offline navigation is free.

**Caching is split by how fast the data ages:**

| | Strategy | Why |
|---|---|---|
| App shell | cache-first | Changes only on deploy |
| API reads | network-first, small cache | A stale proof ETA or streak is worse than a spinner |
| Writes | never intercepted | They belong to the outbox; a replaying service worker would double-post |

`sw.js` is served with `Cache-Control: no-cache`. Browsers honour that for
service workers specifically, and a cached-forever `sw.js` is exactly how a PWA
gets permanently stuck on an old release.

**The offline outbox** is the part that earns its keep. A kitchen has bad wifi
and the phone is in a pocket; losing a feeding because the network blinked would
make the tracker untrustworthy. Mutations go to IndexedDB and replay oldest-first
when connectivity returns — order matters, because an observation references the
feeding before it. The drain policy is deliberate:

* network error, 5xx or 401 → **stop and keep everything**, retry later
* 4xx that is not auth → **drop that entry and continue**, because it will never
  succeed and a stuck entry blocks everything behind it

**Token refresh is collapsed to one in-flight request.** Refresh tokens rotate,
so two concurrent 401s would both rotate and the loser's token would look to the
server exactly like a replayed — i.e. stolen — token, killing the session.

Browser logic is tested with `node --test web/test/app.test.mjs`: 11 tests over
the countdown maths and the outbox drain policy, with browser globals stubbed so
the modules under test are the ones shipped. Static wiring — every referenced
asset, every precache entry, every Alpine binding resolving to something that
exists — is checked in `tests/test_pwa_assets.py`, because a missing icon or a
dangling handler fails silently in a browser.

---

## 8. The fermentation model

The feature that makes this more than a diary. See
[`app/services/fermentation.py`](../app/services/fermentation.py).

```
rate = base_rate · Q10^((T − T_ref)/10) · (inoculation/ref)^k · vigour
eta  = target_rise_fraction / rate
```

- **Every coefficient is configuration** (`FERMENT_*`), because the model is
  wrong until calibrated against real data and tuning must not need a code
  change.
- **Q10 is piecewise** — steeper below 15 °C, continuous at the threshold. A
  single Q10 across 4–30 °C makes a 4 °C fridge only **4×** slower than a 24 °C
  kitchen, which would have made every overnight retard prediction badly wrong.
  The split gives **≈6.2×** at the shipped coefficients (a 75% rise takes 5.0 h at
  24 °C and 31.2 h at 4 °C). *(A deliberate deviation from the formula in the
  plan.)* Whether 6.2× is right for real dough is exactly the sort of thing
  calibration should settle — raise `FERMENT_Q10_COLD` to steepen it further.
- **Rise is linear in time.** Real dough accelerates then plateaus; the
  approximation holds across one proof window, and each logged check re-fits it.
- **Checks blend observation with the model**, weighted `n/(n+1)` towards the
  dough. A check inside the first 15 minutes is ignored for rate purposes —
  dough barely moves early, so an inferred rate would be noise.
- **Output is a window, never a bare timestamp.** The spread starts at ±35% and
  narrows with checks but never reaches zero. Note it is a fraction of
  *remaining* time, so most apparent tightening is simply less time left.
- **Vigour is measured, not asserted**: the median of a starter's last 8
  time-to-peak observations, temperature-normalised so a hot kitchen is not
  mistaken for a lively starter, clamped to 0.5–2.0 and snapshotted onto the
  session.

---

## 9. Testing strategy

| Layer | Count | Runs against |
|---|---|---|
| Unit | 205 | Nothing — pure functions and static assets |
| Integration | 193 | Live Postgres, Redis, MinIO and ntfy |
| Browser logic | 11 | node, with browser globals stubbed |

Integration tests are marked and deselected by default (`pytest -m integration`
to run them). They exercise the real stack: real SMTP delivery into Mailhog, real
uploads into MinIO with byte-for-byte read-back, real token rotation.

**Known limitation:** integration tests share one database and do not truncate
between runs. Tests that assert on globally-shared listings (leaderboards, public
recipes) must scope to their own data or use `/me`-style endpoints, because the
shared database now holds thousands of accounts. Three tests were rewritten for
this reason. Per-test isolation is on the Phase 10 list.

---

## 10. Deliberate deviations from the plan

| Plan said | Built | Why |
|---|---|---|
| Tailwind browser build | Hand-written CSS | Tailwind's CDN build is a ~400 KB runtime compiler; the shell is 10 KB of CSS instead |
| `notification_preference` table | JSONB map on `notification_settings` | Adding a reminder type needs no migration, and an unset event falls back to its default |
| Single Q10 for fermentation | Piecewise warm/cold Q10 | A flat Q10 under-predicts retard by ~3× |
| `inventory_item.qty_on_hand` column | Derived from the ledger | A counter and a ledger drift; the ledger is also the audit trail |
| Redis sorted set for leaderboards | Rollup table only | The rollup is already a cache; Redis would be a third copy |
| Phase 3 includes reminder rescheduling | `predicted_end_at` seam only | The scheduler table is Phase 7's design; a half-built version would be worse than a clean seam |
| Bakes have `is_public` | Not built | Public bakes belong with the moderation queue in Phase 10 |

---

## 11. What is not built yet

- **Phase 9 — Flutter Android client.**
- **Phase 10 — Admin/moderation UI, backups, data export, load testing,
  per-test database isolation.**
