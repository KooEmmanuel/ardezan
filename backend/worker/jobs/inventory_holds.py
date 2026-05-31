"""Periodic job: release inventory holds whose ``expires_at`` has passed.

Scheduled by ``worker.main.WorkerSettings.cron_jobs`` to run every 30 seconds.
The job is idempotent and uses bounded batch size so a backlog can't make any
single run slow.

References: ARCHITECTURE.md §5.3 (soft-hold lifecycle), §5.9 (Retention &
Cleanup), REQ-040 (last-unit atomicity).
"""
from __future__ import annotations

from typing import Any

from app.db import get_db
from app.logging_setup import get_logger
from app.modules.inventory.service import InventoryService

log = get_logger("worker.jobs.inventory_holds")


async def expire_inventory_holds(ctx: dict[str, Any]) -> dict[str, int]:
    """Find and release any active holds past their ``expires_at`` timestamp."""
    db = get_db()
    service = InventoryService(db)
    released = await service.sweep_expired()
    if released:
        log.info("inventory.cron.expired", released=released)
    return {"released": released}
