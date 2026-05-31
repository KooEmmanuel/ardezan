"""Redis-backed arq job queue — connection pool for the API process.

The API enqueues jobs into Redis; the separate worker process (``worker.main``)
consumes them. They share the Redis instance but not Python objects.

Lifecycle is wired into ``app.main.lifespan`` so the pool is created once at
startup and closed cleanly at shutdown. ``get_queue()`` raises if called before
``init_queue()`` runs — same pattern as ``app.db``.
"""
from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings
from app.logging_setup import get_logger

log = get_logger(__name__)

_pool: ArqRedis | None = None


async def init_queue() -> None:
    """Create the Redis connection pool used for enqueueing background jobs."""
    global _pool
    settings = get_settings()
    _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    log.info("queue.connect", url=settings.redis_url)


async def close_queue() -> None:
    """Close the Redis connection pool. Safe to call on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def get_queue() -> ArqRedis:
    """Return the bound arq Redis pool. Raises if not yet initialised."""
    if _pool is None:
        raise RuntimeError("Job queue not initialised — call init_queue() first.")
    return _pool
