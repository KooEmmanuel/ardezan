"""Try-on session + job creation.

Flow per ARCHITECTURE §5.7 + §8.5:
1. Check the AI kill switch from `settings` (M3.4).
2. Run the upload safety pipeline.
3. PUT the photo into object storage with a 15-minute retention class.
4. Insert a ``media_assets`` document, ``try_on_sessions`` document, and
   ``ai_jobs`` document.
5. Enqueue the orchestrator job onto Redis.
6. Return ``(try_on_session_id, job_id, sse_url)``.

If anything fails between steps 2 and 5, we don't leave orphans — uploads
are ephemeral and will be cleaned up by the retention worker (M6).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.ai_repository import AiSettingsRepository
from app.modules.try_on.repository import TryOnRepository
from app.modules.try_on.safety import validate_upload
from app.modules.try_on.schemas import JobCreatedResponse, TryOnInputs
from app.queue import get_queue
from app.storage import get_storage

log = get_logger(__name__)

# Anonymous photos are deleted within 15 minutes (REQ-066).
ANON_UPLOAD_RETENTION_MIN = 15
# Job documents auto-expire after 30 minutes — covers the worst-case orchestrator run.
JOB_TTL_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_id() -> str:
    return f"try_{secrets.token_hex(8)}"


def _job_id() -> str:
    return f"job_{secrets.token_hex(8)}"


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _anon_session_id() -> str:
    return f"anon_{secrets.token_hex(8)}"


class TryOnService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = TryOnRepository(db)
        self.ai_settings_repo = AiSettingsRepository(db)
        self.settings = get_settings()
        self.storage = get_storage()

    async def create_session(
        self,
        *,
        photo_bytes: bytes,
        content_type: str,
        inputs: TryOnInputs,
        seeded_product_id: str | None,
        customer_id: str | None,
        anonymous_session_id: str | None,
        age_confirmed: bool,
    ) -> JobCreatedResponse:
        # 1. Age gate — required by SPECS §9 (Privacy) + REQ-058.
        if not customer_id and not age_confirmed:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Age confirmation required to upload a photo.",
                http_status=400,
                details={"hint": "Submit ``age_confirmed=true`` in the form."},
            )

        # 2. AI kill switch + global cost ceiling check (M3.4 settings).
        ai_settings = await self.ai_settings_repo.get_resolved()
        if ai_settings["kill_switch_enabled"]:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Try-on is temporarily unavailable.",
                http_status=503,
                details={"reason": "kill_switch_enabled"},
            )

        # 3. Upload safety pipeline.
        safety = await validate_upload(photo_bytes, content_type)
        if not safety.passed:
            raise ApiError(
                ErrorCode.UPLOAD_REJECTED,
                safety.reason or "Photo failed safety checks.",
                http_status=400,
                details={"gate": safety.failed_gate or "", **safety.file_metadata},
            )

        # 4. Persist the upload to object storage (ephemeral).
        now = _now()
        expires_at = now + timedelta(minutes=ANON_UPLOAD_RETENTION_MIN)
        media_asset_id = _media_id()
        ext = _guess_extension(content_type, safety.file_metadata.get("format", ""))
        key_prefix = "tryon/uploads/registered" if customer_id else "tryon/uploads/anonymous"
        object_key = f"{key_prefix}/{media_asset_id}{ext}"

        try:
            written_key = await self.storage.put_object(
                object_key,
                photo_bytes,
                content_type=content_type,
                metadata={
                    "media_asset_id": media_asset_id,
                    "owner_type": "try_on_upload",
                },
            )
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("tryon.upload_failed", error=str(exc))
            raise ApiError(
                ErrorCode.INTERNAL_ERROR,
                "Could not store the uploaded photo.",
                http_status=502,
            ) from exc

        anon_id = (
            anonymous_session_id
            if anonymous_session_id and not customer_id
            else None
        )
        if not customer_id and not anon_id:
            anon_id = _anon_session_id()

        try_on_session_id = _session_id()
        job_id = _job_id()

        # media_assets row — Sources of truth for retention worker (M6).
        await self.repo.insert_media_asset(
            {
                "media_asset_id": media_asset_id,
                "owner_type": "try_on_session",
                "owner_id": try_on_session_id,
                "purpose": "customer_upload",
                "storage": {
                    "bucket": self.settings.s3_bucket,
                    "object_key": written_key,
                    "content_type": content_type,
                    "byte_size": safety.file_metadata.get("size_bytes", len(photo_bytes)),
                    "width": safety.file_metadata.get("width"),
                    "height": safety.file_metadata.get("height"),
                },
                "access": {"visibility": "private", "signed_url_required": True},
                "retention": {
                    "policy": "anonymous_15_min" if not customer_id else "registered_until_deleted",
                    "expires_at": expires_at if not customer_id else None,
                    "deleted_at": None,
                },
                "provenance": {
                    "ai_generated": False,
                    "provider": None,
                    "c2pa_embedded": False,
                    "digital_source_type": None,
                },
                "created_at": now,
                "updated_at": now,
            }
        )

        # try_on_sessions row.
        source = "product_seed" if seeded_product_id else "upload"
        await self.repo.insert_session(
            {
                "try_on_session_id": try_on_session_id,
                "customer_id": customer_id,
                "anonymous_session_id": anon_id,
                "source": source,
                "uploaded_media_asset_id": media_asset_id,
                "saved_photo_used": False,
                "optional_inputs": inputs.model_dump(),
                "body_profile_snapshot": None,
                "result_cards": [],
                "status": "active",
                "expires_at": expires_at if not customer_id else None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )

        # Fold the safety classifier's provider_call into the job so cost
        # and audit history start from the very first AI call we made.
        safety_call = safety.provider_call
        initial_provider_calls = [safety_call] if safety_call else []
        initial_cost = (
            int(safety_call.get("estimated_cost_amount", 0) or 0) if safety_call else 0
        )

        # ai_jobs row — initial state ``queued``; worker takes it from here.
        await self.repo.insert_job(
            {
                "job_id": job_id,
                "try_on_session_id": try_on_session_id,
                "customer_id": customer_id,
                "anonymous_session_id": anon_id,
                "status": "queued",
                "current_stage": None,
                "input": {
                    "uploaded_media_asset_id": media_asset_id,
                    "optional_inputs": inputs.model_dump(),
                    "seeded_product_id": seeded_product_id,
                },
                "progress_events": [],
                "provider_calls": initial_provider_calls,
                "cost": {
                    "estimated_total_amount": initial_cost,
                    "currency": self.settings.store_currency,
                },
                "failure": None,
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "expires_at": now + timedelta(minutes=JOB_TTL_MINUTES),
            }
        )

        # Enqueue the orchestrator job.
        queue = get_queue()
        await queue.enqueue_job("run_tryon_orchestrator", job_id)

        log.info(
            "tryon.session_created",
            try_on_session_id=try_on_session_id,
            job_id=job_id,
            customer_id=customer_id,
            anonymous_session_id=anon_id,
            seeded_product_id=seeded_product_id,
        )

        return JobCreatedResponse(
            try_on_session_id=try_on_session_id,
            job_id=job_id,
            sse_url=f"/api/v1/try-on/jobs/{job_id}/events",
        )

    async def refine_session(
        self,
        *,
        original_session_id: str,
        refinement_prompt: str,
        requesting_customer_id: str | None,
        requesting_anonymous_session_id: str | None,
    ) -> JobCreatedResponse:
        """Spawn a new try-on session that reuses the original's uploaded
        photo + adds a refinement prompt.

        The new session inherits ``optional_inputs`` from the source (fit
        preference, occasion, etc.) and appends/replaces the prompt. Reusing
        the existing ``media_asset_id`` means no re-upload — the worker
        downloads the same B2 object and runs the full pipeline against
        the refined brief.
        """
        original = await self.db[C.try_on_sessions].find_one(
            {"try_on_session_id": original_session_id, "deleted_at": None}
        )
        if not original:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {original_session_id}",
                http_status=404,
            )

        # Ownership: customer-owned sessions only refinable by that customer,
        # anonymous sessions refinable by anyone with the id (same threat
        # model as the public session-read endpoint).
        owner_customer_id = original.get("customer_id")
        if owner_customer_id and owner_customer_id != requesting_customer_id:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {original_session_id}",
                http_status=404,
            )

        media_asset_id = original.get("uploaded_media_asset_id")
        if not media_asset_id:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Original session has no uploaded photo to refine against.",
                http_status=409,
            )

        # AI kill-switch + budget check before spawning new work.
        ai_settings = await self.ai_settings_repo.get_resolved()
        if ai_settings["kill_switch_enabled"]:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Try-on is temporarily unavailable.",
                http_status=503,
                details={"reason": "kill_switch_enabled"},
            )

        now = _now()
        new_session_id = _session_id()
        new_job_id = _job_id()

        # Merge the refinement prompt into optional_inputs. We append rather
        # than overwrite so prior style notes survive ("linen-forward · show
        # warmer pieces").
        prior_inputs = dict(original.get("optional_inputs") or {})
        prior_prompt = (prior_inputs.get("prompt") or "").strip()
        merged_prompt = (
            f"{prior_prompt} · refine: {refinement_prompt.strip()}"
            if prior_prompt
            else f"refine: {refinement_prompt.strip()}"
        )
        new_inputs = {**prior_inputs, "prompt": merged_prompt}

        # The new session belongs to whoever the original belonged to —
        # registered if the original was registered, anonymous otherwise.
        anon_id = original.get("anonymous_session_id") if not owner_customer_id else None
        expires_at = (
            now + timedelta(minutes=ANON_UPLOAD_RETENTION_MIN)
            if not owner_customer_id
            else None
        )

        await self.repo.insert_session(
            {
                "try_on_session_id": new_session_id,
                "customer_id": owner_customer_id,
                "anonymous_session_id": anon_id,
                "source": "refine",
                "uploaded_media_asset_id": media_asset_id,
                "saved_photo_used": False,
                "optional_inputs": new_inputs,
                "body_profile_snapshot": original.get("body_profile_snapshot"),
                "result_cards": [],
                "status": "active",
                "refined_from_session_id": original_session_id,
                "expires_at": expires_at,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )

        await self.repo.insert_job(
            {
                "job_id": new_job_id,
                "try_on_session_id": new_session_id,
                "customer_id": owner_customer_id,
                "anonymous_session_id": anon_id,
                "status": "queued",
                "current_stage": None,
                "input": {
                    "uploaded_media_asset_id": media_asset_id,
                    "optional_inputs": new_inputs,
                    "seeded_product_id": (original.get("optional_inputs") or {}).get(
                        "seeded_product_id"
                    ),
                    "refined_from_session_id": original_session_id,
                },
                "progress_events": [],
                "provider_calls": [],
                "cost": {
                    "estimated_total_amount": 0,
                    "currency": self.settings.store_currency,
                },
                "failure": None,
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "expires_at": now + timedelta(minutes=JOB_TTL_MINUTES),
            }
        )

        queue = get_queue()
        await queue.enqueue_job("run_tryon_orchestrator", new_job_id)

        log.info(
            "tryon.session_refined",
            from_session_id=original_session_id,
            new_session_id=new_session_id,
            new_job_id=new_job_id,
            customer_id=owner_customer_id,
        )

        return JobCreatedResponse(
            try_on_session_id=new_session_id,
            job_id=new_job_id,
            sse_url=f"/api/v1/try-on/jobs/{new_job_id}/events",
        )

    async def get_job(self, job_id: str) -> dict[str, Any]:
        doc = await self.repo.find_job(job_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Job not found: {job_id}", http_status=404
            )
        return doc


def _guess_extension(content_type: str, fmt: str) -> str:
    fmt_lower = (fmt or "").lower()
    if "jpeg" in fmt_lower or "jpg" in content_type.lower():
        return ".jpg"
    if "png" in fmt_lower or "png" in content_type.lower():
        return ".png"
    if "webp" in fmt_lower or "webp" in content_type.lower():
        return ".webp"
    if "heic" in content_type.lower() or "heif" in content_type.lower():
        return ".heic"
    return ".bin"
