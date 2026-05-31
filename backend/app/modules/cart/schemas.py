"""Cart module schemas.

Two layers:
- ``CartLineInput`` / ``RevalidateRequest`` / ``FullLookAddRequest`` — what the
  frontend sends.
- ``CartLineState`` / ``RevalidateResponse`` / ``FullLookAddResponse`` — what
  the backend returns. Each line carries a ``status`` so the UI can render
  warnings (stale price, out-of-stock, removed product).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.catalog.schemas import VariantPricing

LineSource = Literal["catalog", "try_on_full_look", "try_on_single_item", "design_me"]

# A line is either a real catalog variant or a custom design from the
# Design Me flow. The two have different validation, pricing, and order
# semantics — most of the cart/checkout code branches on this.
LineKind = Literal["catalog", "custom_design"]

LineStatus = Literal[
    "ok",              # nothing changed; line is fine
    "price_changed",   # current price differs from what client had
    "low_stock",       # available_quantity < requested but > 0
    "out_of_stock",    # available_quantity == 0
    "removed",         # variant or design session no longer exists
]


# ── Input (from frontend) ───────────────────────────────────────────
class CartLineInput(BaseModel):
    line_id: str = Field(..., min_length=1, max_length=64)
    kind: LineKind = "catalog"
    # Required for kind=catalog; ignored for kind=custom_design.
    product_id: str | None = None
    variant_id: str | None = None
    # Required for kind=custom_design; absent on catalog lines.
    design_session_id: str | None = None
    quantity: int = Field(..., ge=1, le=99)
    source: LineSource = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None
    # Optional: the price the client thinks this line costs. If present and
    # different from the current price, we set status=price_changed.
    expected_unit_price_amount: int | None = None


class RevalidateRequest(BaseModel):
    lines: list[CartLineInput] = Field(..., max_length=99)


class FullLookItem(BaseModel):
    """One item inside an "Add full look to cart" request."""

    product_id: str
    variant_id: str
    quantity: int = Field(1, ge=1, le=10)


class FullLookAddRequest(BaseModel):
    try_on_session_id: str = Field(..., min_length=1, max_length=64)
    card_id: str = Field(..., min_length=1, max_length=64)
    items: list[FullLookItem] = Field(..., min_length=1, max_length=10)


# ── Output (back to frontend) ───────────────────────────────────────
class CartLineState(BaseModel):
    line_id: str
    kind: LineKind = "catalog"
    product_id: str | None = None
    variant_id: str | None = None
    design_session_id: str | None = None

    # Display fields (may be None if status=removed)
    product_title: str | None = None
    variant_title: str | None = None
    size: str | None = None
    color: str | None = None
    color_hex: str | None = None
    primary_media_asset_id: str | None = None
    # Pre-signed catalog image URL so the cart page can drop it straight
    # into <img src=> without a second hop. For custom_design lines this
    # carries the signed Gemini-rendered URL.
    primary_image_url: str | None = None

    quantity: int
    status: LineStatus

    # Provenance — echoed back from the input so the cart can group lines
    # by the outfit they came from (and the customer can pick which
    # outfits to check out independently).
    source: LineSource = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None

    pricing: VariantPricing | None = None
    line_subtotal_amount: int = 0      # quantity x current price (0 if removed)
    # Custom designs have no inventory; this is set to 1 once the design
    # session resolves and 0 if it's gone, so the rest of the cart code
    # can treat both kinds uniformly.
    available_quantity: int = 0

    # Optional human-readable note (e.g. "Was $99.00, now $79.00")
    message: str | None = None


class CartTotals(BaseModel):
    subtotal_amount: int
    item_count: int
    currency: str


class RevalidateResponse(BaseModel):
    lines: list[CartLineState]
    totals: CartTotals
    any_changes: bool
    blocks_checkout: bool   # True if any line is out_of_stock or removed


class FullLookAddResponse(BaseModel):
    added_lines: list[CartLineState]
    unavailable_lines: list[CartLineState]
    swap_suggestions: list[str] = Field(default_factory=list)
    all_available: bool


# ── Server-side cart (M5.2) ─────────────────────────────────────────
class ServerCartLine(BaseModel):
    """A single line on a customer's server-side cart.

    Snapshot fields (``price_snapshot``, ``added_at``) capture what was true
    at add time. Enriched fields (``product_title``, ``variant_size``…) are
    populated at read time from the current product/variant docs so the
    cart page can render without a second round-trip. Stock-level validation
    (price changes, OOS) still goes through ``POST /cart/revalidate``.
    """

    line_id: str
    product_id: str
    variant_id: str
    quantity: int
    source: LineSource = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None
    price_snapshot: VariantPricing
    added_at: datetime
    # Read-time enrichment:
    product_title: str | None = None
    variant_size: str | None = None
    variant_color: str | None = None
    variant_color_hex: str | None = None
    primary_media_asset_id: str | None = None


class ServerCart(BaseModel):
    cart_id: str
    customer_id: str
    status: Literal["active", "converted", "abandoned"]
    lines: list[ServerCartLine]
    item_count: int
    snapshot_subtotal_amount: int
    currency: str
    last_validated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AddLineRequest(BaseModel):
    product_id: str
    variant_id: str
    quantity: int = Field(1, ge=1, le=99)
    source: LineSource = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None


class UpdateLineRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=99)


class MergeCartRequest(BaseModel):
    """Anonymous local cart payload to merge into the server cart on login."""

    lines: list[CartLineInput] = Field(default_factory=list, max_length=99)
