# Quickstart

From nothing to a running service with data in it. About five minutes, most of
which is Docker pulling images.

**Prerequisites:** Docker with Compose v2. Nothing else — Python, Postgres and
the rest all live in containers.

---

## 1. Start the stack

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec api alembic upgrade head
docker compose exec api sdt seed-achievements
```

Check it came up:

```bash
curl localhost:8000/api/v1/health
# {"status":"ok","version":"0.1.0","checks":{"postgres":"ok","redis":"ok"}}
```

> **Port already in use?** Every published port is overridable in `.env`
> (`API_DEV_PORT`, `POSTGRES_DEV_PORT`, `REDIS_DEV_PORT`, …). Nothing inside the
> stack depends on them; containers talk over the compose network.

| What | Where |
|---|---|
| API docs (Swagger) | http://localhost:8000/docs |
| Mailhog — catches all outbound email | http://localhost:8025 |
| MinIO console (`minioadmin` / `minioadmin`) | http://localhost:9001 |
| ntfy | http://localhost:8081 |

---

## 2. Create an account

There is no web UI yet — the PWA is Phase 8. Everything below works from
http://localhost:8000/docs, or from curl.

```bash
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"a-long-enough-password",
       "handle":"my_handle","display_name":"Me","timezone":"America/Chicago"}'
```

Open http://localhost:8025 and find the confirmation mail **addressed to the
address you registered** — Mailhog keeps every message the instance has ever
sent, so check the recipient rather than grabbing the top of the list. Delivery
happens on the worker rather than in the request, so give it a second or two; if
nothing arrives, `docker compose logs worker` will say why.

Copy the `token=` value out of the link, then:

```bash
curl -X POST localhost:8000/api/v1/auth/verify-email \
  -H 'content-type: application/json' -d '{"token":"PASTE_TOKEN_HERE"}'

curl -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"a-long-enough-password"}'
```

Keep the `access_token`. In Swagger, click **Authorize** (top right) and paste
it; every endpoint then works from the browser.

```bash
export TOKEN="paste-access-token"
export AUTH="authorization: Bearer $TOKEN"
```

Email confirmation is not optional theatre: **reads work unverified, writes do
not.** Creating anything returns 403 until the address is confirmed.

---

## 3. Keep a starter

```bash
# Create it — the feed ratio is starter:flour:water
curl -X POST localhost:8000/api/v1/starters -H "$AUTH" -H 'content-type: application/json' \
  -d '{"name":"Gerald","flour_type":"rye","ratio_starter":1,"ratio_flour":5,
       "ratio_water":4,"feed_interval_hours":24}'
```

Note the returned `id`, then feed it:

```bash
curl -X POST localhost:8000/api/v1/starters/$STARTER/feedings -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"starter_g":20,"flour_g":100,"water_g":80,"ambient_temp_c":22}'

curl localhost:8000/api/v1/starters/schedule -H "$AUTH"   # what is due, most urgent first
curl localhost:8000/api/v1/starters/$STARTER/streak -H "$AUTH"
```

Streaks count **scheduled intervals, not calendar days** — set a fridge starter's
interval to 168 hours and a weekly feed keeps its streak alive.

---

## 4. Predict a proof

Before committing to anything:

```bash
curl -X POST localhost:8000/api/v1/proofing/estimate -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"stage":"bulk","dough_temp_c":24,"starter_pct":20}'
# {"hours":5.0,"earliest_hours":3.25,"latest_hours":6.75,"rise_per_hour_pct":15.0}
```

Then run one for real, and check in on it:

```bash
curl -X POST localhost:8000/api/v1/proofing/sessions -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"stage":"bulk","dough_temp_c":25,"starter_pct":20,"starter_id":"'$STARTER'"}'

# Dough at 55% rise — the ETA re-fits against what it is actually doing
curl -X POST localhost:8000/api/v1/proofing/sessions/$PROOF/checks -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"rise_pct":55,"poke_test":"springs_back"}'

curl localhost:8000/api/v1/proofing/sessions/active -H "$AUTH"   # live countdowns
```

Try `"dough_temp_c":4` to see a retard: 31.2 h rather than 5.0 h — a 6.2×
slowdown, because the temperature curve steepens below 15 °C instead of applying
one flat Q10 (which would give only 4×).

---

## 5. Write a recipe and scale it

```bash
curl -X POST localhost:8000/api/v1/recipes -H "$AUTH" -H 'content-type: application/json' \
  -d '{"name":"Country Loaf","is_public":true,"tags":["rye"],
       "starter_hydration_pct":100,"default_dough_weight_g":1920,
       "ingredients":[
         {"name":"bread flour","kind":"flour","percentage":90},
         {"name":"whole rye","kind":"flour","percentage":10},
         {"name":"water","kind":"liquid","percentage":70},
         {"name":"salt","kind":"salt","percentage":2},
         {"name":"levain","kind":"starter","percentage":20}]}'
```

Flours must sum to exactly 100% — every other ingredient is a percentage *of the
flour*. Then scale to whatever you are actually baking:

```bash
curl "localhost:8000/api/v1/recipes/$RECIPE/scale?dough_weight_g=1800&loaf_count=2" -H "$AUTH"
```

The response gives grams per ingredient plus **two hydrations**:
`stated_hydration_pct` is 70 (what the recipe says), `true_hydration_pct` is 72.7
(what the dough actually is, once the levain's flour and water are counted).

---

## 6. Log a bake and cost it

```bash
# Stock some flour first, so the bake can be costed
curl -X POST localhost:8000/api/v1/inventory/items -H "$AUTH" -H 'content-type: application/json' \
  -d '{"name":"bread flour","kind":"flour","low_threshold_g":2000}'

curl -X POST localhost:8000/api/v1/inventory/items/$ITEM/transactions -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"kind":"purchase","quantity_g":10000,"unit_cost_per_kg":1.20}'

# Bake it
curl -X POST localhost:8000/api/v1/bakes -H "$AUTH" -H 'content-type: application/json' \
  -d '{"title":"Saturday loaf","recipe_id":"'$RECIPE'","total_flour_g":1000,
       "hydration_pct":70,"loaf_count":2,"flour_blend":{"bread flour":100}}'

curl -X POST localhost:8000/api/v1/bakes/$BAKE/complete -H "$AUTH" \
  -H 'content-type: application/json' -d '{"oven_temp_c":245,"bake_time_minutes":42}'
```

Completing a bake draws its flour from stock, stamps a per-loaf cost, pays XP and
may award achievements — all reported in the response:

```json
{ "status": "done",
  "flour_cost": 1.2, "flour_cost_per_loaf": 0.6,
  "inventory": {"consumed": [{"item_name": "bread flour", "grams": 1000, "cost": 1.2}],
                "unmatched": []},
  "xp_gained": 75,
  "awards": [{"icon": "🍞", "name": "First Loaf", "xp_award": 50}] }
```

Then rate it, and see where you stand:

```bash
curl -X PUT localhost:8000/api/v1/bakes/$BAKE/rating -H "$AUTH" \
  -H 'content-type: application/json' -d '{"overall":5,"crumb":4,"oven_spring":5}'

curl localhost:8000/api/v1/gamification/tier -H "$AUTH"
curl localhost:8000/api/v1/inventory/cost-report -H "$AUTH"
```

---

## 7. Add a photo

Three steps, because the API never handles image bytes:

```bash
# 1. Ask for an upload grant
curl -X POST localhost:8000/api/v1/media/presign-upload -H "$AUTH" \
  -H 'content-type: application/json' -d '{"content_type":"image/jpeg"}'

# 2. POST the file straight to MinIO using the returned url + fields
curl -X POST "$UPLOAD_URL" $(echo "$FIELDS" | jq -r 'to_entries|map("-F \(.key)=\(.value)")|join(" ")') \
     -F "file=@crumb.jpg"

# 3. Attach the object key to the bake
curl -X POST localhost:8000/api/v1/bakes/$BAKE/photos -H "$AUTH" \
  -H 'content-type: application/json' \
  -d '{"object_key":"'$KEY'","kind":"crumb","caption":"open crumb"}'
```

---

## Next

- [HOWTO.md](HOWTO.md) — common operator and baker tasks
- [ARCHITECTURE.md](ARCHITECTURE.md) — how and why it is built this way
- [API.md](API.md) — the full endpoint catalogue
- [DEPLOYMENT.md](DEPLOYMENT.md) — running it for real
- [DEVELOPMENT.md](DEVELOPMENT.md) — changing it

**Tear down:**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down        # keep data
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v     # delete data
```
