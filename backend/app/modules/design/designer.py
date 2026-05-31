"""Design Me image renderer.

Different from the try-on designer in two ways:

1. The garment is *imagined*, not pulled from the catalog. The customer's
   brief is the source of truth, so we lean on it in the prompt.
2. The fabric is the visual anchor. We describe its weight, finish, and
   color family so the render reads as that material, not generic cloth.

The output is one image: the customer wearing the imagined piece.
"""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from google.genai import types
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db import C
from app.logging_setup import get_logger
from app.modules.fabrics.schemas import PieceType
from app.modules.try_on.cost import estimate_image_cost_cents
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)


# Anonymous custom-design renders share the 24h retention class with
# anonymous try-on renders — the customer either checks out or it's gone.
ANONYMOUS_GENERATED_RETENTION_HOURS = 24


class DesignerError(RuntimeError):
    def __init__(self, provider_call: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.provider_call = provider_call


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _generated_image_id() -> str:
    return f"genimg_{secrets.token_hex(8)}"


# ── Prompt building ────────────────────────────────────────────────
# We translate the fabric metadata into adjectives the image model
# actually responds to. "warm-neutrals/medium/structured" is meaningless
# to Nano Banana — "warm sand-coloured, medium-weight twill with a
# crisp structured hand" gets us closer to the right material.

_COLOR_FAMILY_DESCRIPTORS: dict[str, str] = {
    "warm-neutrals": "warm sand and stone tones",
    "cool-neutrals": "cool grey and slate tones",
    "rich-tones": "deep chocolate and warm umber tones",
    "denim": "deep indigo",
}

_WEIGHT_DESCRIPTORS: dict[str, str] = {
    "light": "lightweight, with soft drape",
    "medium": "medium-weight, holds a clean line",
    "heavy": "substantial, structured drape",
}

_FINISH_DESCRIPTORS: dict[str, str] = {
    "matte": "matte surface, no sheen",
    "lustrous": "subtle lustrous sheen",
    "brushed": "brushed surface with a soft hand",
    "structured": "structured weave, crisp surface",
}


def _describe_fabric(snapshot: dict[str, Any]) -> str:
    color = _COLOR_FAMILY_DESCRIPTORS.get(
        snapshot.get("color_family", ""), snapshot.get("color_family", "")
    )
    weight = _WEIGHT_DESCRIPTORS.get(snapshot.get("weight", ""), "")
    finish = _FINISH_DESCRIPTORS.get(
        snapshot.get("finish") or "", snapshot.get("finish") or ""
    )
    name = snapshot.get("name", "fabric")
    parts = [name, color, weight, finish]
    return ", ".join(p for p in parts if p)


def build_design_prompt(
    *,
    piece_type: PieceType,
    brief: str,
    fit_note: str | None,
    fabric_snapshot: dict[str, Any],
) -> str:
    fabric_desc = _describe_fabric(fabric_snapshot)
    fit_line = f"Fit: {fit_note}." if fit_note else ""
    return (
        f"Render the person from the reference photo wearing a custom "
        f"{piece_type} they have designed.\n\n"
        f"The piece: {brief.strip()}\n"
        f"The fabric: {fabric_desc}.\n"
        f"{fit_line}\n\n"
        "Guidelines:\n"
        "- Preserve the person's face, skin tone, body proportions, and pose.\n"
        "- The fabric should read clearly as the material described — show "
        "its weight, drape, and surface character.\n"
        "- The piece should fit naturally on their body. Show construction "
        "details (seams, hems, closures) at a realistic level.\n"
        "- Studio photography: clean neutral background, soft even lighting.\n"
        "- Photorealistic, magazine-quality, full-length composition.\n"
        "- Do not invent accessories or additional garments the customer "
        "did not describe."
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


async def render_design(
    *,
    photo_bytes: bytes,
    photo_content_type: str,
    piece_type: PieceType,
    brief: str,
    fit_note: str | None,
    fabric_snapshot: dict[str, Any],
) -> tuple[bytes, str, dict[str, Any]]:
    """Single Nano Banana call. Returns ``(image_bytes, mime, provider_call)``."""
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_designer
    prompt = build_design_prompt(
        piece_type=piece_type,
        brief=brief,
        fit_note=fit_note,
        fabric_snapshot=fabric_snapshot,
    )
    image_part = types.Part.from_bytes(
        data=photo_bytes, mime_type=photo_content_type
    )
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        temperature=0.6,
    )

    started = time.perf_counter()
    started_at = datetime.now(UTC)
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[image_part, prompt],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "design_me",
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:300],
            "created_at": started_at,
            "extra": {"piece_type": piece_type},
        }
        log.warning("design_me.call_failed", error=str(exc)[:200])
        raise DesignerError(provider_call, "Design render failed") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    estimated_cost = estimate_image_cost_cents(1)

    extracted = _extract_image(response)
    if extracted is None:
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "design_me",
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": estimated_cost,
            "currency": "USD",
            "error_code": "NoImageInResponse",
            "error_message": "Model returned no image (safety block or empty output).",
            "created_at": started_at,
            "extra": {"piece_type": piece_type},
        }
        log.warning("design_me.no_image")
        raise DesignerError(provider_call, "Design render returned no image")

    image_bytes, mime_type = extracted
    provider_call = {
        "provider": "gemini",
        "model": model_name,
        "purpose": "design_me",
        "request_id": getattr(response, "response_id", None),
        "status": "ok",
        "latency_ms": latency_ms,
        "estimated_cost_amount": estimated_cost,
        "currency": "USD",
        "error_code": None,
        "error_message": None,
        "created_at": started_at,
        "extra": {
            "piece_type": piece_type,
            "image_bytes": len(image_bytes),
            "mime_type": mime_type,
        },
    }
    log.info(
        "design_me.ok", piece_type=piece_type, latency_ms=latency_ms,
        image_bytes=len(image_bytes),
    )
    return image_bytes, mime_type, provider_call


async def store_design_image(
    db: AsyncIOMotorDatabase[Any],
    *,
    storage_client: Any,
    image_bytes: bytes,
    mime_type: str,
    design_session_id: str,
    customer_id: str | None,
    anonymous_session_id: str | None,
) -> tuple[str, str]:
    """Persist the render in object storage + ``media_assets``.

    Returns ``(media_asset_id, signed_url)``.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    is_anonymous = customer_id is None

    media_asset_id = _media_id()
    extension = ".png" if "png" in mime_type.lower() else ".jpg"
    key_prefix = (
        "design/generated/anonymous" if is_anonymous else "design/generated/registered"
    )
    object_key = f"{key_prefix}/{media_asset_id}{extension}"

    written_key = await storage_client.put_object(
        object_key,
        image_bytes,
        content_type=mime_type,
        metadata={
            "media_asset_id": media_asset_id,
            "design_session_id": design_session_id,
            "ai_generated": "true",
        },
    )

    retention_policy = (
        "anonymous_24_hour" if is_anonymous else "registered_until_deleted"
    )
    expires_at: datetime | None = None
    if is_anonymous:
        expires_at = now + timedelta(hours=ANONYMOUS_GENERATED_RETENTION_HOURS)

    await db[C.media_assets].insert_one(
        {
            "media_asset_id": media_asset_id,
            "owner_type": "design_session",
            "owner_id": design_session_id,
            "purpose": "generated_design",
            "storage": {
                "bucket": settings.s3_bucket,
                "object_key": written_key,
                "content_type": mime_type,
                "byte_size": len(image_bytes),
            },
            "access": {"visibility": "private", "signed_url_required": True},
            "retention": {
                "policy": retention_policy,
                "expires_at": expires_at,
                "deleted_at": None,
            },
            "provenance": {
                "ai_generated": True,
                "provider": "gemini",
                "c2pa_embedded": False,
                "digital_source_type": "trainedAlgorithmicMedia",
            },
            "created_at": now,
            "updated_at": now,
        }
    )

    signed_url = await storage_client.presigned_get_url(
        written_key,
        expires_in=ANONYMOUS_GENERATED_RETENTION_HOURS * 3600 if is_anonymous else 3600,
    )
    return media_asset_id, signed_url
