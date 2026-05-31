"""Admin media operations — attach images to products.

Two ingestion modes:

- ``upload`` — admin uploads a file (multipart). The bytes go straight to
  object storage; a ``media_assets`` row is created with provenance
  ``ai_generated=False``.
- ``ai-generate`` — admin asks the system to generate a flat product photo
  via Gemini 2.5 Flash Image (Nano Banana). Uses the product's title +
  category + material as the prompt seed. Provenance ``ai_generated=True``.

Either way the result is the same: a ``media_assets`` row + a patched
``product.primary_media_asset_id`` (or appended to ``media_asset_ids`` if a
primary already exists). Every action writes an ``audit_logs`` entry so a
human can see when an image was added and by whom.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from google.genai import types
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.repository import AdminRepository
from app.modules.try_on.gemini_client import get_gemini_client
from app.storage import get_storage

log = get_logger(__name__)

MediaSource = Literal["upload", "ai_generate"]

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _extension(mime_type: str) -> str:
    mt = mime_type.lower()
    if "png" in mt:
        return ".png"
    if "webp" in mt:
        return ".webp"
    return ".jpg"


def _build_ai_prompt(product: dict[str, Any]) -> str:
    """Compose a flat-lay product photo prompt from the product doc."""
    title = product["title"]
    category = product.get("category") or "garment"
    subcategory = product.get("subcategory") or category
    details = product.get("product_details") or {}
    material = details.get("material") or "premium materials"
    palette = ((product.get("ai") or {}).get("color_palette")) or []
    primary_color = palette[0] if palette else "neutral"

    return (
        f"Editorial product photography of one single {title} ({subcategory}, {category}). "
        f"Material: {material}. Primary color: {primary_color}.\n\n"
        "Style:\n"
        "- Clean studio shot on a flat off-white background (#fafafa).\n"
        "- Soft, even, diffused lighting. Subtle natural shadow.\n"
        "- Garment laid flat or styled cleanly (no person, no mannequin).\n"
        "- Centered composition with generous negative space.\n"
        "- High resolution, sharp focus, premium minimalist aesthetic.\n"
        "- 4:5 portrait orientation.\n"
        "- Color-accurate, true-to-life rendering.\n\n"
        "Avoid: people, faces, hands, mannequins, props, logos, watermarks, "
        "text overlays, busy backgrounds, vintage filters."
    )


def _extract_image(response: Any) -> tuple[bytes, str] | None:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None) or "image/png"
            if data:
                return data, mime
    return None


class AdminMediaService:
    """Owns image attach + AI-generate for products."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings = get_settings()
        self.audit = AdminRepository(db)

    async def _load_product(self, product_id: str) -> dict[str, Any]:
        doc = await self.db[C.products].find_one(
            {"product_id": product_id, "deleted_at": None}
        )
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Product not found: {product_id}",
                http_status=404,
            )
        return doc

    async def _persist(
        self,
        *,
        product: dict[str, Any],
        image_bytes: bytes,
        mime_type: str,
        ai_generated: bool,
        set_as_primary: bool,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        media_asset_id = _media_id()
        ext = _extension(mime_type)
        object_key = f"catalog/products/{product['slug']}/{media_asset_id}{ext}"

        storage = get_storage()
        written_key = await storage.put_object(
            object_key,
            image_bytes,
            content_type=mime_type,
            metadata={
                "media_asset_id": media_asset_id,
                "product_id": product["product_id"],
                "slug": product["slug"],
                "ai_generated": "true" if ai_generated else "false",
                "purpose": "catalog_image",
                "uploaded_by": admin["admin_id"],
            },
        )

        now = _now()
        media_doc = {
            "media_asset_id": media_asset_id,
            "owner_type": "product",
            "owner_id": product["product_id"],
            "purpose": "catalog_image",
            "storage": {
                "bucket": self.settings.s3_bucket,
                "object_key": written_key,
                "content_type": mime_type,
                "byte_size": len(image_bytes),
            },
            "access": {"visibility": "private", "signed_url_required": True},
            "retention": {
                # Catalog images stay until an admin explicitly removes them.
                "policy": "permanent",
                "expires_at": None,
                "deleted_at": None,
            },
            "provenance": {
                "ai_generated": ai_generated,
                "provider": "gemini" if ai_generated else None,
                "c2pa_embedded": False,
                "digital_source_type": (
                    "trainedAlgorithmicMedia" if ai_generated else None
                ),
            },
            "uploaded_by_admin_id": admin["admin_id"],
            "created_at": now,
            "updated_at": now,
        }
        await self.db[C.media_assets].insert_one(media_doc)

        update: dict[str, Any] = {
            "$addToSet": {"media_asset_ids": media_asset_id},
            "$set": {
                "updated_at": now,
                "updated_by_admin_id": admin["admin_id"],
            },
        }
        # Set as primary if requested OR if there isn't one yet.
        primary_existed = bool(product.get("primary_media_asset_id"))
        if set_as_primary or not primary_existed:
            update["$set"]["primary_media_asset_id"] = media_asset_id

        await self.db[C.products].update_one(
            {"product_id": product["product_id"]}, update
        )

        await self.audit.write_audit(
            actor_id=admin["admin_id"],
            action="admin.product.media_attached",
            target_type="product",
            target_id=product["product_id"],
            after={
                "media_asset_id": media_asset_id,
                "object_key": written_key,
                "ai_generated": ai_generated,
                "primary": set_as_primary or not primary_existed,
            },
        )
        log.info(
            "admin.media_attached",
            product_id=product["product_id"],
            media_asset_id=media_asset_id,
            ai_generated=ai_generated,
        )
        return {**media_doc, "is_primary": set_as_primary or not primary_existed}

    # ── Upload (admin uploads a file) ──────────────────────────
    async def attach_uploaded(
        self,
        *,
        product_id: str,
        file_bytes: bytes,
        content_type: str,
        set_as_primary: bool,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        if content_type.lower() not in _ALLOWED_CONTENT_TYPES:
            raise ApiError(
                ErrorCode.UPLOAD_REJECTED,
                f"Unsupported content type {content_type}.",
                http_status=400,
                details={"allowed": sorted(_ALLOWED_CONTENT_TYPES)},
            )
        if not file_bytes:
            raise ApiError(
                ErrorCode.UPLOAD_REJECTED,
                "Uploaded file is empty.",
                http_status=400,
            )
        if len(file_bytes) > _MAX_UPLOAD_BYTES:
            raise ApiError(
                ErrorCode.UPLOAD_REJECTED,
                f"File exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                http_status=400,
            )

        product = await self._load_product(product_id)
        return await self._persist(
            product=product,
            image_bytes=file_bytes,
            mime_type=content_type,
            ai_generated=False,
            set_as_primary=set_as_primary,
            admin=admin,
        )

    # ── Site media (hero, categories, editorial) ───────────────
    async def attach_site_media_ai(
        self,
        *,
        slot_name: str,
        prompt: str,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a branded image via Nano Banana for a UI slot and persist it.

        Marks any existing media for the same slot as deleted (retention
        worker will sweep storage). Always sets the new image as the
        canonical media for that slot.
        """
        if not self.settings.gemini_api_key:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Image generation requires GEMINI_API_KEY.",
                http_status=503,
            )

        client = get_gemini_client()
        model_name = self.settings.gemini_model_designer
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            temperature=0.55,
        )
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "admin.site_media_ai_call_failed",
                slot=slot_name,
                error=str(exc)[:200],
            )
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Image generation failed — try again.",
                http_status=502,
                details={"error": str(exc)[:200]},
            ) from exc

        extracted = _extract_image(response)
        if extracted is None:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "The model returned no image (safety block or empty output).",
                http_status=502,
            )
        image_bytes, mime_type = extracted

        media_asset_id = _media_id()
        ext = _extension(mime_type)
        object_key = f"site/{slot_name}/{media_asset_id}{ext}"
        storage = get_storage()
        written_key = await storage.put_object(
            object_key,
            image_bytes,
            content_type=mime_type,
            metadata={
                "media_asset_id": media_asset_id,
                "slot_name": slot_name,
                "ai_generated": "true",
                "purpose": "site_media",
                "uploaded_by": admin["admin_id"],
            },
        )

        now = _now()
        # Mark prior media for this slot as deleted so the retention worker
        # cleans them up. We don't physically delete here — that lets us
        # roll back by clearing ``deleted_at`` if needed.
        await self.db[C.media_assets].update_many(
            {
                "owner_type": "site_media",
                "owner_id": slot_name,
                "retention.deleted_at": None,
            },
            {"$set": {"retention.deleted_at": now, "updated_at": now}},
        )

        media_doc = {
            "media_asset_id": media_asset_id,
            "owner_type": "site_media",
            "owner_id": slot_name,
            "purpose": "site_media",
            "storage": {
                "bucket": self.settings.s3_bucket,
                "object_key": written_key,
                "content_type": mime_type,
                "byte_size": len(image_bytes),
            },
            "access": {"visibility": "private", "signed_url_required": True},
            "retention": {
                "policy": "permanent",
                "expires_at": None,
                "deleted_at": None,
            },
            "provenance": {
                "ai_generated": True,
                "provider": "gemini",
                "c2pa_embedded": False,
                "digital_source_type": "trainedAlgorithmicMedia",
            },
            "uploaded_by_admin_id": admin["admin_id"],
            "prompt": prompt,
            "created_at": now,
            "updated_at": now,
        }
        await self.db[C.media_assets].insert_one(media_doc)

        await self.audit.write_audit(
            actor_id=admin["admin_id"],
            action="admin.site_media.replaced",
            target_type="site_media",
            target_id=slot_name,
            after={
                "media_asset_id": media_asset_id,
                "object_key": written_key,
                "ai_generated": True,
            },
        )
        log.info(
            "admin.site_media_replaced",
            slot=slot_name,
            media_asset_id=media_asset_id,
        )
        return media_doc

    # ── AI-generate (Nano Banana) ──────────────────────────────
    async def attach_ai_generated(
        self,
        *,
        product_id: str,
        set_as_primary: bool,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Image generation requires GEMINI_API_KEY.",
                http_status=503,
            )

        product = await self._load_product(product_id)
        client = get_gemini_client()
        model_name = self.settings.gemini_model_designer
        prompt = _build_ai_prompt(product)
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            temperature=0.4,
        )

        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "admin.media_ai_call_failed",
                product_id=product_id,
                error=str(exc)[:200],
            )
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Image generation failed — try again.",
                http_status=502,
                details={"error": str(exc)[:200]},
            ) from exc

        extracted = _extract_image(response)
        if extracted is None:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "The model returned no image (safety block or empty output).",
                http_status=502,
            )
        image_bytes, mime_type = extracted
        return await self._persist(
            product=product,
            image_bytes=image_bytes,
            mime_type=mime_type,
            ai_generated=True,
            set_as_primary=set_as_primary,
            admin=admin,
        )
