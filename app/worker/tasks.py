"""Background tasks and the beat tick.

Division of labour (docs/PLAN.md §6): the *beat* process only decides what is due
and enqueues it onto ``WORK_QUEUE``; the *worker* processes do the actual work.
Phase 7 replaces the placeholder body of `drain_due_notifications` with the
`SELECT ... FOR UPDATE SKIP LOCKED` claim over `scheduled_notification`.
"""

import logging
from typing import Any

# Beat and workers must not share a queue: arq registers cron functions under a
# "cron:" prefix in the defining process only, so a worker on the same queue would
# claim a cron job it cannot resolve.
WORK_QUEUE = "arq:work"
BEAT_QUEUE = "arq:beat"

logger = logging.getLogger(__name__)


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Runs on a worker. Proves the beat -> redis -> worker path is wired end to end."""
    logger.info("heartbeat")
    return "ok"


async def enqueue_heartbeat(ctx: dict[str, Any]) -> None:
    """Beat cron: hand a heartbeat to the worker pool."""
    await ctx["redis"].enqueue_job("heartbeat", _queue_name=WORK_QUEUE)


async def send_email(ctx: dict[str, Any], to: str, subject: str, body: str) -> None:
    """Deliver transactional email off the request path."""
    from app.services.email import send_email as deliver

    await deliver(to, subject, body)


async def enqueue_leaderboard_refresh(ctx: dict[str, Any]) -> None:
    """Beat cron: hand the rollup to a worker rather than doing it on the beat."""
    await ctx["redis"].enqueue_job("refresh_leaderboard", _queue_name=WORK_QUEUE)


async def refresh_leaderboard(ctx: dict[str, Any]) -> int:
    """Rebuild the leaderboard rollup. Idempotent, so a missed run self-heals."""
    from app.db import get_session_factory
    from app.services.leaderboard import refresh

    async with get_session_factory()() as session:
        result = await refresh(session)
        await session.commit()
    logger.info("leaderboard refresh: %d users ranked", result.users_ranked)
    return result.users_ranked


async def drain_due_notifications(ctx: dict[str, Any]) -> int:
    """Beat tick: claim every due reminder and deliver it.

    Runs on the beat process rather than fanning out to workers: `FOR UPDATE
    SKIP LOCKED` already makes concurrent drainers safe, and keeping the claim
    and the send in one transaction means a crash mid-delivery leaves the row
    claimed rather than lost.
    """
    from app.db import get_session_factory
    from app.services.notifications import drain

    async with get_session_factory()() as session:
        result = await drain(session)
        await session.commit()
    return result.claimed
