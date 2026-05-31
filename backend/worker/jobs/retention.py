"""Retention sweeper (M6.1).

Single cron job that runs every 5 minutes and performs four bounded sweeps:

1. **Storage cleanup** — for every ``media_assets`` row whose
   ``retention.expires_at`` has passed OR ``retention.deleted_at`` is set,
   delete the underlying object from storage and stamp
   ``storage_object_deleted_at`` so the next sweep skips it.
2. **Anonymous try-on session expiry** — mark sessions past their
   ``expires_at`` as ``expired`` + ``deleted_at`` so they vanish from the
   customer's Fitting Room and become candidates for storage cleanup.
3. **AI job expiry** — non-terminal ``ai_jobs`` past their ``expires_at``
   get flipped to ``expired`` with a structured failure stamp.
4. **Checkout session expiry** — ``open`` sessions past their ``expires_at``
   get flipped to ``expired`` so customers retrying see a clear "session
   expired" error rather than the silent void.

Bounded to 500 docs per sub-sweep. Each item's failure is logged but doesn't
abort the rest of the sweep — the next tick (5 min later) retries.

References:
- ARCHITECTURE.md §5.9 (Retention and Cleanup)
- REQ-066, REQ-067, REQ-068
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from app.db import C, get_db
from app.logging_setup import get_logger
from app.storage import get_storage

log = get_logger("worker.jobs.retention")

BATCH_SIZE = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _sweep_media_storage(
    db: Any, now: datetime, results: dict[str, int]
) -> None:
    """Delete storage objects for expired or soft-deleted media_assets.

    Idempotent: ``storage_object_deleted_at`` is set once the object is gone,
    and the filter excludes rows where it's already present.
    """
    query: dict[str, Any] = {
        "storage_object_deleted_at": {"$exists": False},
        "$or": [
            {"retention.expires_at": {"$lte": now, "$ne": None}},
            {"retention.deleted_at": {"$ne": None}},
        ],
    }
    cursor = db[C.media_assets].find(query).limit(BATCH_SIZE)
    docs = await cursor.to_list(BATCH_SIZE)
    if not docs:
        return

    storage = get_storage()
    for doc in docs:
        media_id = doc["media_asset_id"]
        storage_block = doc.get("storage") or {}
        key = storage_block.get("object_key")
        if not key:
            log.warning("retention.media_no_key", media_id=media_id)
            # Mark cleanup done anyway so we don't spin on it forever.
            await db[C.media_assets].update_one(
                {"media_asset_id": media_id},
                {
                    "$set": {
                        "storage_object_deleted_at": now,
                        "updated_at": now,
                    }
                },
            )
            continue

        try:
            await storage.delete_object(key)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "retention.storage_delete_failed",
                media_id=media_id,
                object_key=key,
                error=str(exc),
            )
            continue  # try again next sweep

        existing_deleted_at = (doc.get("retention") or {}).get("deleted_at")
        await db[C.media_assets].update_one(
            {"media_asset_id": media_id},
            {
                "$set": {
                    "retention.deleted_at": existing_deleted_at or now,
                    "storage_object_deleted_at": now,
                    "updated_at": now,
                }
            },
        )
        results["media_storage_deleted"] += 1


async def _sweep_try_on_sessions(
    db: Any, now: datetime, results: dict[str, int]
) -> None:
    """Mark anonymous sessions past their ``expires_at`` as ``expired``.

    The session's uploaded photo + result-card generated images get cleaned
    by the media-storage sweep on subsequent ticks (they share retention rows).
    """
    update_result = await db[C.try_on_sessions].update_many(
        {
            "expires_at": {"$lte": now, "$ne": None},
            "status": {"$nin": ["deleted", "expired"]},
            "deleted_at": None,
        },
        {
            "$set": {
                "status": "expired",
                "deleted_at": now,
                "updated_at": now,
            }
        },
    )
    results["try_on_sessions_expired"] = int(update_result.modified_count or 0)


async def _sweep_ai_jobs(
    db: Any, now: datetime, results: dict[str, int]
) -> None:
    """Non-terminal ``ai_jobs`` past their ``expires_at`` get flipped to
    ``expired`` with a structured failure marker for analytics."""
    terminal = {"completed", "completed_partial", "failed", "cancelled", "expired"}
    update_result = await db[C.ai_jobs].update_many(
        {
            "expires_at": {"$lte": now, "$ne": None},
            "status": {"$nin": list(terminal)},
        },
        {
            "$set": {
                "status": "expired",
                "current_stage": "expired",
                "completed_at": now,
                "updated_at": now,
                "failure": {
                    "reason": "Job exceeded its retention TTL.",
                    "recoverable": False,
                    "failed_stage": "retention_sweep",
                },
            }
        },
    )
    results["ai_jobs_expired"] = int(update_result.modified_count or 0)


async def _sweep_checkout_sessions(
    db: Any, now: datetime, results: dict[str, int]
) -> None:
    """Flip ``open`` checkout sessions past their ``expires_at`` to ``expired``.

    The inventory-hold sweep (M2) handles the per-variant hold expiry on its
    own 30-second cadence; this one is for the *checkout session* document so
    a customer who comes back to a stale Stripe page sees a clean state.
    """
    update_result = await db[C.checkout_sessions].update_many(
        {
            "expires_at": {"$lte": now, "$ne": None},
            "status": "open",
        },
        {"$set": {"status": "expired", "updated_at": now}},
    )
    results["checkout_sessions_expired"] = int(update_result.modified_count or 0)


async def run_retention_sweep(ctx: dict[str, Any]) -> dict[str, int]:
    """arq cron entry point. Runs all four sweeps in order."""
    db = get_db()
    now = _now()
    results: dict[str, int] = {
        "media_storage_deleted": 0,
        "try_on_sessions_expired": 0,
        "ai_jobs_expired": 0,
        "checkout_sessions_expired": 0,
    }

    try:
        await _sweep_media_storage(db, now, results)
    except Exception as exc:  # noqa: BLE001
        log.exception("retention.media_sweep_error", error=str(exc))

    try:
        await _sweep_try_on_sessions(db, now, results)
    except Exception as exc:  # noqa: BLE001
        log.exception("retention.session_sweep_error", error=str(exc))

    try:
        await _sweep_ai_jobs(db, now, results)
    except Exception as exc:  # noqa: BLE001
        log.exception("retention.ai_job_sweep_error", error=str(exc))

    try:
        await _sweep_checkout_sessions(db, now, results)
    except Exception as exc:  # noqa: BLE001
        log.exception("retention.checkout_sweep_error", error=str(exc))

    if any(v > 0 for v in results.values()):
        log.info("retention.sweep_done", **results)
    return results


# Re-exported for ad-hoc invocation from the API (e.g. a dev "run sweep now"
# endpoint or a teardown helper).
async def run_once() -> dict[str, int]:
    """Run a sweep outside the worker — useful for tests + dev smoke."""
    return await run_retention_sweep({})


__all__ = ["run_retention_sweep", "run_once"]


# Helper for one-off doc updates from elsewhere (currently unused).
async def mark_media_force_expire(db: Any, media_asset_id: str) -> dict[str, Any] | None:
    """Force-expire a media_asset so the next sweep removes it.

    Sets ``retention.deleted_at`` if not already set. Useful for explicit
    teardown flows outside the standard customer/admin paths.
    """
    return await db[C.media_assets].find_one_and_update(
        {"media_asset_id": media_asset_id},
        {"$set": {"retention.deleted_at": _now(), "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
