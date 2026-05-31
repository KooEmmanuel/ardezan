"""Smoke-test job to verify the worker is alive.

Enqueue from anywhere with::

    from arq import create_pool
    from arq.connections import RedisSettings
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job("worker_health", "ping")
"""
from __future__ import annotations

from typing import Any

from app.logging_setup import get_logger

log = get_logger("worker.jobs.health")


async def worker_health(ctx: dict[str, Any], payload: str = "ping") -> dict[str, str]:
    """Echoes the payload back. Used to confirm worker boots and runs jobs."""
    log.info("worker.health", payload=payload, job_id=ctx.get("job_id"))
    return {"status": "ok", "echo": payload}
