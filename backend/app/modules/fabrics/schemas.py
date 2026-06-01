"""Fabric library schemas.

A fabric is a *material*, not a SKU — there are no variants. The customer
picks one and combines it with their own design brief; the AI generates
them wearing the imagined garment. Pricing on a custom design is
``fabric.cost_per_yard × yardage_for_piece_type + tailoring_fee`` —
see ``estimate_cost`` in :mod:`app.modules.fabrics.pricing`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# Piece types we support out of the gate. The pricing helper maps each
# of these to an estimated yardage; the AI prompt uses the same names
# so customers see consistent terminology.
PieceType = Literal[
    "shirt",
    "blouse",
    "trouser",
    "skirt",
    "dress",
    "jacket",
    "blazer",
    "coat",
    "overshirt",
    "tee",
    # African pieces — brand-relevant additions. Yardage + tailoring
    # fee tables in ``pricing.py`` carry sensible defaults for these.
    "caftan",
    "agbada",
    "dashiki",
    "kaba",
]


class FabricSwatch(BaseModel):
    """Visual representation of the fabric for the picker.

    For the demo we render as a CSS gradient (no image upload required
    before launch). When real swatch photos arrive, ``image_url`` takes
    precedence over ``gradient``.
    """

    gradient: str | None = None  # e.g. "linear-gradient(135deg, #d4c5a0, #b8a679)"
    image_url: str | None = None


class FabricPublic(BaseModel):
    """Fabric as returned by ``GET /fabrics``."""

    fabric_id: str
    name: str
    description: str
    color_family: str  # "warm-neutrals", "cool-neutrals", "rich-tones", "denim"
    cost_per_yard_amount: int = Field(..., ge=0)  # USD cents per yard
    currency: str = "USD"
    suitable_for: list[PieceType] = Field(default_factory=list)
    swatch: FabricSwatch = Field(default_factory=FabricSwatch)
    weight: Literal["light", "medium", "heavy"] = "medium"
    finish: str | None = None  # "matte", "lustrous", "brushed", "structured"


class FabricListResponse(BaseModel):
    items: list[FabricPublic]


class Fabric(BaseModel):
    """Stored shape — what the seeder writes to Mongo."""

    fabric_id: str
    name: str
    description: str
    color_family: str
    cost_per_yard_amount: int
    currency: str = "USD"
    suitable_for: list[PieceType]
    swatch: FabricSwatch
    weight: Literal["light", "medium", "heavy"]
    finish: str | None = None
    active: bool = True
    created_at: datetime
    updated_at: datetime
