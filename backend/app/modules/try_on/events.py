"""SSE event helpers — emit from the worker, consume in the API.

Persistence: every event is appended to ``ai_jobs.progress_events`` so a
reconnecting client can replay missed events via the ``Last-Event-ID`` header.

Live delivery: the SSE endpoint polls the ``ai_jobs`` document every 500 ms.
This is the simple Phase-1 implementation; M4.2+ can upgrade to Redis
pub/sub if latency becomes a concern.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event_id() -> str:
    return f"evt_{secrets.token_hex(6)}"


async def emit(
    db: AsyncIOMotorDatabase[Any],
    job_id: str,
    *,
    type: str,
    stage: str | None = None,
    message: str | None = None,
    progress_percent: int = 0,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a progress event to ``ai_jobs.progress_events``.

    Returns the event document (with its id) so callers can use it for logs.
    Also updates ``current_stage`` + ``updated_at`` in the same op.
    """
    event = {
        "event_id": _event_id(),
        "type": type,
        "stage": stage,
        "message": message,
        "progress_percent": progress_percent,
        "payload": payload or {},
        "created_at": _now(),
    }
    update: dict[str, Any] = {
        "$push": {"progress_events": event},
        "$set": {"updated_at": event["created_at"]},
    }
    if stage:
        update["$set"]["current_stage"] = stage
    await db[C.ai_jobs].update_one({"job_id": job_id}, update)
    log.info(
        "tryon.event",
        job_id=job_id,
        type=type,
        stage=stage,
        progress_percent=progress_percent,
    )
    return event
