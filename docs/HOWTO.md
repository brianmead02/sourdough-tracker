# How-to

Task-oriented recipes. Two audiences: **operators** running an instance, and
**bakers** (or client developers) using the API.

Assumes `$AUTH` holds `authorization: Bearer <access_token>` — see
[QUICKSTART.md](QUICKSTART.md).

---

# For operators

## Promote someone to admin

There is no self-service promotion. Create one directly:

```bash
docker compose exec api sdt create-admin
```

Admin accounts are created **pre-verified** — they are made out-of-band by an
operator, so there is no email round-trip to complete. The only admin-gated
endpoint today is `POST /leaderboard/refresh`; the moderation surface arrives in
Phase 10.

## Reset a user's password

Trigger the normal recovery flow rather than editing the hash:

```bash
curl -X POST https://your-host/api/v1/auth/forgot-password \
  -H 'content-type: application/json' -d '{"email":"them@example.com"}'
```

This deliberately returns the same response whether or not the address exists.
Confirm delivery in `docker compose logs worker`. A completed reset signs out
**all** of that user's sessions.

## Force a session logout

Password reset and password change both revoke every refresh token. To cut a
single suspicious session, the user's client can call `POST /auth/logout` with
that refresh token. To cut *all* sessions for a user without their cooperation,
suspend them:

```sql
UPDATE "user" SET is_suspended = true, suspended_reason = 'abuse report #12'
WHERE email = 'them@example.com';
```

Suspension is checked **per request**, so it takes effect before the current
15-minute access token expires — no waiting. Suspended users also drop off
leaderboards on the next rollup, and their public recipes disappear from browse.

## Fix a stale or empty leaderboard

The board is a rollup refreshed every five minutes by `beat`.

```bash
docker compose exec api sdt refresh-leaderboard
docker compose logs beat | grep leaderboard      # is the cron firing?
```

## Fix badges stuck at 100% but unearned

Achievements evaluate on events, so history created before a badge existed is not
retroactively awarded.

```bash
docker compose exec api sdt recompute-xp --yes
```

Destructive and idempotent: it deletes the ledger and replays every user's
history chronologically. Take a database backup first if the instance matters.

## Rebalance XP or achievement targets

1. Edit rates in `app/services/events.py` or targets in
   `app/services/achievements/definitions.py`.
2. `docker compose exec api sdt seed-achievements`
3. `docker compose exec api sdt recompute-xp --yes`

History is re-derived, not patched. This is the entire reason the ledger is
append-only and source-keyed.

## Tune the fermentation model

Every coefficient is configuration, so this needs no code change. Add to `.env`:

```bash
FERMENT_BASE_RISE_PER_HOUR=0.15   # 75% rise in 5h at reference conditions
FERMENT_Q10_WARM=2.0              # rate multiplier per +10C
FERMENT_Q10_COLD=3.0              # steeper below the threshold
FERMENT_COLD_THRESHOLD_C=15.0
FERMENT_INOCULATION_EXPONENT=0.7  # sub-linear: 2x starter is not 2x speed
```

Restart the API, then sanity-check across the range:

```bash
for t in 28 24 20 15 4; do
  curl -s -X POST localhost:8000/api/v1/proofing/estimate -H "$AUTH" \
    -H 'content-type: application/json' \
    -d "{\"stage\":\"bulk\",\"dough_temp_c\":$t}" | jq -c '{t:'$t', hours}'
done
```

Sanity anchors at the shipped coefficients: a 75% bulk rise is **5.0 h at 24 °C**
and **31.2 h at 4 °C** — a **6.2×** slowdown. A flat Q10 would give only 4×, which
is why the curve is piecewise. If your cold predictions still come out short,
raise `FERMENT_Q10_COLD`; these numbers are a starting point, not measured truth.

Changing coefficients does **not** rewrite existing sessions — each stores the
`vigour_used` and window it was created with, so old predictions stay explicable.

## Inspect the database

```bash
docker compose exec postgres psql -U sourdough -d sourdough

\dt                                    -- 23 tables
SELECT rule_code, count(*), sum(amount) FROM xp_event GROUP BY 1 ORDER BY 3 DESC;
SELECT code, count(*) FROM user_achievement JOIN achievement ON code = achievement_code
  GROUP BY 1 ORDER BY 2 DESC LIMIT 10;   -- which badges are actually earned
```

That last query is the one to watch when balancing: a badge nobody has is either
too hard or unreachable.

---

# For bakers and client developers

## Keep a fridge starter without breaking its streak

Streaks count **scheduled intervals, not calendar days**. Set the interval to
match how you actually keep it:

```bash
curl -X PATCH .../starters/$ID -H "$AUTH" -H 'content-type: application/json' \
  -d '{"state":"fridge","feed_interval_hours":168}'
```

A weekly feed now sustains the streak. A feed may also be up to 1.5× late and
still count.

To pause entirely without penalty, set `"state":"dormant"` — dormant and retired
starters leave the schedule and cannot go overdue.

## Work out what a feed should weigh

```bash
curl -X POST .../starters/$ID/suggested-feed -H "$AUTH" \
  -H 'content-type: application/json' -d '{"total_g":250}'
```

Give **exactly one** of `starter_g` (I have this much starter) or `total_g` (I
want this much levain).

## Get an accurate proof prediction

The model starts from a generic starter. It gets specific once it can measure
yours:

1. Log a feeding.
2. When the starter peaks, log an observation **linked to that feeding**, with
   `peaked: true` and a `dough_temp_c`.

```bash
curl -X POST .../starters/$ID/observations -H "$AUTH" -H 'content-type: application/json' \
  -d '{"feeding_id":"'$FEEDING'","peaked":true,"rise_multiple":2.5,"dough_temp_c":24}'
```

After a few of these, `vigour_used` on new proof sessions moves off 1.0 and the
predictions follow. Vigour is temperature-normalised, so peaking fast in a hot
kitchen is not mistaken for a lively starter.

**Check in during a proof.** Each check re-fits the ETA against what the dough is
actually doing, weighted increasingly towards observation. Checks in the first 15
minutes are ignored for rate purposes — dough barely moves that early.

## Understand the two hydrations

```bash
curl ".../recipes/$ID/scale?flour_g=1000" -H "$AUTH"
```

```json
{ "stated_hydration_pct": 70.0, "true_hydration_pct": 72.7,
  "total_flour_g": 1100.0, "total_water_g": 800.0 }
```

**Stated** is what the recipe says: water ÷ added flour. **True** counts the
levain, which is itself flour and water. A recipe "at 70%" with a 20% levain is
really a 72.7% dough — which is why it handles wetter than the number suggests.

Set `starter_hydration_pct` on the recipe if you keep a stiff levain; a 50%
levain brings proportionally more flour and lowers true hydration.

## Scale a recipe to a specific loaf

```bash
# Two 900 g loaves
curl ".../recipes/$ID/scale?dough_weight_g=1800&loaf_count=2" -H "$AUTH"

# Or: I have exactly 500 g of flour
curl ".../recipes/$ID/scale?flour_g=500" -H "$AUTH"
```

Grams are never stored — they are computed from the percentages every time, so
scaling can never disagree with the formula.

## Fork someone's recipe and make it yours

```bash
curl ".../recipes/public?q=rye&sort=stars" -H "$AUTH"
curl -X POST .../recipes/$THEIRS/fork -H "$AUTH"
```

A fork is a **copy, not a link**: private, version 1, remembering its parent.
Changes the original author makes later do not touch it. Their `fork_count` goes
up, which credits them — and pays them XP, not you.

## Cost your loaves

1. Create an inventory item per flour, **named to match your `flour_blend` keys**
   (matching is case-insensitive but otherwise exact).
2. Record purchases with `unit_cost_per_kg`.
3. Give the bake a `total_flour_g` and a `flour_blend`.
4. Complete it.

```json
"inventory": { "consumed": [{"item_name": "bread flour", "grams": 800, "cost": 1.60}],
               "unmatched": ["rye"], "total_cost": null }
```

`unmatched` means a flour in the blend has no inventory item. When anything is
unmatched, **`total_cost` is deliberately null** — a figure that quietly excludes
20% of the flour reads as the real cost and is worse than none. Add the missing
item and the next bake costs correctly.

Stock is allowed to go negative. The bread was baked whether or not the ledger
agrees; correct it with an `adjust` transaction.

## Log a bake without inventory

```bash
curl -X POST .../bakes/$ID/complete -H "$AUTH" \
  -H 'content-type: application/json' -d '{"consume_inventory":false}'
```

## Earn the photo-gated badges

`hydration_85` and `hydration_95` require **both** a bake at that hydration rated
4 or better **and** at least one photo on your account. Numbers alone do not earn
them.

Progress shows 100% as soon as the numbers qualify; the award lands on the next
qualifying event after a photo exists — re-saving the rating is enough.

## Find your rank

```bash
curl .../leaderboard/me -H "$AUTH"
```

Use this rather than paging `/leaderboard` — the board spans every account on the
service, so a page of the top 25 is not where a specific baker will be. `/me`
returns your rank plus two neighbours either side.

Six boards exist so no single metric dominates:
`?category=xp|lifetime|bakes|streak|crumb|achievements`. Someone who bakes rarely
but keeps an immaculate starter still has a board to top.

**Keeping your profile private does not remove you from the boards** — you appear
as "Anonymous Baker" with your score intact. You always see your own name.
