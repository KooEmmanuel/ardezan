"""Admin commerce settings — pricing formulas + shipping rates.

One ``settings`` document, key ``commerce``, holds:

- ``yardage_by_piece`` — fabric yardage per piece type (float)
- ``base_tailoring_by_piece`` — flat tailoring fee per piece type
  (integer cents, before complexity multiplier)
- ``complexity_multiplier`` — simple/standard/intricate factor (float)
- ``shipping`` — per-method flat rates (integer cents), with optional
  international destinations

The Design Me cost estimator + checkout shipping calculator both read
from this doc, with the previous hardcoded values as the default if a
field is missing. The admin can override anything live without a
redeploy.

Mounted at ``/api/v1/admin/commerce``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.db import C
from app.deps import DbDep
from app.modules.admin.deps import AdminDep

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────
PIECE_TYPES = [
    "shirt", "blouse", "trouser", "skirt", "dress",
    "jacket", "blazer", "coat", "overshirt", "tee",
    "caftan", "agbada", "dashiki", "kaba",
]

DEFAULT_YARDAGE = {
    "tee": 1.5, "shirt": 2.5, "blouse": 2.5, "trouser": 1.8, "skirt": 1.5,
    "dress": 4.0, "jacket": 3.0, "blazer": 3.0, "coat": 4.0, "overshirt": 2.8,
    "caftan": 3.5, "agbada": 6.0, "dashiki": 2.2, "kaba": 4.5,
}
DEFAULT_TAILORING_CENTS = {
    "tee": 4_500, "shirt": 9_500, "blouse": 9_500, "trouser": 12_000,
    "skirt": 8_500, "dress": 18_000, "jacket": 22_000, "blazer": 22_000,
    "coat": 28_000, "overshirt": 14_000, "caftan": 15_000, "agbada": 38_000,
    "dashiki": 9_000, "kaba": 22_000,
}
DEFAULT_COMPLEXITY = {"simple": 0.85, "standard": 1.0, "intricate": 1.35}
DEFAULT_SHIPPING = {
    "standard_cents": 800,    # $8 domestic standard
    "express_cents": 1_800,   # $18 domestic express
    "international_cents": 5_000,  # $50 — DHL Express to US from Ghana etc.
}


class CommerceConfig(BaseModel):
    """The full commerce config — pricing tables + shipping rates."""

    yardage_by_piece: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_YARDAGE))
    base_tailoring_by_piece: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_TAILORING_CENTS))
    complexity_multiplier: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_COMPLEXITY))
    shipping: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_SHIPPING))


class CommerceConfigUpdate(BaseModel):
    yardage_by_piece: dict[str, float] | None = None
    base_tailoring_by_piece: dict[str, int] | None = None
    complexity_multiplier: dict[str, float] | None = None
    shipping: dict[str, int] | None = None


# ── Repository helpers ─────────────────────────────────────────────
async def _load_doc(db: DbDep) -> dict[str, Any]:
    doc = await db[C.settings].find_one({"_id": "commerce"})
    return doc or {}


async def _save_doc(db: DbDep, fields: dict[str, Any]) -> None:
    fields["updated_at"] = datetime.now(UTC)
    await db[C.settings].update_one(
        {"_id": "commerce"},
        {"$set": fields},
        upsert=True,
    )


async def get_commerce_config(db: DbDep) -> CommerceConfig:
    """Load the commerce config, filling missing fields with defaults.

    The Design Me estimator + checkout shipping calculator import this
    so they never see ``None`` for any field.
    """
    raw = await _load_doc(db)
    return CommerceConfig(
        yardage_by_piece={**DEFAULT_YARDAGE, **raw.get("yardage_by_piece", {})},
        base_tailoring_by_piece={**DEFAULT_TAILORING_CENTS, **raw.get("base_tailoring_by_piece", {})},
        complexity_multiplier={**DEFAULT_COMPLEXITY, **raw.get("complexity_multiplier", {})},
        shipping={**DEFAULT_SHIPPING, **raw.get("shipping", {})},
    )


# ── Routes ──────────────────────────────────────────────────────────
@router.get(
    "/commerce",
    response_model=CommerceConfig,
    summary="Read the pricing + shipping configuration (admin)",
)
async def read_commerce_config(
    db: DbDep, admin: AdminDep
) -> CommerceConfig:
    return await get_commerce_config(db)


@router.patch(
    "/commerce",
    response_model=CommerceConfig,
    summary="Update pricing + shipping configuration",
)
async def update_commerce_config(
    body: CommerceConfigUpdate,
    db: DbDep,
    admin: AdminDep,
) -> CommerceConfig:
    fields: dict[str, Any] = {}
    for name, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            fields[name] = value
    if fields:
        await _save_doc(db, fields)
    return await get_commerce_config(db)
