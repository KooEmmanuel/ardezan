"""Retention sweep tests (REQ-066, REQ-067, REQ-068).

Verifies the periodic sweeper expires anonymous try-on sessions, stale AI
jobs, and abandoned checkout sessions once past their TTL — and leaves
not-yet-expired rows untouched. (The media-storage sub-sweep is exercised
separately; here we seed no media_assets so it short-circuits without
touching object storage.)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db import C
from worker.jobs.retention import run_once


def _past() -> datetime:
    return datetime.now(UTC) - timedelta(hours=1)


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


async def test_expires_anonymous_try_on_sessions(mock_db: Any) -> None:
    await mock_db[C.try_on_sessions].insert_one(
        {"try_on_session_id": "tos_old", "expires_at": _past(), "status": "active", "deleted_at": None}
    )
    await mock_db[C.try_on_sessions].insert_one(
        {"try_on_session_id": "tos_new", "expires_at": _future(), "status": "active", "deleted_at": None}
    )

    results = await run_once()

    assert results["try_on_sessions_expired"] == 1
    old = await mock_db[C.try_on_sessions].find_one({"try_on_session_id": "tos_old"})
    new = await mock_db[C.try_on_sessions].find_one({"try_on_session_id": "tos_new"})
    assert old["status"] == "expired"
    assert old["deleted_at"] is not None
    assert new["status"] == "active"  # untouched


async def test_expires_stale_ai_jobs_but_not_terminal(mock_db: Any) -> None:
    await mock_db[C.ai_jobs].insert_one(
        {"ai_job_id": "job_running", "expires_at": _past(), "status": "running"}
    )
    await mock_db[C.ai_jobs].insert_one(
        {"ai_job_id": "job_done", "expires_at": _past(), "status": "completed"}
    )

    results = await run_once()

    assert results["ai_jobs_expired"] == 1
    running = await mock_db[C.ai_jobs].find_one({"ai_job_id": "job_running"})
    done = await mock_db[C.ai_jobs].find_one({"ai_job_id": "job_done"})
    assert running["status"] == "expired"
    assert running["failure"]["failed_stage"] == "retention_sweep"
    assert done["status"] == "completed"  # terminal jobs are never re-expired


async def test_expires_open_checkout_sessions(mock_db: Any) -> None:
    await mock_db[C.checkout_sessions].insert_one(
        {"checkout_session_id": "cs_open", "expires_at": _past(), "status": "open"}
    )
    await mock_db[C.checkout_sessions].insert_one(
        {"checkout_session_id": "cs_paid", "expires_at": _past(), "status": "paid"}
    )

    results = await run_once()

    assert results["checkout_sessions_expired"] == 1
    opened = await mock_db[C.checkout_sessions].find_one({"checkout_session_id": "cs_open"})
    paid = await mock_db[C.checkout_sessions].find_one({"checkout_session_id": "cs_paid"})
    assert opened["status"] == "expired"
    assert paid["status"] == "paid"  # only open sessions expire
