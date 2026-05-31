"""Gemini-backed upload safety classifier (M6.2).

One multimodal call that returns a structured :class:`SafetyAssessment`
covering moderation, minor detection, multi-person, and quality. Rolling
all four gates into a single call halves cost vs. running four separate
classifiers and keeps latency under the upload budget (REQ-073).

Returns the assessment plus a ``provider_call`` dict the orchestrator can
attach to ``ai_jobs.provider_calls`` — same shape as the analyzer's, so
the cost/latency story stays consistent.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.logging_setup import get_logger
from app.modules.try_on.agent_schemas import SafetyAssessment
from app.modules.try_on.cost import estimate_text_cost_cents
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)


_SAFETY_PROMPT = """\
You are a content-safety classifier for an online clothing store's AI try-on
feature. The customer has uploaded a photo. Assess it on four dimensions and
return JSON matching the requested schema.

1. moderation_verdict
   - "fail" if the photo contains: explicit nudity, sexual content, graphic
     violence, weapons aimed at people, hateful symbols, or other content
     that would be inappropriate to render outfits onto.
   - "pass" if the photo is a normal clothed or casually clothed person in
     an everyday setting.
   - "uncertain" only for genuinely ambiguous cases. Briefly explain in
     ``moderation_reason``.

2. minor_verdict
   - "fail" if the primary subject appears to be under 18.
   - "pass" if the primary subject is clearly an adult.
   - "uncertain" if you cannot tell with reasonable confidence. The
     orchestrator treats uncertain as a soft block.
   - ``minor_reason`` should be one short sentence — never describe the
     person beyond age cues.

3. person_count
   - Integer count of distinct people clearly visible in the foreground.
   - 0 if no person is visible.
   - Photos in mirrors, photos of photos, or group photos all count.
   - Set ``multi_person_reason`` if count is not exactly 1.

4. quality_verdict
   - "good"            — sharp, well-lit, full or near-full body visible.
   - "blurry"          — motion blur or out-of-focus.
   - "too_dark"        — lighting too low to see the outfit clearly.
   - "poorly_framed"   — head, feet, or significant body parts cut off.
   - "obstructed"      — body largely hidden by props, furniture, or pose.
   - ``quality_reason`` should be a short sentence the customer can act on,
     e.g. "Try a brighter room" or "Stand back so your whole body is visible."

Be conservative. When in doubt about safety, err toward blocking; when in
doubt about quality, err toward asking the customer to retake.
"""


class SafetyClassifierError(RuntimeError):
    """Raised when the safety classifier call itself fails (network, quota,
    invalid output). The caller decides whether to fail open or closed based
    on ``ai_safety_fail_open``."""

    def __init__(self, provider_call: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.provider_call = provider_call


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def classify(
    photo_bytes: bytes, content_type: str
) -> tuple[SafetyAssessment, dict[str, Any]]:
    """Run the classifier. Returns ``(assessment, provider_call)``.

    Raises :class:`SafetyClassifierError` on call/parse failure.
    """
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_safety

    image_part = types.Part.from_bytes(data=photo_bytes, mime_type=content_type)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SafetyAssessment,
        # Deterministic — we want the same photo to get the same verdict.
        temperature=0.0,
        max_output_tokens=2048,
        # Disable internal thinking budget so it doesn't crowd out the JSON
        # output — same fix as the analyzer (see comment there).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    started = time.perf_counter()
    started_at = _now()
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[_SAFETY_PROMPT, image_part],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "safety_classifier",
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:300],
            "created_at": started_at,
        }
        log.warning(
            "safety_classifier.call_failed",
            model=model_name,
            error_code=provider_call["error_code"],
            latency_ms=latency_ms,
        )
        raise SafetyClassifierError(provider_call, "Safety classifier call failed") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = getattr(response, "usage_metadata", None)
    estimated_cost = estimate_text_cost_cents(usage)

    parsed: SafetyAssessment | None = getattr(response, "parsed", None)
    if parsed is None:
        text = getattr(response, "text", None) or ""
        try:
            parsed = SafetyAssessment.model_validate_json(text)
        except ValidationError as exc:
            provider_call = {
                "provider": "gemini",
                "model": model_name,
                "purpose": "safety_classifier",
                "status": "failed",
                "latency_ms": latency_ms,
                "estimated_cost_amount": estimated_cost,
                "currency": "USD",
                "error_code": "InvalidJsonOutput",
                "error_message": str(exc)[:300],
                "created_at": started_at,
            }
            log.warning(
                "safety_classifier.invalid_output", text_excerpt=text[:200]
            )
            raise SafetyClassifierError(
                provider_call, "Safety classifier returned invalid JSON"
            ) from exc

    provider_call = {
        "provider": "gemini",
        "model": model_name,
        "purpose": "safety_classifier",
        "request_id": getattr(response, "response_id", None),
        "status": "ok",
        "latency_ms": latency_ms,
        "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "estimated_cost_amount": estimated_cost,
        "currency": "USD",
        "error_code": None,
        "error_message": None,
        "created_at": started_at,
    }

    log.info(
        "safety_classifier.ok",
        moderation=parsed.moderation_verdict,
        minor=parsed.minor_verdict,
        person_count=parsed.person_count,
        quality=parsed.quality_verdict,
        latency_ms=latency_ms,
        estimated_cost_cents=estimated_cost,
    )
    return parsed, provider_call


__all__ = ["classify", "SafetyClassifierError"]
