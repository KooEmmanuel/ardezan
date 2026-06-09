"""Upload safety pipeline (REQ-057, REQ-058, ARCHITECTURE §8.5).

Five gates, in order:

1. File type / size / dimensions    — Pillow + size limit
2. Content moderation               — Gemini classifier
3. Minor detection                  — Gemini classifier
4. Multi-person check               — Gemini classifier
5. Quality (blur / dark / crop)     — Gemini classifier

Gates 2-5 share a single multimodal Gemini call (the M6.2 classifier) so
we don't pay 4× for one upload. The Pillow gate runs first so corrupt or
oversized files never reach the AI provider.

Fail-open vs fail-closed
------------------------
If the classifier call errors, the pipeline behaviour depends on the
``ai_safety_fail_open`` flag (defaults False = fail closed in production).
In development (no API key configured) fail-open is the practical default
so contributors can iterate without billing — set it explicitly in ``.env``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.try_on.agent_schemas import SafetyAssessment
from app.modules.try_on.safety_classifier import (
    SafetyClassifierError,
    classify as classify_safety,
)

log = get_logger(__name__)

# Register the HEIC/HEIF Pillow opener at module import so every later
# ``Image.open`` call can read iPhone screenshots / Live Photo stills.
# pillow-heif is a small native dep; failing to install means HEIC uploads
# get a clean ``file_format`` rejection instead of a crash.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    log.warning(
        "safety.heif_opener_missing",
        hint="`uv add pillow-heif` to support iPhone HEIC photos",
    )

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_DIMENSION = 300
MAX_DIMENSION = 8000


async def read_upload_capped(upload: Any, max_bytes: int = MAX_BYTES) -> bytes:
    """Read an ``UploadFile`` body without buffering an unbounded payload.

    ``await upload.read()`` pulls the whole multipart part into memory
    *before* any size gate runs — a trivially exploitable memory-DoS.
    Read in chunks and reject as soon as the cap is crossed instead.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                f"Photo is too large (max {max_bytes // (1024 * 1024)} MB).",
                http_status=413,
                details={"failed_gate": "file_size"},
            )
        chunks.append(chunk)
    return b"".join(chunks)
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


@dataclass
class UploadSafetyResult:
    passed: bool
    failed_gate: str | None = None
    reason: str | None = None
    file_metadata: dict[str, Any] = field(default_factory=dict)
    # The provider_call dict from the classifier, if it ran. Lets the
    # orchestrator append it to ai_jobs.provider_calls for cost/audit.
    provider_call: dict[str, Any] | None = None


def _file_gate(body: bytes, content_type: str) -> UploadSafetyResult:
    """Gate 1 — file type, byte size, and image dimensions."""
    if not body:
        return UploadSafetyResult(False, "file_empty", "The uploaded file is empty.")

    if len(body) > MAX_BYTES:
        return UploadSafetyResult(
            False,
            "file_size",
            f"Photo is too large (max {MAX_BYTES // (1024 * 1024)} MB).",
            {"size_bytes": len(body)},
        )

    if content_type.lower() not in ALLOWED_CONTENT_TYPES:
        return UploadSafetyResult(
            False,
            "file_type",
            f"Unsupported file type ({content_type}). Use JPEG, PNG, WebP, or HEIC.",
            {"content_type": content_type},
        )

    try:
        from PIL import Image
    except ImportError as exc:
        log.error("safety.pillow_missing", error=str(exc))
        return UploadSafetyResult(
            False, "internal", "Image validator unavailable.",
        )

    try:
        img = Image.open(BytesIO(body))
        img.verify()  # raises on corrupt file
        img = Image.open(BytesIO(body))  # re-open after verify
        width, height = img.size
        fmt = img.format
    except Exception as exc:  # noqa: BLE001
        return UploadSafetyResult(
            False,
            "file_format",
            "Could not read the image — file may be corrupt.",
            {"error": str(exc)[:200]},
        )

    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        return UploadSafetyResult(
            False,
            "dimensions_min",
            f"Photo is too small (min {MIN_DIMENSION}×{MIN_DIMENSION} px).",
            {"width": width, "height": height},
        )
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        return UploadSafetyResult(
            False,
            "dimensions_max",
            f"Photo is too large (max {MAX_DIMENSION}×{MAX_DIMENSION} px).",
            {"width": width, "height": height},
        )

    return UploadSafetyResult(
        True,
        file_metadata={
            "width": width,
            "height": height,
            "format": fmt or "",
            "size_bytes": len(body),
            "content_type": content_type,
        },
    )


def _check_assessment(
    assessment: SafetyAssessment, metadata: dict[str, Any], provider_call: dict[str, Any]
) -> UploadSafetyResult:
    """Run gates 2-5 against the classifier result.

    Order matters: moderation → minor → multi-person → quality so the most
    serious failure surfaces first.
    """
    if assessment.moderation_verdict == "fail":
        return UploadSafetyResult(
            False,
            "moderation",
            assessment.moderation_reason
            or "Photo contains content that can't be used for try-on.",
            metadata,
            provider_call,
        )

    # Uncertain on minors is treated as fail — REQ-058 asymmetric exposure.
    if assessment.minor_verdict in {"fail", "uncertain"}:
        return UploadSafetyResult(
            False,
            "minor_detected",
            assessment.minor_reason
            or "We can only generate try-on results for adults.",
            metadata,
            provider_call,
        )

    if assessment.person_count == 0:
        return UploadSafetyResult(
            False,
            "no_person",
            assessment.multi_person_reason
            or "We couldn't see a person in the photo — try one of you standing.",
            metadata,
            provider_call,
        )
    if assessment.person_count > 1:
        return UploadSafetyResult(
            False,
            "multi_person",
            assessment.multi_person_reason
            or "Use a solo photo so we can fit outfits to just you.",
            metadata,
            provider_call,
        )

    if assessment.quality_verdict != "good":
        return UploadSafetyResult(
            False,
            f"quality_{assessment.quality_verdict}",
            assessment.quality_reason
            or "Try a clearer, well-lit, full-body photo for the best results.",
            metadata,
            provider_call,
        )

    return UploadSafetyResult(True, file_metadata=metadata, provider_call=provider_call)


async def validate_upload(
    body: bytes, content_type: str
) -> UploadSafetyResult:
    """Run every gate in order. First failure short-circuits.

    When the classifier is disabled or fails open, the file gate still
    runs — so we never accept truly malformed uploads regardless of AI
    availability.
    """
    result = _file_gate(body, content_type)
    if not result.passed:
        log.info("safety.failed", gate=result.failed_gate, reason=result.reason)
        return result

    settings = get_settings()

    if not settings.ai_safety_classifier_enabled:
        log.warning(
            "safety.classifier_disabled",
            note="ai_safety_classifier_enabled=False — gates 2-5 bypassed",
        )
        return result

    if not settings.gemini_api_key:
        # No key — only path forward is fail-open with a loud warning, or
        # fail-closed with a clean error. Default is closed.
        if settings.ai_safety_fail_open:
            log.warning(
                "safety.fail_open_no_key",
                note="Gemini key absent; passing upload under ai_safety_fail_open",
            )
            return result
        log.error("safety.no_gemini_key", note="classifier required but key missing")
        return UploadSafetyResult(
            False,
            "classifier_unavailable",
            "Photo safety check is unavailable right now — please try again shortly.",
            result.file_metadata,
        )

    try:
        assessment, provider_call = await classify_safety(body, content_type)
    except SafetyClassifierError as exc:
        if settings.ai_safety_fail_open:
            log.warning(
                "safety.fail_open_classifier_error",
                error=str(exc),
                provider_call=exc.provider_call,
            )
            return UploadSafetyResult(
                True,
                file_metadata=result.file_metadata,
                provider_call=exc.provider_call,
            )
        log.warning("safety.fail_closed_classifier_error", error=str(exc))
        raise ApiError(
            ErrorCode.AI_UNAVAILABLE,
            "Photo safety check is unavailable right now — please try again shortly.",
            http_status=503,
            details={"failed_gate": "classifier"},
        ) from exc

    final = _check_assessment(assessment, result.file_metadata, provider_call)
    if not final.passed:
        log.info(
            "safety.failed",
            gate=final.failed_gate,
            reason=final.reason,
            classifier_latency_ms=provider_call.get("latency_ms"),
        )
    else:
        log.info("safety.passed", metadata=final.file_metadata)
    return final
