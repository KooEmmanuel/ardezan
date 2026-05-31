"""Try-on orchestrator job.

Stage-by-stage progression per ARCHITECTURE §5.7 + §8.3:

  queued → validating_upload → analyzing_photo → building_catalog_context →
  recommending_outfits → generating_images → completed (or _partial / failed)

M4 status:
- Analyzer (M4.2): real Gemini multimodal call → BodyProfile
- Recommender (M4.3): real Gemini call over CatalogContext → outfits
- Designer (M4.4, this turn): real Nano Banana per outfit → generated images

Cost ceiling and kill switch are checked before each provider call so the
runtime respects the admin controls from M3.4. Per-image failures don't kill
the batch (REQ-054) — the job ends ``completed_partial`` if any image fails.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.db import C, get_db
from app.logging_setup import get_logger
from app.modules.admin.ai_repository import AiSettingsRepository, AnalyticsRepository
from app.modules.try_on.analyzer import AnalyzerError, analyze
from app.modules.try_on.catalog_context import build_catalog_context
from app.modules.try_on.designer import (
    DesignerError,
    generate_image_for_card,
    store_generated_image,
)
from app.modules.try_on.events import emit
from app.modules.try_on.recommender import RecommenderError, recommend
from app.modules.try_on.result_cards import build_result_cards, persist_result_cards
from app.modules.try_on.schemas import TryOnInputs
from app.storage import get_storage

# Up to 3 image generations concurrently — keeps per-job latency low while
# staying well under Gemini's per-key rate limits.
DESIGNER_CONCURRENCY = 3

log = get_logger("worker.jobs.tryon")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _set_stage(db, job_id: str, *, status: str, current_stage: str | None) -> None:
    await db[C.ai_jobs].update_one(
        {"job_id": job_id},
        {"$set": {"status": status, "current_stage": current_stage, "updated_at": _now()}},
    )


async def _record_provider_call(db, job_id: str, provider_call: dict[str, Any]) -> None:
    """Append the provider_call entry and increment the cumulative cost."""
    cost = int(provider_call.get("estimated_cost_amount") or 0)
    await db[C.ai_jobs].update_one(
        {"job_id": job_id},
        {
            "$push": {"provider_calls": provider_call},
            "$inc": {"cost.estimated_total_amount": cost},
            "$set": {"updated_at": _now()},
        },
    )


async def _check_ai_budget(db) -> tuple[bool, str | None]:
    """Return ``(can_proceed, reason_if_blocked)`` based on admin AI controls."""
    settings_repo = AiSettingsRepository(db)
    settings = await settings_repo.get_resolved()
    if settings["kill_switch_enabled"]:
        return False, "kill_switch_enabled"

    analytics_repo = AnalyticsRepository(db)
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_spend = await analytics_repo.ai_today_spend(today_start)
    ceiling = int(settings["daily_spend_ceiling_amount"])
    if ceiling > 0 and today_spend >= ceiling:
        return False, "daily_spend_ceiling_reached"
    return True, None


async def _fail_job(
    db,
    job_id: str,
    *,
    reason: str,
    failed_stage: str,
    recoverable: bool = False,
    technical_detail: str | None = None,
) -> None:
    """Mark a job failed.

    ``reason`` is the customer-facing message — keep it short, friendly, and
    actionable. The raw exception text goes in ``technical_detail`` so the
    admin audit trail can still see Pydantic stack traces, but the SSE
    stream and frontend never receive them.
    """
    now = _now()
    await emit(
        db,
        job_id,
        type="job.failed",
        stage="failed",
        message=reason,
        progress_percent=0,
        payload={"failed_stage": failed_stage},
    )
    await db[C.ai_jobs].update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": "failed",
                "current_stage": "failed",
                "failure": {
                    "reason": reason[:300],
                    "recoverable": recoverable,
                    "failed_stage": failed_stage,
                    "technical_detail": (technical_detail or "")[:1000] or None,
                },
                "completed_at": now,
                "updated_at": now,
            }
        },
    )


# ── Photo loading ───────────────────────────────────────────────────
async def _load_uploaded_photo(
    db, job: dict[str, Any]
) -> tuple[bytes, str] | None:
    """Resolve the uploaded media asset and pull its bytes from storage.

    Returns ``(bytes, content_type)`` on success; ``None`` if anything is
    missing — caller is expected to have already failed the job in that case.
    """
    media_asset_id = (job.get("input") or {}).get("uploaded_media_asset_id")
    if not media_asset_id:
        return None
    media = await db[C.media_assets].find_one({"media_asset_id": media_asset_id})
    if not media:
        return None
    storage = get_storage()
    try:
        body = await storage.get_object(media["storage"]["object_key"])
    except Exception as exc:  # noqa: BLE001
        log.exception("tryon.upload_fetch_failed", error=str(exc))
        return None
    content_type = media["storage"].get("content_type", "image/jpeg")
    return body, content_type


# ── Analyzer stage (real Gemini call, M4.2) ─────────────────────────
async def _run_analyzer(
    db,
    job: dict[str, Any],
    photo_bytes: bytes,
    content_type: str,
) -> dict[str, Any] | None:
    """Call the Analyzer on the pre-loaded photo bytes. Returns the
    BodyProfile dict on success; returns ``None`` on failure (after recording
    the failure on the job)."""
    job_id = job["job_id"]
    inputs = TryOnInputs(**(job.get("input", {}).get("optional_inputs") or {}))

    await emit(
        db,
        job_id,
        type="analyzer.started",
        stage="analyzing_photo",
        message="Reading your photo…",
        progress_percent=15,
    )

    try:
        body_profile, provider_call = await analyze(
            photo_bytes, content_type, inputs
        )
    except AnalyzerError as exc:
        await _record_provider_call(db, job_id, exc.provider_call)
        await _fail_job(
            db,
            job_id,
            reason=(
                "We couldn't read your photo clearly. Try a brighter, "
                "full-body shot against a plain background."
            ),
            failed_stage="analyzing_photo",
            recoverable=True,  # retryable — usually transient
            technical_detail=(
                f"AnalyzerError: {exc.provider_call.get('error_code') or 'unknown'} "
                f"- {exc.provider_call.get('error_message') or ''}"
            ),
        )
        return None

    await _record_provider_call(db, job_id, provider_call)

    profile_dict = body_profile.model_dump()
    # Snapshot the profile onto the try_on_session so the Recommender (and
    # admin UI) can read it without poking ai_jobs.
    await db[C.try_on_sessions].update_one(
        {"try_on_session_id": job["try_on_session_id"]},
        {
            "$set": {
                "body_profile_snapshot": {
                    "measurements_estimate": {
                        "height_cm": profile_dict.get("estimated_height_cm"),
                        "chest_cm": profile_dict.get("estimated_chest_cm"),
                        "waist_cm": profile_dict.get("estimated_waist_cm"),
                        "hip_cm": profile_dict.get("estimated_hip_cm"),
                        "inseam_cm": profile_dict.get("estimated_inseam_cm"),
                    },
                    "body_shape": profile_dict.get("body_shape"),
                    "skin_undertone": profile_dict.get("skin_undertone"),
                    "current_style_notes": profile_dict.get("current_style_notes"),
                    "confidence": profile_dict.get("confidence"),
                },
                "updated_at": _now(),
            }
        },
    )

    await emit(
        db,
        job_id,
        type="analyzer.completed",
        stage="analyzing_photo",
        message="Read your photo.",
        progress_percent=30,
        payload={
            "body_shape": profile_dict.get("body_shape"),
            "skin_undertone": profile_dict.get("skin_undertone"),
            "confidence": profile_dict.get("confidence"),
        },
    )
    return profile_dict


# ── Recommender stage (M4.3) ────────────────────────────────────────
async def _run_recommender(
    db, job: dict[str, Any], body_profile: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Build CatalogContext, call Gemini for outfits, persist result cards.

    Returns the list of result cards on success; ``None`` after recording
    a failure on the job.
    """
    job_id = job["job_id"]
    try_on_session_id = job["try_on_session_id"]
    inputs = TryOnInputs(**(job.get("input", {}).get("optional_inputs") or {}))
    seeded_product_id = (job.get("input") or {}).get("seeded_product_id")

    # Stage: building_catalog_context
    await _set_stage(
        db, job_id, status="building_catalog_context", current_stage="building_catalog_context"
    )
    await emit(
        db,
        job_id,
        type="context.building",
        stage="building_catalog_context",
        message="Selecting candidate pieces…",
        progress_percent=35,
    )

    # When the customer is trying on a specific piece, generate fewer outfits
    # — variety comes only from the complementary items around the hero
    # piece, so 5 distinct looks is plenty and keeps generation cost down.
    requested_max_outfits = 5 if seeded_product_id else 10

    context = await build_catalog_context(
        db,
        body_profile=body_profile,
        inputs=inputs,
        seeded_product_id=seeded_product_id,
        max_outfits=requested_max_outfits,
    )

    if not context["candidates"]:
        await _fail_job(
            db,
            job_id,
            reason="No eligible products in the catalogue right now.",
            failed_stage="building_catalog_context",
            recoverable=True,
        )
        return None

    await emit(
        db,
        job_id,
        type="context.completed",
        stage="building_catalog_context",
        message=f"{len(context['candidates'])} pieces in play.",
        progress_percent=42,
        payload={"candidate_count": len(context["candidates"])},
    )

    # Stage: recommending_outfits
    await _set_stage(
        db, job_id, status="recommending_outfits", current_stage="recommending_outfits"
    )
    await emit(
        db,
        job_id,
        type="recommender.started",
        stage="recommending_outfits",
        message="Finding pieces that fit…",
        progress_percent=48,
    )

    try:
        outfits, provider_call = await recommend(context)
    except RecommenderError as exc:
        await _record_provider_call(db, job_id, exc.provider_call)
        await _fail_job(
            db,
            job_id,
            reason=(
                "We couldn't put together outfits this time. "
                "Try again in a moment or refine the brief."
            ),
            failed_stage="recommending_outfits",
            recoverable=True,
            technical_detail=(
                f"RecommenderError: {exc.provider_call.get('error_code') or 'unknown'} "
                f"- {exc.provider_call.get('error_message') or ''}"
            ),
        )
        return None

    await _record_provider_call(db, job_id, provider_call)

    if not outfits:
        await _fail_job(
            db,
            job_id,
            reason="The recommender couldn't find suitable outfits — try a different photo or occasion.",
            failed_stage="recommending_outfits",
            recoverable=True,
        )
        return None

    cards = build_result_cards(outfits, context)
    await persist_result_cards(db, try_on_session_id, cards)

    await emit(
        db,
        job_id,
        type="recommender.completed",
        stage="recommending_outfits",
        message=f"{len(cards)} outfit{'s' if len(cards) != 1 else ''} selected.",
        progress_percent=60,
        payload={
            "outfit_count": len(cards),
            "outfits_dropped": (provider_call.get("extra") or {}).get(
                "outfits_dropped", 0
            ),
        },
    )
    return cards


# ── Agent-backed recommender (Google ADK + Gemini, hackathon scope) ──
async def _run_recommender_via_agent(
    db, job: dict[str, Any], body_profile: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Stylist ADK agent variant of ``_run_recommender``.

    Used for **refine** jobs so judges can see a real agent loop in
    action (multi-tool, multi-turn). Falls back to the legacy path on
    any agent failure so the refine UX still completes.
    """
    from app.agents import run_stylist_refine
    from app.modules.try_on.recommender import RecommendedOutfit

    job_id = job["job_id"]
    try_on_session_id = job["try_on_session_id"]
    inputs = TryOnInputs(**(job.get("input", {}).get("optional_inputs") or {}))
    brief = (inputs.prompt or "").strip()

    await _set_stage(
        db, job_id, status="recommending_outfits", current_stage="recommending_outfits"
    )
    await emit(
        db,
        job_id,
        type="agent.started",
        stage="recommending_outfits",
        message="Stylist agent thinking…",
        progress_percent=42,
        payload={"agent": "ardezan_stylist"},
    )

    # Look up prior outfit titles from the original session so the agent
    # has continuity context for the refinement.
    prior_titles: list[str] = []
    original_session_id = (job.get("input") or {}).get("refined_from_session_id")
    if original_session_id:
        orig = await db[C.try_on_sessions].find_one(
            {"try_on_session_id": original_session_id}
        )
        for card in (orig or {}).get("result_cards", [])[:5]:
            t = card.get("outfit_name") or card.get("title")
            if t:
                prior_titles.append(t)

    user_id = (
        job.get("customer_id")
        or job.get("anonymous_session_id")
        or "anonymous"
    )

    try:
        result = await run_stylist_refine(
            db=db,
            session_id=try_on_session_id,
            user_id=user_id,
            refinement_brief=brief,
            body_profile=body_profile,
            prior_outfit_titles=prior_titles,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("agent.refine_failed", error=str(exc)[:200])
        await emit(
            db,
            job_id,
            type="agent.failed",
            stage="recommending_outfits",
            message="Agent failed; falling back to direct recommender.",
            progress_percent=45,
        )
        return await _run_recommender(db, job, body_profile)

    structured = result.get("structured_outfits") or []
    candidates = result.get("candidates") or []
    summary = result.get("summary") or ""
    tool_calls = result.get("tool_calls") or []

    if not structured or not candidates:
        log.info("agent.refine_empty_fallback")
        await emit(
            db,
            job_id,
            type="agent.empty",
            stage="recommending_outfits",
            message="Agent produced no plan; falling back to direct recommender.",
            progress_percent=45,
        )
        return await _run_recommender(db, job, body_profile)

    await emit(
        db,
        job_id,
        type="agent.summary",
        stage="recommending_outfits",
        message=summary[:200] if summary else "Agent finished.",
        progress_percent=55,
        payload={
            "summary": summary,
            "tool_call_count": len(tool_calls),
            "tool_calls": [
                {"name": tc.get("name")} for tc in tool_calls
            ],
        },
    )

    # Hydrate to RecommendedOutfit so build_result_cards stays one path.
    outfits = [RecommendedOutfit(**d) for d in structured]
    context = {"candidates": candidates}
    cards = build_result_cards(outfits, context)
    if not cards:
        log.warning("agent.no_cards_after_build")
        return await _run_recommender(db, job, body_profile)
    await persist_result_cards(db, try_on_session_id, cards)

    await emit(
        db,
        job_id,
        type="recommender.completed",
        stage="recommending_outfits",
        message=f"{len(cards)} outfit{'s' if len(cards) != 1 else ''} via stylist agent.",
        progress_percent=60,
        payload={"outfit_count": len(cards), "via_agent": True},
    )
    return cards


# ── Designer stage (M4.4 — real Nano Banana per outfit) ─────────────
async def _run_designer(
    db,
    job: dict[str, Any],
    cards: list[dict[str, Any]],
    *,
    photo_bytes: bytes,
    photo_content_type: str,
) -> tuple[int, int]:
    """Generate an image per result card. Returns ``(success_count, failure_count)``.

    Per-card failures are isolated — one bad image doesn't abort the batch.
    The job's final status depends on the success/failure ratio:
    - all succeed     → ``completed``
    - some succeed    → ``completed_partial``
    - none succeed    → still ``completed_partial`` (the recommendations are
                        still useful as text-only cards)
    """
    job_id = job["job_id"]
    try_on_session_id = job["try_on_session_id"]
    customer_id = job.get("customer_id")
    anonymous_session_id = job.get("anonymous_session_id")
    storage_client = get_storage()
    n = len(cards) or 1

    await _set_stage(
        db, job_id, status="generating_images", current_stage="generating_images"
    )

    semaphore = asyncio.Semaphore(DESIGNER_CONCURRENCY)
    completed_count = 0
    success_count = 0
    failure_count = 0
    counter_lock = asyncio.Lock()

    async def _design_one(card_idx: int, card: dict[str, Any]) -> None:
        nonlocal completed_count, success_count, failure_count
        card_id = card.get("card_id")
        outfit_name = card.get("outfit_name")

        # Per-card budget check — short-circuit if the kill switch was flipped
        # mid-job or we crossed the ceiling.
        ok, reason = await _check_ai_budget(db)
        if not ok:
            failure_count += 1
            await emit(
                db,
                job_id,
                type="designer.image_failed",
                stage="generating_images",
                message=f"Skipped outfit {card_idx + 1}: {reason}.",
                progress_percent=_designer_progress(completed_count + failure_count, n),
                payload={"card_id": card_id, "reason": reason},
            )
            return

        async with semaphore:
            # started
            await emit(
                db,
                job_id,
                type="designer.image_started",
                stage="generating_images",
                message=f"Styling {outfit_name or f'outfit {card_idx + 1}'}…",
                progress_percent=_designer_progress(completed_count + failure_count, n),
                payload={"card_id": card_id, "outfit_name": outfit_name},
            )

            try:
                image_bytes, mime_type, provider_call = await generate_image_for_card(
                    photo_bytes, photo_content_type, card
                )
            except DesignerError as exc:
                await _record_provider_call(db, job_id, exc.provider_call)
                async with counter_lock:
                    failure_count += 1
                await emit(
                    db,
                    job_id,
                    type="designer.image_failed",
                    stage="generating_images",
                    message=f"Couldn't render {outfit_name or f'outfit {card_idx + 1}'}.",
                    progress_percent=_designer_progress(completed_count + failure_count, n),
                    payload={
                        "card_id": card_id,
                        "reason": exc.provider_call.get("error_code"),
                    },
                )
                return

            await _record_provider_call(db, job_id, provider_call)

            try:
                generated_image_id, signed_url = await store_generated_image(
                    db,
                    storage_client=storage_client,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    job_id=job_id,
                    try_on_session_id=try_on_session_id,
                    card=card,
                    customer_id=customer_id,
                    anonymous_session_id=anonymous_session_id,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "designer.store_failed", card_id=card_id, error=str(exc)
                )
                async with counter_lock:
                    failure_count += 1
                await emit(
                    db,
                    job_id,
                    type="designer.image_failed",
                    stage="generating_images",
                    message="Generated image couldn't be stored.",
                    progress_percent=_designer_progress(completed_count + failure_count, n),
                    payload={"card_id": card_id, "reason": "storage_error"},
                )
                return

            async with counter_lock:
                completed_count += 1
                success_count += 1
            await emit(
                db,
                job_id,
                type="designer.image_completed",
                stage="generating_images",
                message=f"{outfit_name or f'Outfit {card_idx + 1}'} ready.",
                progress_percent=_designer_progress(completed_count + failure_count, n),
                payload={
                    "card_id": card_id,
                    "outfit_name": outfit_name,
                    "generated_image_id": generated_image_id,
                    "image_url": signed_url,
                },
            )

    await asyncio.gather(*[_design_one(i, c) for i, c in enumerate(cards)])

    log.info(
        "designer.batch_done",
        job_id=job_id,
        success=success_count,
        failed=failure_count,
        total=n,
    )
    return success_count, failure_count


def _designer_progress(done: int, total: int) -> int:
    """Designer occupies the 60→98 progress band."""
    if total <= 0:
        return 60
    ratio = max(0.0, min(1.0, done / total))
    return int(60 + ratio * 38)


# ── Entry point ─────────────────────────────────────────────────────
async def run_tryon_orchestrator(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    db = get_db()
    job = await db[C.ai_jobs].find_one({"job_id": job_id})
    if not job:
        log.warning("tryon.job_not_found", job_id=job_id)
        return {"status": "missing", "job_id": job_id}

    try:
        # Stage 0 → validating_upload
        await _set_stage(db, job_id, status="validating_upload", current_stage="validating_upload")
        await emit(
            db,
            job_id,
            type="job.created",
            stage="validating_upload",
            message="Try-on starting…",
            progress_percent=5,
        )
        await emit(
            db,
            job_id,
            type="validator.completed",
            stage="validating_upload",
            message="Photo accepted.",
            progress_percent=10,
        )

        # Budget check before any provider call.
        ok, reason = await _check_ai_budget(db)
        if not ok:
            await _fail_job(
                db,
                job_id,
                reason=f"Try-on temporarily unavailable: {reason}",
                failed_stage="validating_upload",
                recoverable=True,
            )
            return {"status": "failed", "job_id": job_id, "reason": reason}

        # Load the uploaded photo once — needed for both Analyzer and Designer.
        loaded = await _load_uploaded_photo(db, job)
        if loaded is None:
            await _fail_job(
                db,
                job_id,
                reason="Could not load the uploaded photo from storage.",
                failed_stage="analyzing_photo",
            )
            return {"status": "failed", "job_id": job_id, "reason": "upload_missing"}
        photo_bytes, photo_content_type = loaded

        # Stage 1 — Analyzer (real Gemini call).
        await _set_stage(db, job_id, status="analyzing_photo", current_stage="analyzing_photo")
        profile = await _run_analyzer(db, job, photo_bytes, photo_content_type)
        if profile is None:
            return {"status": "failed", "job_id": job_id, "reason": "analyzer_failed"}

        # Budget check again before the (often-larger) Recommender call.
        ok, reason = await _check_ai_budget(db)
        if not ok:
            await _fail_job(
                db,
                job_id,
                reason=f"Try-on temporarily unavailable: {reason}",
                failed_stage="building_catalog_context",
                recoverable=True,
            )
            return {"status": "failed", "job_id": job_id, "reason": reason}

        # Stage 2 — Recommender. Refine jobs go through the ADK Stylist
        # agent (multi-tool loop); initial jobs use the legacy direct
        # Gemini call. Same return shape so the rest of the pipeline is
        # untouched.
        is_refine = bool((job.get("input") or {}).get("refined_from_session_id"))
        if is_refine:
            cards = await _run_recommender_via_agent(db, job, profile)
        else:
            cards = await _run_recommender(db, job, profile)
        if cards is None:
            return {"status": "failed", "job_id": job_id, "reason": "recommender_failed"}

        # Stage 3 — Designer (real Nano Banana, M4.4).
        ok, reason = await _check_ai_budget(db)
        if not ok:
            # Recommender already gave us text-only cards — we can still
            # complete partially. Skip the Designer entirely and mark partial.
            await emit(
                db,
                job_id,
                type="designer.skipped",
                stage="generating_images",
                message=f"Designer skipped: {reason}.",
                progress_percent=60,
            )
            success_count, failure_count = 0, len(cards)
        else:
            success_count, failure_count = await _run_designer(
                db,
                job,
                cards,
                photo_bytes=photo_bytes,
                photo_content_type=photo_content_type,
            )

        # Final status — completed if every image rendered, otherwise partial.
        final_status = "completed" if failure_count == 0 else "completed_partial"
        completed_at = _now()
        message = (
            f"Done — {success_count}/{len(cards)} outfit"
            f"{'s' if len(cards) != 1 else ''} rendered."
        )
        await emit(
            db,
            job_id,
            type="job.completed_partial" if final_status == "completed_partial" else "job.completed",
            stage="completed",
            message=message,
            progress_percent=100,
            payload={
                "outfit_count": len(cards),
                "rendered_count": success_count,
                "failed_count": failure_count,
            },
        )
        await db[C.ai_jobs].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": final_status,
                    "current_stage": "completed",
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                }
            },
        )
        log.info(
            "tryon.completed",
            job_id=job_id,
            final_status=final_status,
            outfits=len(cards),
            rendered=success_count,
            failed=failure_count,
        )
        return {
            "status": final_status,
            "job_id": job_id,
            "outfit_count": len(cards),
            "rendered_count": success_count,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("tryon.unhandled", job_id=job_id, error=str(exc))
        await _fail_job(
            db,
            job_id,
            reason="Something went wrong on our side. Please try again.",
            failed_stage="orchestrator",
            technical_detail=f"{type(exc).__name__}: {str(exc)[:500]}",
        )
        return {"status": "failed", "job_id": job_id, "error": str(exc)[:200]}
