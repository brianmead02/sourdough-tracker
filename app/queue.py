"""Lazy ARQ pool, so the API can enqueue work onto the worker queue."""

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings
from app.worker.tasks import WORK_QUEUE

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Process-wide pool, created on first use (mirrors app.db.get_engine)."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url), default_queue_name=WORK_QUEUE
        )
    return _pool


async def dispose_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


async def enqueue(function: str, *args: Any) -> None:
    """Fire-and-forget enqueue onto the worker queue (set as the pool default)."""
    pool = await get_arq_pool()
    await pool.enqueue_job(function, *args)
