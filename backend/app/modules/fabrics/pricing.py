"""Cost estimation for Design Me custom pieces.

We expose ``estimate_cost(fabric, piece_type, complexity)`` returning a
structured breakdown. The numbers are intentionally simple — this is a
first-pass estimate before the tailor confirms. Real divergences are
handled via the existing refund / upcharge flows post-checkout.

Math
----
``material_amount = fabric.cost_per_yard × yardage[piece_type]``
``tailoring_amount = base_tailoring[piece_type] × complexity_multiplier``
``total_amount   = material_amount + tailoring_amount``

The constants below are sized for a US market (USD cents) and bias
*upward* by about 15-20% — a customer who pays the estimate, gets a
cheaper real quote, and receives a partial refund is happy. The other
direction is not.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.fabrics.schemas import PieceType


Complexity = Literal["simple", "standard", "intricate"]


# ── Yardage table ──────────────────────────────────────────────────
# Conservative estimates — we'd rather over-quote and refund the
# difference than under-quote and have to call for more money.
_YARDAGE_BY_PIECE: dict[PieceType, float] = {
    "tee": 1.5,
    "shirt": 2.5,
    "blouse": 2.5,
    "trouser": 1.8,
    "skirt": 1.5,
    "dress": 4.0,
    "jacket": 3.0,
    "blazer": 3.0,
    "coat": 4.0,
    "overshirt": 2.8,
    # African pieces tend to use more fabric — full silhouettes, layered
    # construction, traditional cuts. Numbers based on common patterns.
    "caftan": 3.5,
    "agbada": 6.0,    # three-piece ensemble (boubou + dansiki + sokoto)
    "dashiki": 2.2,
    "kaba": 4.5,      # full kaba & slit ensemble
}

# Flat tailoring fee per piece type, in cents. Reflects what a US-based
# bespoke tailor charges before complexity surcharges.
_BASE_TAILORING_BY_PIECE: dict[PieceType, int] = {
    "tee": 4_500,        # $45
    "shirt": 9_500,      # $95
    "blouse": 9_500,
    "trouser": 12_000,   # $120
    "skirt": 8_500,
    "dress": 18_000,     # $180
    "jacket": 22_000,    # $220
    "blazer": 22_000,
    "coat": 28_000,      # $280
    "overshirt": 14_000, # $140
    # African pieces — handmade construction, often hand-finished. Prices
    # reflect typical Bonwire-tailor rates × a modest US markup.
    "caftan": 15_000,    # $150
    "agbada": 38_000,    # $380 (three-piece + embroidery margin)
    "dashiki": 9_000,    # $90
    "kaba": 22_000,      # $220 (kaba + slit set)
}

_COMPLEXITY_MULTIPLIER: dict[Complexity, float] = {
    "simple": 0.85,      # straight cut, no lining, minimal details
    "standard": 1.0,
    "intricate": 1.35,   # pleating, lining, hand-finishing, embellishments
}


class CostBreakdown(BaseModel):
    """What the customer sees on the estimate card and pays at checkout."""

    fabric_id: str
    piece_type: PieceType
    complexity: Complexity
    yardage: float = Field(..., ge=0)
    material_amount: int = Field(..., ge=0)
    tailoring_amount: int = Field(..., ge=0)
    total_amount: int = Field(..., ge=0)
    currency: str = "USD"
    estimate_note: str = (
        "Estimate covers fabric + tailoring. Your designer will confirm "
        "the exact figure after measurements. Any difference is refunded "
        "or charged to your original payment method."
    )


def estimate_cost(
    *,
    fabric_id: str,
    cost_per_yard_amount: int,
    currency: str,
    piece_type: PieceType,
    complexity: Complexity = "standard",
    # Optional admin-managed overrides. When provided, supersede the
    # built-in tables. Pass the entire mapping in — partial overrides
    # are resolved in ``commerce_router.get_commerce_config`` before
    # the value gets here.
    yardage_overrides: dict[str, float] | None = None,
    tailoring_overrides: dict[str, int] | None = None,
    complexity_overrides: dict[str, float] | None = None,
) -> CostBreakdown:
    """Compute the estimate displayed to the customer.

    Raises ``KeyError`` if ``piece_type`` is unknown — the router catches
    and returns a 400.
    """
    yardage_table = yardage_overrides or _YARDAGE_BY_PIECE
    tailoring_table = tailoring_overrides or _BASE_TAILORING_BY_PIECE
    complexity_table = complexity_overrides or _COMPLEXITY_MULTIPLIER
    yardage = yardage_table[piece_type]
    base_tailoring = tailoring_table[piece_type]
    mult = complexity_table[complexity]

    material = int(round(cost_per_yard_amount * yardage))
    tailoring = int(round(base_tailoring * mult))
    total = material + tailoring

    return CostBreakdown(
        fabric_id=fabric_id,
        piece_type=piece_type,
        complexity=complexity,
        yardage=round(yardage, 2),
        material_amount=material,
        tailoring_amount=tailoring,
        total_amount=total,
        currency=currency,
    )
