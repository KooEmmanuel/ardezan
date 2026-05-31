"""AI provider cost estimation helpers.

Returns costs in **integer cents** (matching the rest of the money model in
DATA_MODEL §2.4). Rates are conservative — Gemini occasionally bills slightly
different from list, and we'd rather over-account by a fraction of a cent.
"""
from __future__ import annotations

import math
from typing import Any

# gemini-2.5-flash text pricing (USD per 1M tokens). Update when Gemini does.
GEMINI_FLASH_INPUT_USD_PER_M = 0.075
GEMINI_FLASH_OUTPUT_USD_PER_M = 0.30

# gemini-2.5-flash-image (Nano Banana) — per image, list price.
GEMINI_FLASH_IMAGE_USD_PER_IMAGE = 0.039


def estimate_text_cost_cents(usage_metadata: Any) -> int:
    """Compute cents from a google-genai ``usage_metadata`` (or ``None``).

    Rounds up so partial cents accumulate as conservatively as possible.
    """
    if usage_metadata is None:
        return 0
    input_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0
    dollars = (
        (input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_USD_PER_M
        + (output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_USD_PER_M
    )
    return max(0, math.ceil(dollars * 100))


def estimate_image_cost_cents(images_generated: int) -> int:
    """Designer cost for ``images_generated`` images."""
    if images_generated <= 0:
        return 0
    dollars = images_generated * GEMINI_FLASH_IMAGE_USD_PER_IMAGE
    return max(0, math.ceil(dollars * 100))
