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


async def drain_due_notifications(ctx: dict[str, Any]) -> int:
    """Beat tick: claim due scheduled notifications and enqueue a send per channel.

    Returns the number of rows claimed. Implemented in Phase 7.
    """
    return 0
