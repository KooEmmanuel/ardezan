"""Try-on routes (per API.md §10).

- ``POST /try-on/sessions`` — multipart upload, runs safety pipeline, enqueues job.
- ``GET  /try-on/jobs/{id}`` — job state read.
- ``GET  /try-on/jobs/{id}/events`` — SSE stream (replays past events on
  ``Last-Event-ID`` reconnect; polls the job doc for new events).
"""
from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.db import C
from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.customers.deps import OptionalCustomerDep
from app.modules.try_on.account_schemas import (
    FittingRoomResultCard,
    FittingRoomSessionDetail,
)
from app.modules.try_on.account_service import FittingRoomService
from app.modules.try_on.schemas import JobCreatedResponse, JobPublic, TryOnInputs
from app.modules.try_on.service import TryOnService
from app.rate_limit import enforce_upload_fingerprint, rate_limit_try_on_upload

router = APIRouter()


def get_service(db: DbDep) -> TryOnService:
    return TryOnService(db)


ServiceDep = Annotated[TryOnService, Depends(get_service)]


# ── Create session ──────────────────────────────────────────────────
@router.post(
    "/sessions",
    response_model=JobCreatedResponse,
    summary="Upload a photo and start a try-on orchestration job",
    status_code=201,
    dependencies=[Depends(rate_limit_try_on_upload)],
)
async def create_session(
    request: Request,
    service: ServiceDep,
    photo: Annotated[UploadFile, File(description="Full-body photo (JPEG/PNG/WebP/HEIC)")],
    height: Annotated[str | None, Form()] = None,
    fit_preference: Annotated[str | None, Form()] = None,
    occasion: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
    seeded_product_id: Annotated[str | None, Form()] = None,
    age_confirmed: Annotated[bool, Form()] = False,
    anonymous_session_id: Annotated[str | None, Form()] = None,
) -> JobCreatedResponse:
    # Second-pass fingerprint rate limit using the form value the cookie
    # dep couldn't see. Cheap (1 Redis round-trip) and lets shared-NAT
    # users stay within their own bucket.
    if anonymous_session_id:
        await enforce_upload_fingerprint(request, anonymous_session_id)

    body = await photo.read()
    inputs = TryOnInputs(
        height=height,
        fit_preference=fit_preference,  # type: ignore[arg-type]
        occasion=occasion,
        prompt=prompt,
    )
    return await service.create_session(
        photo_bytes=body,
        content_type=photo.content_type or "application/octet-stream",
        inputs=inputs,
        seeded_product_id=seeded_product_id,
        customer_id=None,  # customer auth lands in M5
        anonymous_session_id=anonymous_session_id,
        age_confirmed=age_confirmed,
    )


# ── Refine: spawn a new session from an existing one ────────────────
from pydantic import BaseModel, Field


class RefineSessionRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=500)


@router.post(
    "/sessions/{try_on_session_id}/refine",
    response_model=JobCreatedResponse,
    summary="Spawn a new try-on session refined from an existing one",
    status_code=201,
)
async def refine_session(
    try_on_session_id: str,
    body: RefineSessionRequest,
    service: ServiceDep,
    customer: OptionalCustomerDep,
) -> JobCreatedResponse:
    return await service.refine_session(
        original_session_id=try_on_session_id,
        refinement_prompt=body.prompt,
        requesting_customer_id=(customer or {}).get("customer_id"),
        requesting_anonymous_session_id=None,
    )


# ── Read session detail (public; owner-gated when customer-owned) ──
@router.get(
    "/sessions/{try_on_session_id}",
    response_model=FittingRoomSessionDetail,
    summary="Read a try-on session with freshly signed image URLs",
)
async def get_session(
    try_on_session_id: str,
    db: DbDep,
    customer: OptionalCustomerDep,
) -> FittingRoomSessionDetail:
    service = FittingRoomService(db)
    raw = await service.get_public(
        try_on_session_id,
        requesting_customer_id=(customer or {}).get("customer_id"),
    )
    return FittingRoomSessionDetail(
        try_on_session_id=raw["try_on_session_id"],
        source=raw["source"],
        status=raw["status"],
        optional_inputs=raw.get("optional_inputs") or {},
        body_profile_snapshot=raw.get("body_profile_snapshot"),
        result_cards=[FittingRoomResultCard(**c) for c in raw.get("result_cards", [])],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
    )


# ── Read job state ──────────────────────────────────────────────────
@router.get(
    "/jobs/{job_id}",
    response_model=JobPublic,
    summary="Read current job state — used for polling fallback if SSE unavailable",
)
async def get_job(job_id: str, service: ServiceDep) -> JobPublic:
    doc = await service.get_job(job_id)
    events = doc.get("progress_events") or []
    latest_pct = max((e.get("progress_percent", 0) for e in events), default=0)
    return JobPublic(
        job_id=doc["job_id"],
        try_on_session_id=doc.get("try_on_session_id"),
        status=doc["status"],
        current_stage=doc.get("current_stage"),
        progress_percent=latest_pct,
        failure_reason=(doc.get("failure") or {}).get("reason"),
        estimated_cost_amount=(doc.get("cost") or {}).get("estimated_total_amount"),
        created_at=doc["created_at"],
        completed_at=doc.get("completed_at"),
    )


# ── SSE event stream ────────────────────────────────────────────────
TERMINAL_STATUSES = {"completed", "completed_partial", "failed", "cancelled", "expired"}


def _sse_format(event_type: str, event_id: str, data: dict) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\nid: {event_id}\ndata: {payload}\n\n"


@router.get(
    "/jobs/{job_id}/events",
    summary="SSE progress stream. Supports Last-Event-ID for reconnect (REQ-018).",
)
async def stream_events(
    job_id: str,
    request: Request,
    db: DbDep,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    async def event_generator():
        seen_event_ids: set[str] = set()
        reconnect_point_reached = last_event_id is None  # if no reconnect, start fresh

        # Initial fetch — replay any events the client missed.
        job = await db[C.ai_jobs].find_one({"job_id": job_id})
        if not job:
            yield _sse_format(
                "error",
                "evt_not_found",
                {"error": "Job not found", "job_id": job_id},
            )
            return

        for event in job.get("progress_events") or []:
            eid = event.get("event_id")
            if not eid:
                continue
            seen_event_ids.add(eid)
            if not reconnect_point_reached:
                if eid == last_event_id:
                    reconnect_point_reached = True
                continue  # skip already-seen events
            yield _sse_format(
                event["type"],
                eid,
                {
                    "stage": event.get("stage"),
                    "message": event.get("message"),
                    "progress_percent": event.get("progress_percent"),
                    "payload": event.get("payload") or {},
                    "created_at": event.get("created_at"),
                },
            )

        # If the job is already finished, close cleanly.
        if job["status"] in TERMINAL_STATUSES:
            return

        # Poll for new events until the job reaches a terminal state.
        poll_interval = 0.5
        idle_keepalive_every = 15  # seconds — Heroku/CF idle-timeout-friendly
        last_keepalive = 0.0

        while True:
            if await request.is_disconnected():
                return

            await asyncio.sleep(poll_interval)
            last_keepalive += poll_interval

            job = await db[C.ai_jobs].find_one({"job_id": job_id})
            if not job:
                yield _sse_format(
                    "error", "evt_gone", {"error": "Job disappeared", "job_id": job_id}
                )
                return

            new_events = [
                e
                for e in (job.get("progress_events") or [])
                if e.get("event_id") and e["event_id"] not in seen_event_ids
            ]
            for event in new_events:
                seen_event_ids.add(event["event_id"])
                yield _sse_format(
                    event["type"],
                    event["event_id"],
                    {
                        "stage": event.get("stage"),
                        "message": event.get("message"),
                        "progress_percent": event.get("progress_percent"),
                        "payload": event.get("payload") or {},
                        "created_at": event.get("created_at"),
                    },
                )
                last_keepalive = 0.0

            if job["status"] in TERMINAL_STATUSES:
                return

            # Keepalive comment so intermediaries don't drop the connection.
            if last_keepalive >= idle_keepalive_every:
                yield ": keepalive\n\n"
                last_keepalive = 0.0

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


# Re-exported so the dev smoke endpoint can call the service directly.
__all__ = ["router", "TryOnService"]
