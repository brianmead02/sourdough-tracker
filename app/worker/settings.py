"""ARQ worker and beat configuration.

Two entrypoints share one Redis but not one queue:
  arq app.worker.settings.WorkerSettings   # consumes arq:work
  arq app.worker.settings.BeatSettings     # runs cron ticks on arq:beat
"""

import logging
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.worker.tasks import (
    BEAT_QUEUE,
    WORK_QUEUE,
    drain_due_notifications,
    enqueue_heartbeat,
    heartbeat,
)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def _startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info("worker starting (environment=%s)", settings.environment)


async def _shutdown(ctx: dict[str, Any]) -> None:
    from app.db import dispose_engine

    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat]
    queue_name = WORK_QUEUE
    redis_settings = _redis_settings()
    on_startup = _startup
    on_shutdown = _shutdown
    max_jobs = 20
    job_timeout = 300


class BeatSettings:
    functions: ClassVar[list[Any]] = []
    cron_jobs: ClassVar[list[Any]] = [
        # Every 60s. arq keys cron runs by timestamp, so a second beat replica
        # cannot double-fire the same tick.
        cron(drain_due_notifications, second=0, run_at_startup=False),
        cron(enqueue_heartbeat, minute={0, 15, 30, 45}, second=0, run_at_startup=True),
    ]
    queue_name = BEAT_QUEUE
    redis_settings = _redis_settings()
    on_startup = _startup
    on_shutdown = _shutdown
