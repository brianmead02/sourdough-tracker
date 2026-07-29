"""A small load test for the endpoints that matter.

No new dependencies — httpx is already here. The point is not to produce an
impressive number but to answer two questions before a deployment:

  * which endpoint is the slowest, and is it the one you would expect?
  * does anything fall over, or start erroring, under concurrency?

Usage:
    python scripts/loadtest.py --users 20 --requests 20
    python scripts/loadtest.py --base-url https://sourdough.example.com
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid
from dataclasses import dataclass, field

import httpx


@dataclass
class Timing:
    label: str
    durations: list[float] = field(default_factory=list)
    errors: int = 0
    statuses: dict[int, int] = field(default_factory=dict)

    def record(self, seconds: float, status: int) -> None:
        self.durations.append(seconds * 1000)
        self.statuses[status] = self.statuses.get(status, 0) + 1
        if status >= 400:
            self.errors += 1

    def percentile(self, p: float) -> float:
        if not self.durations:
            return 0.0
        ordered = sorted(self.durations)
        index = min(int(len(ordered) * p), len(ordered) - 1)
        return ordered[index]

    def report(self) -> str:
        if not self.durations:
            return f"  {self.label:<34} no samples"
        mean = statistics.fmean(self.durations)
        flag = "  <-- errors" if self.errors else ""
        return (
            f"  {self.label:<34} n={len(self.durations):<5} "
            f"mean={mean:7.1f}ms  p50={self.percentile(0.5):7.1f}ms  "
            f"p95={self.percentile(0.95):7.1f}ms  p99={self.percentile(0.99):7.1f}ms"
            f"  err={self.errors}{flag}"
        )


async def provision(base: str, index: int) -> tuple[str, dict[str, str]] | int:
    """Returns (email, headers) on success, or the HTTP status that stopped it."""
    # Confirmation goes straight through Mailhog's API, which is why this is a
    # dev-stack tool: against a real instance you would seed accounts another way.
    suffix = f"{uuid.uuid4().hex[:10]}{index}"
    account = {
        "email": f"load-{suffix}@example.com",
        "password": "a-long-enough-password",
        "handle": f"load_{suffix}",
        "display_name": "Load Test",
    }
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        resp = await client.post("/api/v1/auth/register", json=account)
        if resp.status_code != 202:
            return resp.status_code

        token = None
        for _ in range(30):
            async with httpx.AsyncClient(timeout=10) as mail:
                try:
                    found = await mail.get(
                        "http://mailhog:8025/api/v2/search",
                        params={"kind": "to", "query": account["email"]},
                    )
                except httpx.HTTPError:
                    return 0
            items = found.json().get("items", [])
            if items:
                import re

                body = items[0]["Content"]["Body"].replace("=\r\n", "").replace("=3D", "=")
                match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
                token = match.group(1) if match else None
                break
            await asyncio.sleep(0.5)

        if token:
            await client.post("/api/v1/auth/verify-email", json={"token": token})

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        if login.status_code != 200:
            return login.status_code
        return account["email"], {"Authorization": f"Bearer {login.json()['access_token']}"}


async def exercise(
    base: str, headers: dict[str, str], rounds: int, timings: dict[str, Timing]
) -> None:
    """One virtual baker's session, repeated `rounds` times."""
    async with httpx.AsyncClient(base_url=base, timeout=30, headers=headers) as client:

        async def call(label: str, method: str, path: str, body: object = None) -> httpx.Response:
            started = time.perf_counter()
            response = await client.request(method, path, json=body)
            timings.setdefault(label, Timing(label)).record(
                time.perf_counter() - started, response.status_code
            )
            return response

        starter = await call(
            "POST /starters", "POST", "/api/v1/starters", {"name": f"S{uuid.uuid4().hex[:8]}"}
        )
        starter_id = starter.json().get("id") if starter.status_code == 201 else None

        for _ in range(rounds):
            await call("GET /starters", "GET", "/api/v1/starters")
            await call("GET /starters/schedule", "GET", "/api/v1/starters/schedule")
            await call("GET /proofing/sessions/active", "GET", "/api/v1/proofing/sessions/active")
            await call("GET /gamification/tier", "GET", "/api/v1/gamification/tier")
            await call("GET /leaderboard", "GET", "/api/v1/leaderboard?limit=25")
            await call("GET /notifications/inbox", "GET", "/api/v1/notifications/inbox")
            await call(
                "POST /proofing/estimate",
                "POST",
                "/api/v1/proofing/estimate",
                {"stage": "bulk", "dough_temp_c": 24},
            )
            if starter_id:
                await call(
                    "GET /starters/{id}/streak", "GET", f"/api/v1/starters/{starter_id}/streak"
                )
            bake = await call(
                "POST /bakes", "POST", "/api/v1/bakes", {"title": "load", "total_flour_g": 1000}
            )
            if bake.status_code == 201:
                await call(
                    "POST /bakes/{id}/complete",
                    "POST",
                    f"/api/v1/bakes/{bake.json()['id']}/complete",
                    {"consume_inventory": False},
                )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=10, help="concurrent virtual bakers")
    parser.add_argument("--requests", type=int, default=10, help="rounds per baker")
    args = parser.parse_args()

    print(f"Provisioning {args.users} accounts against {args.base_url} ...")
    accounts = await asyncio.gather(*(provision(args.base_url, i) for i in range(args.users)))
    # Note the isinstance check: a refused signup returns its status code, and a
    # plain truthiness test would treat `429` as a usable session.
    sessions = [a for a in accounts if isinstance(a, tuple)]
    refused = [a for a in accounts if isinstance(a, int)]

    if not sessions:
        raise SystemExit("could not provision any account — is the stack running?")

    print(f"  {len(sessions)}/{args.users} ready")
    if refused:
        from collections import Counter

        reasons = Counter(refused)
        print(f"  {len(refused)} refused: {dict(reasons)}")
        if 429 in reasons:
            # The limiter is per-IP and every virtual baker shares one, so this
            # would measure the limiter rather than the service. Say so loudly
            # rather than quietly running a smaller test than was asked for.
            print(
                "\n  Registration is limited to 5/hour per IP, so most signups were\n"
                "  rejected. For a meaningful run, restart with RATE_LIMIT_ENABLED=false\n"
                "  and flush Redis:  docker compose exec redis redis-cli flushdb"
            )
    print()

    timings: dict[str, Timing] = {}
    started = time.perf_counter()
    await asyncio.gather(
        *(exercise(args.base_url, headers, args.requests, timings) for _, headers in sessions)
    )
    elapsed = time.perf_counter() - started

    total = sum(len(t.durations) for t in timings.values())
    errors = sum(t.errors for t in timings.values())

    print(f"{total} requests from {len(sessions)} concurrent users in {elapsed:.1f}s")
    print(f"{total / elapsed:.0f} req/s · {errors} errors\n")
    for timing in sorted(timings.values(), key=lambda t: -t.percentile(0.95)):
        print(timing.report())

    if errors:
        print("\nStatus codes seen:")
        for timing in timings.values():
            if timing.errors:
                print(f"  {timing.label:<34} {timing.statuses}")


if __name__ == "__main__":
    asyncio.run(main())
