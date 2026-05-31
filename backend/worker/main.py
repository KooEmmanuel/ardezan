"""arq worker configuration.

Run with::

    uv run arq worker.main.WorkerSettings

Jobs live in ``worker.jobs.*`` and are registered in ``WorkerSettings.functions``.
The worker shares MongoDB and config with the FastAPI service so repositories
and Pydantic models can be reused (ARCHITECTURE.md §4.3).
"""
from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.db import close_db, init_db
from app.logging_setup import configure_logging, get_logger
from worker.jobs.email import (
    send_email_verification,
    send_order_confirmation,
    send_order_delivered,
    send_order_shipped,
    send_password_reset,
    send_return_requested,
)
from worker.jobs.health import worker_health
from worker.jobs.inventory_alerts import daily_low_stock_digest
from worker.jobs.inventory_holds import expire_inventory_holds
from worker.jobs.retention import run_retention_sweep
from worker.jobs.tryon import run_tryon_orchestrator

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
log = get_logger("worker.main")


async def startup(ctx: dict[str, Any]) -> None:
    """Initialise shared resources before the worker accepts jobs."""
    log.info("worker.startup", env=settings.app_env)
    await init_db()


async def shutdown(ctx: dict[str, Any]) -> None:
    """Tear down shared resources after the worker stops accepting jobs."""
    log.info("worker.shutdown")
    await close_db()


class WorkerSettings:
    """arq configuration. Job registry, Redis connection, lifecycle hooks."""

    functions: ClassVar[list[Any]] = [
        worker_health,
        expire_inventory_holds,
        send_order_confirmation,
        send_order_shipped,
        send_order_delivered,
        send_return_requested,
        send_email_verification,
        send_password_reset,
        run_tryon_orchestrator,
        run_retention_sweep,
        daily_low_stock_digest,
    ]

    cron_jobs: ClassVar[list[Any]] = [
        # Inventory-hold expiry sweep every 30 seconds. ``unique=True``
        # prevents overlap if a sweep ever runs long; the next tick is skipped.
        cron(
            expire_inventory_holds,
            name="inventory_holds.expire",
            second={0, 30},
            unique=True,
            timeout=60,
        ),
        # Retention sweep every 5 minutes — storage cleanup for expired/
        # deleted media, session/job/checkout expiry. Bounded to 500 docs
        # per sub-sweep so a backlog can't stall the worker.
        cron(
            run_retention_sweep,
            name="retention.sweep",
            minute=set(range(0, 60, 5)),
            unique=True,
            timeout=300,
        ),
        # Daily low-stock digest at 09:00 server-local. Skipped silently
        # if LOW_STOCK_ALERT_EMAIL is unset (dev default).
        cron(
            daily_low_stock_digest,
            name="inventory.low_stock_digest",
            hour={9},
            minute={0},
            unique=True,
            timeout=120,
        ),
    ]

    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # 10 minutes — covers the worst-case AI try-on job (REQ-073 target ≤ 15s,
    # but Designer image loops can stretch under load before we cancel).
    job_timeout = 600

    # Tune up as we observe AI throughput. 8 keeps a single small container
    # responsive while still parallelising image generation.
    max_jobs = 8

    # 24h — matches the anonymous-result retention window (REQ-067).
    keep_result = 60 * 60 * 24
