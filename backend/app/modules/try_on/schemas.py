"""Try-on schemas — request payloads, job state, SSE event types."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Stages match ARCHITECTURE.md §8.3. Each is also the value of
# ``current_stage`` on the ai_jobs document during processing.
JobStatus = Literal[
    "queued",
    "validating_upload",
    "analyzing_photo",
    "building_catalog_context",
    "recommending_outfits",
    "generating_images",
    "completed",
    "completed_partial",
    "failed",
    "cancelled",
    "expired",
]

FitPreference = Literal["slim", "regular", "oversized"]


class TryOnInputs(BaseModel):
    """Optional inputs the customer can add alongside the photo upload."""

    height: str | None = Field(None, max_length=20)
    fit_preference: FitPreference | None = None
    occasion: str | None = Field(None, max_length=240)
    prompt: str | None = Field(None, max_length=400)


class JobCreatedResponse(BaseModel):
    try_on_session_id: str
    job_id: str
    sse_url: str


class JobPublic(BaseModel):
    job_id: str
    try_on_session_id: str | None = None
    status: JobStatus
    current_stage: str | None = None
    progress_percent: int = 0
    failure_reason: str | None = None
    estimated_cost_amount: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


# ── SSE event payloads (ARCHITECTURE.md §8.6) ───────────────────────
class ProgressEvent(BaseModel):
    """Stored on ``ai_jobs.progress_events`` and emitted via SSE."""

    event_id: str
    type: str  # e.g. "job.created", "analyzer.completed", "job.failed"
    stage: str | None = None
    message: str | None = None
    progress_percent: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
