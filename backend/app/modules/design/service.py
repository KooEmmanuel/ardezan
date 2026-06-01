"""Design Me service.

Synchronous on purpose: one Gemini call, one image. The customer
holds the connection (~10-15s). If we move to a queue later, the
router returns a job id instead of the finished session.

End-to-end flow:

1. Safety-validate the uploaded photo (same gate as try-on).
2. Look up the fabric, snapshot it.
3. Compute the estimate (locks in the price the customer sees).
4. Persist the photo to object storage (15-min retention while we render).
5. Call :func:`render_design`.
6. Persist the generated image + a ``design_sessions`` doc.
7. Return the public session shape.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.ai_repository import AiSettingsRepository
from app.modules.design.designer import (
    DesignerError,
    render_design,
    store_design_image,
)
from app.modules.design.schemas import (
    DesignInputs,
    DesignSessionCreateResponse,
    FabricSnapshot,
)
from app.modules.fabrics.pricing import estimate_cost
from app.modules.try_on.safety import validate_upload
from app.storage import get_storage

log = get_logger(__name__)


# We use the same 15-min retention for the customer's uploaded photo —
# it's only needed long enough to render the design.
PHOTO_RETENTION_MIN = 15


def _design_session_id() -> str:
    return f"des_{secrets.token_hex(8)}"


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _anon_session_id() -> str:
    return f"anon_{secrets.token_hex(8)}"


def _guess_extension(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "heic" in ct or "heif" in ct:
        return ".heic"
    return ".bin"


class DesignService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings = get_settings()
        self.storage = get_storage()
        self.ai_settings_repo = AiSettingsRepository(db)

    async def _load_fabric(self, fabric_id: str) -> dict[str, Any]:
        doc = await self.db[C.fabrics].find_one(
            {"fabric_id": fabric_id, "active": True}, projection={"_id": 0}
        )
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Fabric not found: {fabric_id}",
                http_status=404,
            )
        return doc

    async def create_session(
        self,
        *,
        photo_bytes: bytes,
        content_type: str,
        inputs: DesignInputs,
        customer_id: str | None,
        anonymous_session_id: str | None,
        age_confirmed: bool,
        # Optional style reference (Pinterest screenshot, photo of a
        # similar piece, etc.). When present we store it, pass it to the
        # designer, and surface it on the admin tailor brief.
        reference_bytes: bytes | None = None,
        reference_content_type: str | None = None,
    ) -> DesignSessionCreateResponse:
        # 1. Age gate — same as try-on.
        if not customer_id and not age_confirmed:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Age confirmation required to upload a photo.",
                http_status=400,
                details={"hint": "Submit ``age_confirmed=true`` in the form."},
            )

        # 2. AI kill switch.
        ai_settings = await self.ai_settings_repo.get_resolved()
        if ai_settings["kill_switch_enabled"]:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Design Me is temporarily unavailable.",
                http_status=503,
                details={"reason": "kill_switch_enabled"},
            )

        # 3. Fabric + compatibility check.
        fabric = await self._load_fabric(inputs.fabric_id)
        if inputs.piece_type not in fabric.get("suitable_for", []):
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                f"This fabric isn't a good fit for a {inputs.piece_type}.",
                http_status=400,
                details={
                    "fabric_id": inputs.fabric_id,
                    "suitable_for": fabric.get("suitable_for", []),
                },
            )

        # 4. Upload safety.
        safety = await validate_upload(photo_bytes, content_type)
        if not safety.passed:
            raise ApiError(
                ErrorCode.UPLOAD_REJECTED,
                safety.reason or "Photo failed safety checks.",
                http_status=400,
                details={
                    "gate": safety.failed_gate or "",
                    **safety.file_metadata,
                },
            )

        # 5. Compute the estimate (locked into the session doc).
        # Pull live admin-managed pricing overrides.
        from app.modules.admin.commerce_router import get_commerce_config
        cfg = await get_commerce_config(self.db)
        estimate = estimate_cost(
            fabric_id=inputs.fabric_id,
            cost_per_yard_amount=int(fabric["cost_per_yard_amount"]),
            currency=fabric.get("currency", "USD"),
            piece_type=inputs.piece_type,
            complexity=inputs.complexity,
            yardage_overrides=cfg.yardage_by_piece,
            tailoring_overrides=cfg.base_tailoring_by_piece,
            complexity_overrides=cfg.complexity_multiplier,
        )

        # 6. Persist the photo.
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=PHOTO_RETENTION_MIN)
        upload_media_id = _media_id()
        ext = _guess_extension(content_type)
        key_prefix = (
            "design/uploads/registered" if customer_id else "design/uploads/anonymous"
        )
        object_key = f"{key_prefix}/{upload_media_id}{ext}"

        try:
            written_key = await self.storage.put_object(
                object_key,
                photo_bytes,
                content_type=content_type,
                metadata={
                    "media_asset_id": upload_media_id,
                    "owner_type": "design_upload",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("design_me.upload_failed", error=str(exc))
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

        design_session_id = _design_session_id()

        # 6b. Optional style reference image. We do NOT run it through the
        # safety pipeline (it's a curated reference, not a photo of a
        # person), but we cap the size at 8 MB to avoid abuse and we
        # do trust ``Content-Type`` from the multipart upload.
        reference_media_id: str | None = None
        if reference_bytes and reference_content_type:
            if len(reference_bytes) > 8 * 1024 * 1024:
                raise ApiError(
                    ErrorCode.VALIDATION_ERROR,
                    "Style reference is too large (8 MB max).",
                    http_status=400,
                )
            reference_media_id = _media_id()
            ref_ext = _guess_extension(reference_content_type)
            ref_key_prefix = (
                "design/references/registered"
                if customer_id
                else "design/references/anonymous"
            )
            ref_object_key = f"{ref_key_prefix}/{reference_media_id}{ref_ext}"
            try:
                ref_written_key = await self.storage.put_object(
                    ref_object_key,
                    reference_bytes,
                    content_type=reference_content_type,
                    metadata={
                        "media_asset_id": reference_media_id,
                        "owner_type": "design_reference",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("design_me.reference_upload_failed", error=str(exc))
                raise ApiError(
                    ErrorCode.INTERNAL_ERROR,
                    "Could not store the style reference.",
                    http_status=502,
                ) from exc

            await self.db[C.media_assets].insert_one(
                {
                    "media_asset_id": reference_media_id,
                    "owner_type": "design_session",
                    "owner_id": design_session_id,
                    "purpose": "style_reference",
                    "storage": {
                        "bucket": self.settings.s3_bucket,
                        "object_key": ref_written_key,
                        "content_type": reference_content_type,
                        "byte_size": len(reference_bytes),
                    },
                    "access": {"visibility": "private", "signed_url_required": True},
                    "retention": {
                        "policy": (
                            "anonymous_15_min"
                            if not customer_id
                            else "registered_until_deleted"
                        ),
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

        # 7. media_assets row for the uploaded photo (retention worker eats it).
        await self.db[C.media_assets].insert_one(
            {
                "media_asset_id": upload_media_id,
                "owner_type": "design_session",
                "owner_id": design_session_id,
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

        fabric_snapshot = FabricSnapshot(
            fabric_id=fabric["fabric_id"],
            name=fabric["name"],
            color_family=fabric["color_family"],
            cost_per_yard_amount=int(fabric["cost_per_yard_amount"]),
            currency=fabric.get("currency", "USD"),
            weight=fabric["weight"],
            finish=fabric.get("finish"),
        )

        # 8. Insert the draft session doc up front so a partial failure is still recoverable.
        await self.db[C.design_sessions].insert_one(
            {
                "design_session_id": design_session_id,
                "customer_id": customer_id,
                "anonymous_session_id": anon_id,
                "status": "draft",
                "uploaded_media_asset_id": upload_media_id,
                "reference_media_asset_id": reference_media_id,
                "generated_media_asset_id": None,
                "fabric_snapshot": fabric_snapshot.model_dump(),
                "piece_type": inputs.piece_type,
                "complexity": inputs.complexity,
                "brief": inputs.brief,
                "fit_note": inputs.fit_note,
                "estimate": estimate.model_dump(),
                "provider_calls": [],
                "failure_reason": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        # 9. Render. We don't reraise — a failed render still leaves a session
        # the customer can retry from. The router translates `failure_reason`
        # into a user-friendly message.
        try:
            image_bytes, mime_type, call = await render_design(
                photo_bytes=photo_bytes,
                photo_content_type=content_type,
                piece_type=inputs.piece_type,
                brief=inputs.brief,
                fit_note=inputs.fit_note,
                fabric_snapshot=fabric_snapshot.model_dump(),
                reference_bytes=reference_bytes,
                reference_content_type=reference_content_type,
            )
        except DesignerError as exc:
            await self.db[C.design_sessions].update_one(
                {"design_session_id": design_session_id},
                {
                    "$set": {
                        "status": "failed",
                        "failure_reason": str(exc),
                        "updated_at": datetime.now(UTC),
                    },
                    "$push": {"provider_calls": exc.provider_call},
                },
            )
            return DesignSessionCreateResponse(
                design_session_id=design_session_id,
                status="failed",
                estimate=estimate,
                image_url=None,
                failure_reason=(
                    "We couldn't render your design. Try a clearer photo or "
                    "a shorter brief — your card and estimate are saved."
                ),
            )

        # 10. Persist the render + flip the session to `ready`.
        generated_media_id, signed_url = await store_design_image(
            self.db,
            storage_client=self.storage,
            image_bytes=image_bytes,
            mime_type=mime_type,
            design_session_id=design_session_id,
            customer_id=customer_id,
            anonymous_session_id=anon_id,
        )
        await self.db[C.design_sessions].update_one(
            {"design_session_id": design_session_id},
            {
                "$set": {
                    "status": "ready",
                    "generated_media_asset_id": generated_media_id,
                    "image_url_cached": signed_url,
                    "updated_at": datetime.now(UTC),
                },
                "$push": {"provider_calls": call},
            },
        )

        return DesignSessionCreateResponse(
            design_session_id=design_session_id,
            status="ready",
            estimate=estimate,
            image_url=signed_url,
            failure_reason=None,
        )

    async def list_for_customer(
        self,
        customer_id: str,
        *,
        limit: int = 24,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return the customer's design sessions newest-first.

        Image URLs are re-signed at read time. Sessions still in
        ``draft`` (render in flight or failed before persistence) are
        excluded — the activity hub only wants real, addressable rows.
        """
        query = {
            "customer_id": customer_id,
            "status": {"$in": ["ready", "failed"]},
        }
        cursor = (
            self.db[C.design_sessions]
            .find(query, projection={"_id": 0})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        sessions = await cursor.to_list(limit)
        total = await self.db[C.design_sessions].count_documents(query)

        # Re-sign all the images in one batch so the grid doesn't have
        # to do a per-row signed-URL fetch.
        media_ids = [
            s["generated_media_asset_id"]
            for s in sessions
            if s.get("generated_media_asset_id")
        ]
        url_by_media: dict[str, str] = {}
        if media_ids:
            media_cursor = self.db[C.media_assets].find(
                {"media_asset_id": {"$in": media_ids}},
                projection={"media_asset_id": 1, "storage": 1, "_id": 0},
            )
            async for m in media_cursor:
                key = (m.get("storage") or {}).get("object_key")
                if key:
                    url_by_media[m["media_asset_id"]] = (
                        await self.storage.presigned_get_url(key, expires_in=3600)
                    )

        items: list[dict[str, Any]] = []
        for s in sessions:
            fabric = s.get("fabric_snapshot") or {}
            estimate = s.get("estimate") or {}
            piece = (s.get("piece_type") or "piece").title()
            items.append(
                {
                    "design_session_id": s["design_session_id"],
                    "status": s["status"],
                    "title": f"Custom {piece} in {fabric.get('name', 'fabric')}",
                    "fabric_name": fabric.get("name", "Custom fabric"),
                    "piece_type": s["piece_type"],
                    "image_url": url_by_media.get(s.get("generated_media_asset_id")),
                    "total_amount": int(estimate.get("total_amount", 0)),
                    "currency": estimate.get("currency", "USD"),
                    "created_at": s["created_at"],
                }
            )
        return items, total

    async def get_public(self, design_session_id: str) -> dict[str, Any]:
        doc = await self.db[C.design_sessions].find_one(
            {"design_session_id": design_session_id}, projection={"_id": 0}
        )
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                "Design session not found.",
                http_status=404,
            )

        # Re-sign the generated image URL on each read so it stays fresh.
        image_url: str | None = None
        gen_id = doc.get("generated_media_asset_id")
        if gen_id:
            media = await self.db[C.media_assets].find_one(
                {"media_asset_id": gen_id}, projection={"storage": 1, "_id": 0}
            )
            if media and (media.get("storage") or {}).get("object_key"):
                image_url = await self.storage.presigned_get_url(
                    media["storage"]["object_key"], expires_in=3600
                )
        return {**doc, "image_url": image_url}
