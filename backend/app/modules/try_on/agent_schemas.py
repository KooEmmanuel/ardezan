"""Structured-output schemas for the three AI agents.

These models are passed to the ``google-genai`` SDK as ``response_schema``
so the model returns JSON guaranteed to validate against them. Keep them
flat and avoid unsupported types (no custom validators, no aliases, no
deeply-nested unions) — the SDK converts these to OpenAPI for the model.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Analyzer output (M4.2) ──────────────────────────────────────────
BodyShape = Literal[
    "rectangle",
    "hourglass",
    "pear",
    "apple",
    "inverted_triangle",
]
SkinUndertone = Literal["warm", "cool", "neutral"]


class BodyProfile(BaseModel):
    """What the Analyzer produces from a photo + optional context."""

    body_shape: BodyShape | None = None
    estimated_height_cm: int | None = None
    estimated_chest_cm: int | None = None
    estimated_waist_cm: int | None = None
    estimated_hip_cm: int | None = None
    estimated_inseam_cm: int | None = None
    skin_undertone: SkinUndertone | None = None
    current_style_notes: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# ── Recommender output (M4.3) ───────────────────────────────────────
class OutfitItem(BaseModel):
    """One item inside a proposed outfit. The Recommender picks a specific
    variant (size + colour) so the Designer + cart can use it directly."""

    product_id: str
    variant_id: str
    rationale: str = ""


class RecommendedOutfit(BaseModel):
    outfit_name: str
    items: list[OutfitItem] = Field(default_factory=list)
    rationale: str = ""


class OutfitRecommendations(BaseModel):
    outfits: list[RecommendedOutfit] = Field(default_factory=list)


# ── Title-based recommender output ──────────────────────────────────
# Gemini struggles to reliably echo back opaque internal IDs (it strips the
# ``prod_`` prefix or invents new hashes). Asking it to identify items by
# the natural-language title + a colour + a size is much more LLM-friendly
# — and then the server resolves these descriptive picks to canonical
# ``product_id`` / ``variant_id`` via the catalog context.
class OutfitItemNamed(BaseModel):
    """One item identified by its catalogue *title* + colour + size."""

    product_title: str = Field(
        ..., description="Exact product title from the catalogue."
    )
    color: str = Field(
        "", description="Preferred colour (matches one of the variants)."
    )
    size: str = Field(
        "", description="Preferred size (matches one of the variants)."
    )
    rationale: str = Field("", description="Short why-this-piece sentence.")


class RecommendedOutfitNamed(BaseModel):
    outfit_name: str
    items: list[OutfitItemNamed] = Field(default_factory=list)
    rationale: str = ""


class OutfitRecommendationsNamed(BaseModel):
    outfits: list[RecommendedOutfitNamed] = Field(default_factory=list)


# ── Safety classifier output (M6.2) ─────────────────────────────────
# Single multimodal Gemini call that covers all four content gates
# (REQ-057, REQ-058). Each gate carries its own verdict so the caller
# can attribute a failure to the correct gate when surfacing the error.
SafetyVerdict = Literal["pass", "fail", "uncertain"]
QualityVerdict = Literal["good", "blurry", "too_dark", "poorly_framed", "obstructed"]


class SafetyAssessment(BaseModel):
    """All four AI safety gates rolled into one structured response."""

    # Gate 2 — moderation. ``fail`` covers nudity, violence, hateful imagery.
    moderation_verdict: SafetyVerdict = "pass"
    moderation_reason: str = ""

    # Gate 3 — minor detection. ``fail`` if the subject appears under 18.
    # ``uncertain`` defers — we treat uncertain as fail in production
    # because legal exposure on misclassified minors is asymmetric.
    minor_verdict: SafetyVerdict = "pass"
    minor_reason: str = ""

    # Gate 4 — multi-person. ``person_count`` is the visible subject count;
    # 0 (no person) or >1 (multiple people) both fail this gate.
    person_count: int = 1
    multi_person_reason: str = ""

    # Gate 5 — quality. ``good`` passes; any other verdict fails with the
    # specific reason the customer can act on.
    quality_verdict: QualityVerdict = "good"
    quality_reason: str = ""
