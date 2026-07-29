# API Reference

96 endpoints under `/api/v1`. The live, always-accurate contract is the OpenAPI
schema — this document covers the **semantics that a schema cannot express**:
which errors mean what, which operations are idempotent, and where a status code
was chosen deliberately.

- Interactive: http://localhost:8000/docs
- Machine-readable: http://localhost:8000/openapi.json

The Dart client in `mobile/` is generated from that schema
(`python scripts/generate_dart_models.py`), so a breaking change to a response
shape stops the Android app compiling rather than failing on a user's phone.

---

## Conventions

**Authentication.** `Authorization: Bearer <access_token>`. Access tokens last
15 minutes; refresh to get a new pair.

**Two levels of access.** Reads need a login. Writes additionally need a
**confirmed email address** and return `403` until then.

**Timestamps** are ISO-8601, always UTC on the wire. Users have a `timezone` on
their profile, used for display and for quiet-hours calculations.

**Status codes.**

| Code | Meaning here |
|---|---|
| `200` | Fine |
| `201` | Created |
| `202` | Accepted — used by register, which never confirms whether the email existed |
| `204` | Done, nothing to return |
| `400` | A token was invalid or expired |
| `401` | Not authenticated, or credentials rejected |
| `403` | Authenticated but not allowed — unverified email, wrong role, suspended |
| `404` | Not found **or not yours** — see below |
| `409` | Conflict: duplicate name, already-completed, double-tap |
| `422` | Validation failed |
| `429` | Rate limited; `Retry-After` header included |

> **404 vs 403 on someone else's data.** Every owned resource returns `404` when
> the caller is not the owner. A `403` would confirm the row exists, which is a
> disclosure. This is deliberate and tested on every mutating route.

**Rate limits** (per IP, fixed window, *fail open* if Redis is down):

| Endpoint | Limit |
|---|---|
| `POST /auth/register` | 5/hour |
| `POST /auth/login` | 10/15 min |
| `POST /auth/refresh` | 60/hour |
| `POST /auth/forgot-password` | 5/hour |
| `POST /auth/resend-verification` | 3/hour |
| `POST /media/presign-upload` | 60/hour |

---

## Health (2)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/ping` | Liveness. Touches nothing. Use for container healthchecks. |
| `GET` | `/health` | Readiness. Checks Postgres and Redis; `503` + per-check detail if either is down. |

---

## Auth (10)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/register` | `202`. **Identical response whether or not the email exists** — the real owner instead receives a "someone tried to sign up" mail. A handle collision *does* return `409`, because handles are public. |
| `POST` | `/auth/verify-email` | Single-use token. Second use is `400`. |
| `POST` | `/auth/resend-verification` | Generic response; only sends if the address exists and is unverified. |
| `POST` | `/auth/login` | Returns `access_token`, `refresh_token`, `expires_in`. Spends a dummy hash on unknown accounts so timing does not leak. |
| `POST` | `/auth/refresh` | **Rotates.** The presented token is revoked and a successor issued. Replaying a spent token revokes the entire family — both parties must log in again. |
| `POST` | `/auth/logout` | Revokes one refresh token. Silent on unknown tokens. |
| `POST` | `/auth/forgot-password` | Generic response, always `200`. |
| `POST` | `/auth/reset-password` | Signs out **all** sessions — a reset is a recovery action. |
| `POST` | `/auth/change-password` | Requires the current password. Also signs out all sessions. |
| `GET` | `/auth/me` | Current user + own profile. Never includes the password hash. |

---

## Profiles (3)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/profiles/me` | Your own profile, including private fields. |
| `PATCH` | `/profiles/me` | `display_name`, `bio`, `is_public`, `timezone`. **`handle` is not editable** — it appears in public URLs and on leaderboards, and renaming needs a redirect story it does not have yet. |
| `GET` | `/profiles/{handle}` | Public view. **A private profile 404s exactly like a missing one.** Never includes the email. |

---

## Starters (12)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/starters` | Feed ratio is `starter:flour:water`; hydration is derived from it. |
| `GET` | `/starters` | Includes schedule status per starter. `?include_retired=true` to see retired ones. |
| `GET` | `/starters/schedule` | **Declared before `/{starter_id}`** so it is not shadowed. Never-fed first, then most overdue. |
| `GET`&nbsp;/&nbsp;`PATCH`&nbsp;/&nbsp;`DELETE` | `/starters/{id}` | Delete is soft; the name is freed but the feeding log survives. |
| `POST` | `/starters/{id}/feedings` | `409` if another feeding is within 30 minutes. `422` if `fed_at` is in the future or >30 days back. |
| `GET` | `/starters/{id}/feedings` | Newest first, `limit`/`offset`. |
| `POST` | `/starters/{id}/observations` | `feeding_id` must belong to the same starter. Peak observations feed the vigour estimate. |
| `GET` | `/starters/{id}/observations` | Newest first. |
| `GET` | `/starters/{id}/streak` | Derived from feedings on read. |
| `POST` | `/starters/{id}/suggested-feed` | Provide **exactly one** of `starter_g` or `total_g`. |

**Schedule statuses:** `never_fed`, `ok`, `due`, `overdue`, `paused`. `overdue`
and "streak broken" are the same instant by construction.

---

## Proofing (9)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/proofing/estimate` | Preview without starting anything. `422` for time-based stages (`autolyse`). |
| `POST` | `/proofing/sessions` | Stages: `levain`, `autolyse`, `bulk`, `shaped`, `retard`. Optional `starter_id` (measures vigour) and `bake_id`. |
| `GET` | `/proofing/sessions` | `?status=running\|done\|aborted`. |
| `GET` | `/proofing/sessions/active` | **Declared before `/{session_id}`.** Adds `check_count`, `latest_rise_pct`, `progress_pct`, `hours_remaining`. |
| `GET` | `/proofing/sessions/{id}` | |
| `POST` | `/proofing/sessions/{id}/checks` | **Returns the session, not the check** — the point of checking in is the new ETA. |
| `GET` | `/proofing/sessions/{id}/checks` | Chronological. |
| `POST` | `/proofing/sessions/{id}/complete` | Optional `final_rise_pct` is recorded as a check. |
| `POST` | `/proofing/sessions/{id}/abort` | |

Any action on a finished session is `409`. Predictions are always a **window**
(`window_start_at` … `window_end_at`), never just `predicted_end_at`.

---

## Recipes (10)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/recipes` | Flours must sum to 100% (±0.5). `422` otherwise. |
| `GET` | `/recipes` | Your own. |
| `GET` | `/recipes/public` | **Declared before `/{recipe_id}`.** `?q=`, `?tag=`, `?sort=stars\|recent\|forks`. Excludes suspended and deleted accounts. |
| `GET` | `/recipes/{id}` | Yours, or anyone's public one. |
| `PATCH` | `/recipes/{id}` | Supplying `ingredients` **replaces the whole set** and bumps `version`; a partial merge would break the sums-to-100 invariant. Metadata edits do not bump the version. |
| `DELETE` | `/recipes/{id}` | Soft; also unpublishes immediately. Existing forks keep working. |
| `GET` | `/recipes/{id}/scale` | Exactly one of `dough_weight_g` or `flour_g` (defaults to the recipe's own batch size), plus `loaf_count`. Returns grams **and both hydrations**. |
| `POST` | `/recipes/{id}/fork` | A **copy**, not a link: private, version 1, remembers its parent. Editing the parent later does not touch it. Forking your own recipe does not credit `fork_count`. |
| `POST`&nbsp;/&nbsp;`DELETE` | `/recipes/{id}/star` | Idempotent both ways. `409` on starring your own. |

---

## Bakes (12)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/bakes` | `recipe_id` must be yours or public. The formula is **snapshotted**, not referenced. |
| `GET` | `/bakes` | `?status=in_progress\|done\|abandoned`. |
| `GET`&nbsp;/&nbsp;`PATCH`&nbsp;/&nbsp;`DELETE` | `/bakes/{id}` | Delete is soft. |
| `POST` | `/bakes/{id}/complete` | The big one — see below. `409` if already finished. |
| `PUT` | `/bakes/{id}/rating` | **Upsert, not merge**: omitted fields are cleared. |
| `DELETE` | `/bakes/{id}/rating` | |
| `POST` | `/bakes/{id}/photos` | Attaches a confirmed object key. `404` if the key is not yours or the object does not exist; `409` if already attached. Max 20 per bake. |
| `GET` | `/bakes/{id}/photos` | Each carries a time-limited signed `url`. |
| `DELETE` | `/bakes/{id}/photos/{photo_id}` | Also deletes the object. |
| `GET` | `/bakes/{id}/proof-sessions` | Proof sessions linked to this bake. |

**`POST /bakes/{id}/complete`** does four things and reports all of them:

```json
{ "status": "done",
  "flour_cost": 2.40, "flour_cost_per_loaf": 1.20,
  "inventory": { "consumed": [{"item_name": "bread flour", "grams": 800, "cost": 1.60}],
                 "unmatched": [], "total_cost": 2.40, "skipped_reason": null },
  "xp_gained": 75,
  "awards": [{"code": "first_loaf", "name": "First Loaf", "icon": "🍞", "xp_award": 50}] }
```

Pass `"consume_inventory": false` to skip the stock draw. **Inventory problems
never block completion** — the bread was baked whether or not the ledger agrees.

---

## Inventory (9)

| Method | Path | Notes |
|---|---|---|
| `POST`&nbsp;/&nbsp;`GET` | `/inventory/items` | Reads include derived `on_hand_g`, `average_cost_per_kg`, `stock_value`, `is_low`. |
| `GET` | `/inventory/low-stock` | At or below threshold, emptiest first. |
| `GET` | `/inventory/cost-report` | Optional `from_date`/`to_date`. Spend, consumption, stock value, cost per bake and per loaf. |
| `GET`&nbsp;/&nbsp;`PATCH`&nbsp;/&nbsp;`DELETE` | `/inventory/items/{id}` | Delete is soft; the ledger stays so past costs remain explicable. |
| `POST` | `/inventory/items/{id}/transactions` | `kind` is `purchase` \| `consume` \| `adjust`. |
| `GET` | `/inventory/items/{id}/transactions` | Newest first. |

**Transaction rules.** `quantity_g` is always a **positive magnitude**; the sign
comes from `kind`, so a negative "consume" cannot become a stock increase. A
purchase *requires* `unit_cost_per_kg`; a consumption *refuses* one — consumption
is valued from the weighted average at that moment and stamped, so later
purchases never rewrite past costs. Only `adjust` may go either way, via
`"decrease": true`.

---

## Media (2)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/media/presign-upload` | Returns `url` + `fields` for a multipart POST **straight to storage**. `422` for content types outside the allowlist. |
| `POST` | `/media/confirm` | HEADs the object; `404` if missing or not yours. |

The size cap is a storage-side condition, not a client promise — an oversized
upload is rejected by MinIO, not by trust.

---

## Gamification (3)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/gamification/tier` | Tier, lifetime and season XP, distance to next tier, badge counts. |
| `GET` | `/gamification/achievements` | All 44 with your progress. `?earned_only=true`. Sorted earned-first, then closest to completion. |
| `GET` | `/gamification/xp/history` | The ledger: every award and what caused it. |

Tiers by lifetime XP: **Novice** (0) → **Home Baker** (250) → **Levain Keeper**
(1,000) → **Crumb Chaser** (3,000) → **Artisan** (8,000) → **Master Baker**
(20,000).

---

## Leaderboard (3)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/leaderboard` | `?category=xp\|lifetime\|bakes\|streak\|crumb\|achievements`, `?season=2026 Q3`, `limit`/`offset`. Unknown season is `404`. |
| `GET` | `/leaderboard/me` | Your rank plus two neighbours either side. Works regardless of position — **use this rather than paging the board to find a specific user.** |
| `POST` | `/leaderboard/refresh` | **Admin only.** Also runs on a beat cron every 5 minutes. |

Boards read a rollup refreshed every five minutes, so `refreshed_at` may lag.
**A private profile still ranks but appears as "Anonymous Baker" with a null
handle** — you always see your own name.

---

## Notifications (13)

| Method | Path | Notes |
|---|---|---|
| `GET`&nbsp;/&nbsp;`PUT` | `/notifications/settings` | Quiet hours, per-event channel map, digest prefs. Unknown event names are `422`. |
| `GET` | `/notifications/events` | Every reminder the service sends, with its urgency and whether it ignores quiet hours. |
| `GET` | `/notifications/channels` | Configured destinations. `target` is recognisable but never reusable. |
| `GET` | `/notifications/vapid-key` | Public key for a browser to subscribe with. `available: false` means Web Push is not configured. |
| `POST` | `/notifications/webpush/subscribe` | `503` when the server has no VAPID keys — better than accepting a subscription that can never be delivered. |
| `POST` | `/notifications/channels/ntfy` | Topic + optional token. |
| `POST` | `/notifications/channels/email` | **Must be your own verified address**, else this endpoint mails strangers. |
| `DELETE` | `/notifications/channels/{id}` | |
| `POST` | `/notifications/test` | Queues a test reminder; arrives within a minute. |
| `GET` | `/notifications/inbox` | `?unread_only`. Returns items plus `unread_count`. |
| `POST` | `/notifications/inbox/read` | `{"ids": [...]}` or `{"all": true}`. |
| `GET` | `/notifications/scheduled` | What is queued for you — useful for clients, essential for debugging. |

**Re-subscribing updates in place.** Channels are keyed by a hash of their
destination, so the same browser or topic registered twice yields one row, and a
previously-disabled channel is re-enabled.

**Delivery semantics.** Reminders are queued in a table and drained by a beat
tick every 60 seconds; nothing is delivered inline. Channels are attempted
independently, so a dead push subscription cannot stop the inbox copy. A reminder
that is delivered to at least one channel counts as sent.

**Quiet hours** defer *routine* reminders to the end of the window, judged in the
user's own timezone. **Time-critical reminders ignore them** — dough that is
ready at 3am is ready at 3am. `GET /notifications/events` says which is which.

**Stale reminders are dropped, not delivered late.** A "your dough is ready" six
hours after the fact is wrong, not merely late.

---

## Admin (6)

**Moderator or admin only.** Everything here returns `403` to an ordinary user.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/admin/users` | `?q=` matches email or handle. Rows carry public-recipe and bake counts. |
| `POST` | `/admin/users/{id}/suspend` | Needs a `reason`. Takes effect on the account's **next request** and revokes every refresh token. `409` on yourself; `403` on an administrator. |
| `POST` | `/admin/users/{id}/unsuspend` | Restores access. Previously revoked tokens stay revoked. |
| `GET` | `/admin/moderation/queue` | Published recipes, `?order=newest\|most_starred`. |
| `POST` | `/admin/recipes/{id}/unpublish` | Withdraws from public view; **the author keeps their copy**. Moderation should be reversible. |
| `GET` | `/admin/stats` | Instance counts, pending/failed notifications, database size. |

An administrator cannot be suspended, and nobody can suspend themselves — one
compromised moderator should not be able to lock out the operators.

---

## Account (2)

Self-service on your own data. Any authenticated user.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/account/export` | Everything the service holds, as a JSON attachment. Photos appear as time-limited signed URLs rather than bytes. **Credentials are excluded** — a password hash is a secret, not personal data. |
| `POST` | `/account/delete` | Permanent erasure. Requires the current password **and** `confirm: "DELETE MY ACCOUNT"` exactly. |

Erasure is a **hard delete**, unlike the soft delete used elsewhere: soft
deletion exists to stop XP farming, which is not a reason to keep someone's data
after they have asked for it to go. Two things deliberately survive, because
they are not the deleting user's to erase — **forks other people made** (the
parent link is nulled, the copy stays whole) and **the star counts they
inflated**, which are decremented rather than left overstated.

---

## Errors

```json
{ "detail": "You already have a starter with that name" }
```

Validation failures use FastAPI's standard shape:

```json
{ "detail": [{ "loc": ["body", "handle"], "msg": "that handle is reserved",
               "type": "value_error" }] }
```
