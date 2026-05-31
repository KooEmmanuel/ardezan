"""Analyzer agent (M4.2).

Takes a customer photo + optional inputs and returns a typed ``BodyProfile``
via a Gemini multimodal call with structured output.

This is the *first* of the three orchestrator stages. Output feeds the
Recommender (M4.3) which then drives the Designer (M4.4).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.logging_setup import get_logger
from app.modules.try_on.agent_schemas import BodyProfile
from app.modules.try_on.cost import estimate_text_cost_cents
from app.modules.try_on.gemini_client import get_gemini_client
from app.modules.try_on.schemas import TryOnInputs

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


_PROMPT_BASE = """\
You are a professional fashion stylist's assistant. A customer has uploaded a
full-body photo so we can recommend outfits that fit them. Analyse the photo
and return a body profile in JSON matching the requested schema.

Guidelines:
- Use neutral, professional language. Never judgmental.
- Measurements should be in centimetres. If you can't estimate a measurement
  with reasonable confidence, return null for it.
- ``confidence`` (0.0-1.0) reflects how clear, well-lit, and well-framed the
  photo is for styling purposes — not whether the *person* looks good.
- ``current_style_notes`` is ONE short sentence about the outfit visible in
  the photo (e.g., "casual streetwear in neutral tones").
- For ``body_shape``, choose the closest match from the allowed values.
- For ``skin_undertone``, observe the visible skin tone. If unclear, return null.
"""


def _build_prompt(inputs: TryOnInputs) -> str:
    lines = [_PROMPT_BASE.strip()]
    ctx: list[str] = []
    if inputs.height:
        ctx.append(f"- Stated height: {inputs.height}")
    if inputs.fit_preference:
        ctx.append(f"- Fit preference: {inputs.fit_preference}")
    if inputs.occasion:
        ctx.append(f"- Occasion: {inputs.occasion}")
    if inputs.prompt:
        ctx.append(f"- Additional notes: {inputs.prompt}")
    if ctx:
        lines.append("\nCustomer-provided context:")
        lines.extend(ctx)
        lines.append(
            "\nUse this context when estimating measurements and noting style, "
            "but do not invent measurements you can't see."
        )
    return "\n".join(lines)


class AnalyzerError(RuntimeError):
    """Raised when the analyzer call fails — carries the provider_call dict
    so the orchestrator can attach it to ai_jobs.provider_calls."""

    def __init__(self, provider_call: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.provider_call = provider_call


async def analyze(
    photo_bytes: bytes,
    content_type: str,
    inputs: TryOnInputs,
) -> tuple[BodyProfile, dict[str, Any]]:
    """Run the Analyzer. Returns ``(body_profile, provider_call_metadata)``.

    Raises :class:`AnalyzerError` on failure. The error carries the same
    provider-call dict so callers can record both success and failure to
    ``ai_jobs.provider_calls``.
    """
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_analyzer

    prompt = _build_prompt(inputs)
    image_part = types.Part.from_bytes(data=photo_bytes, mime_type=content_type)
    # Gemini 2.5 Flash budgets internal "thinking" against ``max_output_tokens``
    # by default — at temperature=0.2 with structured output that easily eats
    # most of the budget before any JSON is written, producing the truncated
    # stream we saw in M4. Disable thinking explicitly (we want raw analysis,
    # not deliberation) and raise the cap to a comfortable margin.
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BodyProfile,
        temperature=0.2,
        max_output_tokens=4096,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    started = time.perf_counter()
    started_at = _now()
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[prompt, image_part],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "analyzer",
            "request_id": None,
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:300],
            "created_at": started_at,
        }
        log.warning(
            "analyzer.call_failed",
            model=model_name,
            error_code=provider_call["error_code"],
            error_message=provider_call["error_message"],
            latency_ms=latency_ms,
        )
        raise AnalyzerError(provider_call, "Analyzer call failed") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = getattr(response, "usage_metadata", None)
    estimated_cost = estimate_text_cost_cents(usage)

    # Pull the parsed model if the SDK populated it, fall back to JSON text.
    parsed: BodyProfile | None = getattr(response, "parsed", None)
    if parsed is None:
        text = getattr(response, "text", None) or ""
        try:
            parsed = BodyProfile.model_validate_json(text)
        except ValidationError as exc:
            provider_call = {
                "provider": "gemini",
                "model": model_name,
                "purpose": "analyzer",
                "status": "failed",
                "latency_ms": latency_ms,
                "estimated_cost_amount": estimated_cost,
                "currency": "USD",
                "error_code": "InvalidJsonOutput",
                "error_message": str(exc)[:300],
                "created_at": started_at,
            }
            log.warning("analyzer.invalid_output", text_excerpt=text[:200])
            raise AnalyzerError(provider_call, "Analyzer returned invalid JSON") from exc

    provider_call = {
        "provider": "gemini",
        "model": model_name,
        "purpose": "analyzer",
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
        "analyzer.ok",
        body_shape=parsed.body_shape,
        confidence=parsed.confidence,
        latency_ms=latency_ms,
        estimated_cost_cents=estimated_cost,
        input_tokens=provider_call.get("input_tokens", 0),
        output_tokens=provider_call.get("output_tokens", 0),
    )
    return parsed, provider_call
