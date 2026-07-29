# Deployment

Running Sourdough Tracker for real: a public, multi-tenant service on the
internet. If you only want it on your laptop, use
[QUICKSTART.md](QUICKSTART.md) instead.

> **Status.** The server is feature-complete through Phase 6 except for
> notifications (Phase 7). There is **no web UI yet** — the PWA is Phase 8, so
> today a deployment serves an API and its docs. Admin/moderation tooling,
> automated backups and data export land in Phase 10. Deploy accordingly.

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

- Adds **Caddy** on 80/443: automatic TLS via Let's Encrypt, serves the PWA,
  reverse-proxies `/api/*`, sets `X-Content-Type-Options`, `X-Frame-Options` and
  `Referrer-Policy`.
- **Does not publish** the Postgres, Redis or MinIO ports. Only Caddy is exposed.
- Drops Mailhog.

Everything else talks over the compose network.

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
| `beat` | **Keep at 1 by preference.** Multiple replicas are safe (arq keys cron runs by timestamp) but there is no benefit. |
| `postgres` | Vertical first. It is the only stateful component that matters. |
| `redis` | Rarely the bottleneck; it holds a queue and rate-limit counters. |
| `minio` | Swap for real S3/R2 by pointing `MINIO_*` at them — the storage layer is S3 API only. |

**Known hot spots at scale:** `services/leaderboard.py:refresh` walks every
user's feedings to compute streaks. That is fine for thousands of users and will
need attention long before millions. The rollup runs on a worker, not in a
request, so it degrades into staleness rather than latency.

---

## 6. Backups

Not yet automated — this is Phase 10 work. Until then, at minimum:

```bash
# Postgres — the system of record
docker compose exec -T postgres pg_dump -U sourdough sourdough | gzip > db-$(date +%F).sql.gz

# MinIO — the photos
docker run --rm -v sourdough_minio_data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/minio-$(date +%F).tar.gz /data
```

Restore:

```bash
gunzip -c db-2026-07-28.sql.gz | docker compose exec -T postgres psql -U sourdough sourdough
```

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

| Job | Cadence |
|---|---|
| `refresh_leaderboard` | every 5 min |
| `drain_due_notifications` | every 60 s (no-op until Phase 7) |
| `enqueue_heartbeat` | every 15 min |

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
