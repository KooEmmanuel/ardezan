"""Designer agent (M4.4) — Nano Banana (gemini-2.5-flash-image).

For each outfit in the result cards, render the customer wearing it. Each
generated image is:

1. Uploaded to object storage under ``tryon/generated/{anonymous|registered}/``
2. Recorded as a ``media_assets`` row with a 24-hour retention class (REQ-068)
3. Linked from a new ``generated_images`` row (DATA_MODEL §9.3)
4. Stitched back into the corresponding ``result_card.generated_image_id``
   so the customer-facing SSE event carries an image URL

Failures are isolated per outfit — one bad image doesn't abort the batch
(REQ-054). The job ends as ``completed`` only if every Designer call
succeeds; otherwise ``completed_partial``.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from google.genai import types
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db import C
from app.logging_setup import get_logger
from app.modules.try_on.cost import estimate_image_cost_cents
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _generated_image_id() -> str:
    return f"genimg_{secrets.token_hex(8)}"


# 24-hour retention for anonymous generated images (REQ-068).
ANONYMOUS_GENERATED_RETENTION_HOURS = 24


class DesignerError(RuntimeError):
    """Raised on Gemini failure; carries the provider_call dict for audit."""

    def __init__(self, provider_call: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.provider_call = provider_call


def _build_design_prompt(card: dict[str, Any]) -> str:
    items_text_parts: list[str] = []
    for item in card.get("items", []):
        title = item.get("product_title") or "garment"
        size = item.get("recommended_size") or ""
        color = item.get("color") or ""
        bits = [b for b in (color, title) if b]
        descriptor = " ".join(bits)
        if size:
            descriptor += f" (size {size})"
        items_text_parts.append(descriptor)

    items_text = "; ".join(items_text_parts) or "the styled outfit"
    outfit_name = card.get("outfit_name") or "a complete look"

    return (
        f"Render the person from the reference photo wearing this outfit "
        f'("{outfit_name}"): {items_text}.\n\n'
        "Guidelines:\n"
        "- Preserve the person's face, skin tone, body proportions, and pose.\n"
        "- The clothing should drape naturally on their body.\n"
        "- Studio photography: clean neutral background, soft even lighting.\n"
        "- Photorealistic, magazine-quality.\n"
        "- Full outfit visible from head to at least mid-calf.\n"
        "- Do not add accessories or items not listed."
    )


def _extract_image(response: Any) -> tuple[bytes, str] | None:
    """Pull the first image part from a Gemini response. ``None`` if there isn't one."""
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


async def generate_image_for_card(
    photo_bytes: bytes,
    photo_content_type: str,
    card: dict[str, Any],
) -> tuple[bytes, str, dict[str, Any]]:
    """Call Nano Banana once. Returns ``(image_bytes, mime_type, provider_call)``.

    Raises :class:`DesignerError` on failure. The error's ``provider_call``
    has ``status=failed`` so callers append it uniformly.
    """
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_designer
    prompt = _build_design_prompt(card)
    image_part = types.Part.from_bytes(data=photo_bytes, mime_type=photo_content_type)

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        temperature=0.55,
    )

    started = time.perf_counter()
    started_at = _now()
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
            "purpose": "designer",
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:300],
            "created_at": started_at,
            "extra": {"card_id": card.get("card_id")},
        }
        log.warning(
            "designer.call_failed",
            card_id=card.get("card_id"),
            error=str(exc)[:200],
        )
        raise DesignerError(provider_call, "Designer call failed") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    estimated_cost = estimate_image_cost_cents(1)

    extracted = _extract_image(response)
    if extracted is None:
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "designer",
            "status": "failed",
            "latency_ms": latency_ms,
            # Charge for the call attempt even though nothing usable came back.
            "estimated_cost_amount": estimated_cost,
            "currency": "USD",
            "error_code": "NoImageInResponse",
            "error_message": "Model returned no image (safety block or empty output).",
            "created_at": started_at,
            "extra": {"card_id": card.get("card_id")},
        }
        log.warning("designer.no_image", card_id=card.get("card_id"))
        raise DesignerError(provider_call, "Designer returned no image")

    image_bytes, mime_type = extracted
    provider_call = {
        "provider": "gemini",
        "model": model_name,
        "purpose": "designer",
        "request_id": getattr(response, "response_id", None),
        "status": "ok",
        "latency_ms": latency_ms,
        "estimated_cost_amount": estimated_cost,
        "currency": "USD",
        "error_code": None,
        "error_message": None,
        "created_at": started_at,
        "extra": {
            "card_id": card.get("card_id"),
            "outfit_name": card.get("outfit_name"),
            "image_bytes": len(image_bytes),
            "mime_type": mime_type,
        },
    }
    log.info(
        "designer.ok",
        card_id=card.get("card_id"),
        latency_ms=latency_ms,
        image_bytes=len(image_bytes),
        mime_type=mime_type,
    )
    return image_bytes, mime_type, provider_call


async def store_generated_image(
    db: AsyncIOMotorDatabase[Any],
    *,
    storage_client: Any,
    image_bytes: bytes,
    mime_type: str,
    job_id: str,
    try_on_session_id: str,
    card: dict[str, Any],
    customer_id: str | None,
    anonymous_session_id: str | None,
) -> tuple[str, str]:
    """Persist a generated image and link it from the card.

    Returns ``(generated_image_id, signed_url)``. The signed URL TTL matches
    the retention class (24h for anonymous).
    """
    settings = get_settings()
    now = _now()
    is_anonymous = customer_id is None

    media_asset_id = _media_id()
    extension = ".png" if "png" in mime_type.lower() else ".jpg"
    key_prefix = (
        "tryon/generated/anonymous" if is_anonymous else "tryon/generated/registered"
    )
    object_key = f"{key_prefix}/{media_asset_id}{extension}"

    written_key = await storage_client.put_object(
        object_key,
        image_bytes,
        content_type=mime_type,
        metadata={
            "media_asset_id": media_asset_id,
            "job_id": job_id,
            "card_id": card.get("card_id") or "",
            "ai_generated": "true",
        },
    )

    retention_policy = (
        "anonymous_24_hour" if is_anonymous else "registered_until_deleted"
    )
    expires_at: datetime | None = None
    if is_anonymous:
        expires_at = now + timedelta(hours=ANONYMOUS_GENERATED_RETENTION_HOURS)

    # media_assets row
    await db[C.media_assets].insert_one(
        {
            "media_asset_id": media_asset_id,
            "owner_type": "try_on_session",
            "owner_id": try_on_session_id,
            "purpose": "generated_try_on",
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

    # generated_images row (DATA_MODEL §9.3)
    generated_image_id = _generated_image_id()
    await db[C.generated_images].insert_one(
        {
            "generated_image_id": generated_image_id,
            "try_on_session_id": try_on_session_id,
            "job_id": job_id,
            "media_asset_id": media_asset_id,
            "customer_id": customer_id,
            "anonymous_session_id": anonymous_session_id,
            "provider": "gemini",
            "model": settings.gemini_model_designer,
            "outfit_card_id": card.get("card_id"),
            "product_ids": [it.get("product_id") for it in card.get("items", [])],
            "variant_ids": [it.get("variant_id") for it in card.get("items", [])],
            "disclosure": {
                "ai_preview_label_shown": True,
                "alt_text_marks_ai_generated": True,
                "provenance_metadata_embedded": False,
            },
            "retention": {
                "policy": retention_policy,
                "expires_at": expires_at,
                "deleted_at": None,
            },
            "created_at": now,
            "updated_at": now,
        }
    )

    # Signed URL — for anonymous, lifetime = retention window (24h).
    signed_url = await storage_client.presigned_get_url(
        written_key,
        expires_in=ANONYMOUS_GENERATED_RETENTION_HOURS * 3600 if is_anonymous else 3600,
    )

    # Patch the card on try_on_sessions using the positional operator.
    await db[C.try_on_sessions].update_one(
        {
            "try_on_session_id": try_on_session_id,
            "result_cards.card_id": card.get("card_id"),
        },
        {
            "$set": {
                "result_cards.$.generated_image_id": generated_image_id,
                "result_cards.$.image_url": signed_url,
                "updated_at": now,
            }
        },
    )

    return generated_image_id, signed_url
