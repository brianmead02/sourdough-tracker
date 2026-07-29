# Deployment

Running Sourdough Tracker for real: a public, multi-tenant service on the
internet. If you only want it on your laptop, use
[QUICKSTART.md](QUICKSTART.md) instead.

> **Status.** All ten phases are complete. The server is feature-complete, a
> deployment serves the installable web app at `/` alongside the API, an Android
> APK can be built from `mobile/`, and moderation, backups, data export and
> erasure are available. There is no admin *page* — moderation is six endpoints
> under `/api/v1/admin`, documented in [HOWTO.md](HOWTO.md).

---

## 1. Requirements

| | Minimum | Comfortable |
|---|---|---|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 100 GB+ (photos grow) |
| OS | Any Linux with Docker Compose v2 | |

Also needed: a **domain name** pointing at the host (for TLS), and an **SMTP
relay** that will actually deliver mail. Registration, verification and password
reset are all email-dependent — an instance that cannot send mail cannot onboard
anyone.

---

## 2. Configure

```bash
git clone <your-repo> sourdough && cd sourdough
cp .env.example .env
```

Edit `.env`. The values that **must** change from their defaults:

```bash
ENVIRONMENT=prod

# Refuses to boot in prod with the shipped default, and must be >= 32 chars.
# python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=<48+ random characters>

POSTGRES_PASSWORD=<strong random>
MINIO_ACCESS_KEY=<strong random>
MINIO_SECRET_KEY=<strong random>

# Caddy uses this for automatic TLS; must resolve to this host.
SITE_ADDRESS=sourdough.example.com
PUBLIC_BASE_URL=https://sourdough.example.com
CORS_ORIGINS=["https://sourdough.example.com"]

# REQUIRED: presigned URLs go to browsers and phones, which cannot resolve
# the compose-internal "minio" hostname.
MINIO_PUBLIC_ENDPOINT=https://sourdough.example.com/media

# A relay that will actually deliver. Port 587 enables STARTTLS automatically.
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USER=<username>
SMTP_PASSWORD=<password>
SMTP_FROM=Sourdough Tracker <no-reply@sourdough.example.com>
```

**Web Push** needs a VAPID keypair. Without one the channel is cleanly absent —
the API reports `available: false` and refuses subscriptions rather than
accepting ones it can never deliver to:

```bash
docker compose run --rm api sdt vapid-keys   # prints the three lines to paste
```

```bash
VAPID_PUBLIC_KEY=<generated>
VAPID_PRIVATE_KEY=<generated — a secret>
VAPID_SUBJECT=mailto:admin@sourdough.example.com
```

Every other setting has a working default. `.env.example` documents all 53 of
them, with the tuning knobs commented out.

**Sanity-check the secret handling before going further:**

```bash
docker compose run --rm api sdt config    # secrets masked; confirms what loaded
```

A missing or short `JWT_SECRET` in `prod` is a startup failure, not a warning.
That is intentional.

---

## 3. Bring it up

```bash
docker compose --profile prod up -d --build
docker compose exec api alembic upgrade head
docker compose exec api sdt seed-achievements
docker compose exec api sdt check          # verifies Postgres + Redis
```

`seed-achievements` is not optional: the achievement table is a projection of
the code catalogue, and without it every badge lookup fails a foreign key.

Create the first administrator:

```bash
docker compose exec api sdt create-admin
```

Verify:

```bash
curl https://sourdough.example.com/api/v1/health
```

**Migrations are never applied automatically on boot.** Run
`alembic upgrade head` deliberately, so a rolling deploy cannot race itself.

---

## 4. What the prod profile changes

- Adds **Caddy** on 80/443: automatic TLS via Let's Encrypt, serves the PWA from
  `web/`, reverse-proxies `/api/*`, sets `X-Content-Type-Options`,
  `X-Frame-Options` and `Referrer-Policy`.
- **Does not publish** the Postgres, Redis or MinIO ports. Only Caddy is exposed.
- Drops Mailhog.

Everything else talks over the compose network.

### Serving the web app

In production Caddy serves `web/` directly and requests never reach the API. In
development the API mounts the same directory itself, so `docker compose up`
gives a working app rather than only an API — the mount is registered after the
routers, so it cannot shadow `/api` or `/docs`.

One thing to get right on a deploy: **`sw.js` must not be cached**. The API
serves it with `Cache-Control: no-cache`, and Caddy should do the same. A
service worker cached by a CDN is how a PWA gets permanently stuck on an old
release. Bump `VERSION` in `web/sw.js` on each deploy so the shell cache
invalidates.

### The Android app

`mobile/` is not deployed by this stack; it is built and distributed separately:

```bash
cd mobile
flutter build apk --release --dart-define=API_BASE_URL=https://sourdough.example.com
```

Two things that will bite:

* The **API base URL is compiled in**. A build pointing at the wrong host is a
  new build, not a setting.
* The app only permits cleartext HTTP to `10.0.2.2` and `localhost`. A real
  deployment must be **HTTPS**, or the app cannot talk to it at all.

The release APK is ~49 MB because it is a fat APK covering every ABI. Use
`flutter build apk --split-per-abi` to cut that roughly in three if you are
distributing the files directly.

### Exposing MinIO

Photos are uploaded and read **directly by clients** via presigned URLs, so the
object store must be reachable from the internet. Two options:

1. **Proxy through Caddy** (simplest). Add a `handle /media/*` block that strips
   the prefix and proxies to `minio:9000`, and set `MINIO_PUBLIC_ENDPOINT` to
   match.
2. **A separate hostname** (`media.example.com`) pointing at MinIO with its own
   TLS.

Either way, the bucket stays **private** — `minio-init` sets
`anonymous set none`, and every read is a signed URL. Do not "fix" a broken image
by making the bucket public; that would expose every user's photos.

---

## 5. Scaling

The API is stateless. Scale it horizontally:

```bash
docker compose --profile prod up -d --scale api=4
```

| Component | Scaling notes |
|---|---|
| `api` | Stateless. Scale freely. |
| `worker` | Scale freely; jobs are claimed from one queue. |
| `beat` | **Keep at 1 by preference.** Multiple replicas are safe — arq keys cron runs by timestamp, and the notification drain claims rows `FOR UPDATE SKIP LOCKED` — but there is no benefit. |
| `postgres` | Vertical first. It is the only stateful component that matters. |
| `redis` | Rarely the bottleneck; it holds a queue and rate-limit counters. |
| `minio` | Swap for real S3/R2 by pointing `MINIO_*` at them — the storage layer is S3 API only. |

**Known hot spots at scale:** `services/leaderboard.py:refresh` walks every
user's feedings to compute streaks. That is fine for thousands of users and will
need attention long before millions. The rollup runs on a worker, not in a
request, so it degrades into staleness rather than latency.

### Measuring it

`scripts/loadtest.py` drives a realistic session — create a starter, then loop
over the reads a client actually makes, plus a bake and a completion:

```bash
docker compose exec api python scripts/loadtest.py --users 25 --requests 10
```

On a single-container dev stack this returned **3025 requests from 25
concurrent users in 8.1 s — 375 req/s, zero errors**. The slowest endpoint was
`POST /starters` at p95 390 ms, which is the answer you want: creating a starter
runs the achievement evaluation, so it *should* be the expensive one. If a plain
`GET` ever tops that table, something has regressed.

One gotcha: registration is rate-limited to 5/hour **per IP**, and every virtual
baker shares one. Run it with `RATE_LIMIT_ENABLED=false` and a flushed Redis, or
you will measure the limiter. The script says so rather than silently running a
smaller test than you asked for.

---

## 6. Backups

`scripts/backup.sh` takes both stores in one pass:

```bash
./scripts/backup.sh /var/backups/sourdough
```

It writes `db-<stamp>.dump` (`pg_dump -Fc`, compressed and selectively
restorable with `pg_restore`) and `media-<stamp>.tar.gz` from the MinIO bucket.
Both are written under a `.partial` name and renamed only on success, so an
interrupted run can never leave a half-file that looks like a good backup —
which matters, because whatever reads this directory is usually picking "the
newest file".

Cron it:

```cron
17 3 * * * cd /opt/sourdough && BACKUP_KEEP_DAYS=30 ./scripts/backup.sh /var/backups/sourdough >> /var/log/sourdough-backup.log 2>&1
```

`BACKUP_KEEP_DAYS` prunes older files (default 30; `0` keeps everything).

Restore:

```bash
docker compose exec -T postgres pg_restore -U sourdough -d sourdough --clean --if-exists < db-<stamp>.dump
tar xzf media-<stamp>.tar.gz -C /tmp && mc mirror /tmp/media dst/sourdough-media
```

**Both stores or neither.** Postgres holds every row and MinIO holds the photos;
restoring one alone leaves bakes pointing at objects that are not there.

**Test a restore before you need one.** A backup you have never restored is a
hypothesis, not a backup.

Redis needs no backup: it holds a job queue and rate-limit counters, both of
which regenerate.

---

## 7. Operations

```bash
docker compose logs -f api worker beat
docker compose ps
docker compose exec api sdt check
docker compose exec api sdt db current
```

**Health endpoints for a load balancer:**

- `/api/v1/ping` — liveness. Touches nothing; use it for restarts.
- `/api/v1/health` — readiness. `503` when Postgres or Redis is unreachable; use
  it to pull an instance out of rotation.

**Scheduled jobs**, all run by `beat`:

| Job | Cadence | What it does |
|---|---|---|
| `drain_due_notifications` | every 60 s | Claims due reminders and delivers them to each channel |
| `refresh_leaderboard` | every 5 min | Rebuilds the rollup every board reads from |
| `enqueue_heartbeat` | every 15 min | Proves the beat → Redis → worker path is alive |

If reminders stop arriving, this is the first place to look:

```bash
docker compose logs beat --since 10m | grep drain
docker compose exec -T postgres psql -U sourdough -d sourdough -c "SELECT status, count(*) FROM scheduled_notification GROUP BY 1;"
```

**Upgrading:**

```bash
git pull
docker compose --profile prod build
docker compose exec api alembic upgrade head   # before restarting
docker compose --profile prod up -d
docker compose exec api sdt seed-achievements   # if the catalogue changed
```

---

## 8. Security checklist

- [ ] `JWT_SECRET` is unique, random and ≥32 characters
- [ ] `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` all changed
- [ ] `ENVIRONMENT=prod` — this also disables `/docs`
- [ ] `CORS_ORIGINS` lists only your real origins
- [ ] TLS working; HTTP redirects to HTTPS
- [ ] Database and Redis ports **not** published (the prod profile handles this)
- [ ] MinIO bucket is private; images load via signed URLs
- [ ] `.env` is not committed and is `chmod 600`
- [ ] SMTP credentials are for a dedicated sending identity, not a personal mailbox
- [ ] SPF/DKIM/DMARC configured, or verification mail lands in spam
- [ ] Backups running **and a restore tested**

Rate limiting **fails open** if Redis is unavailable — a Redis outage must not
lock everyone out of logging in. That is a deliberate trade: availability over
throttling. If you need the opposite, `app/api/deps.py:RateLimiter` is where to
change it.

---

## 9. Things that will bite you

**Presigned URLs point at the wrong host.** The symptom is uploads working from
inside the network and failing from a browser. Set `MINIO_PUBLIC_ENDPOINT`.

**Verification email never arrives.** Check `docker compose logs worker` — sends
happen in the worker, not the request. A stale worker image is the classic cause;
`api`, `worker` and `beat` share one image tag precisely to prevent that.

**Port already allocated.** The dev overlay publishes ports and can collide with
existing services. All of them are overridable in `.env`. The prod profile
publishes only 80/443.

**Leaderboard looks empty or stale.** It is a rollup. Either wait for the 5-minute
cron, or run `docker compose exec api sdt refresh-leaderboard`.

**A user's badges are stuck at 100% but unearned.** Achievements evaluate on
events, so data created before a badge existed is not retroactively awarded.
`sdt recompute-xp --yes` replays the whole ledger and fixes it. It is destructive
and idempotent — read [DEVELOPMENT.md](DEVELOPMENT.md#recomputing-the-xp-ledger)
first.
