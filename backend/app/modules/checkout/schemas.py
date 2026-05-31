"""Checkout module schemas — sessions, addresses, totals."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.modules.cart.schemas import CartLineInput

CheckoutStatus = Literal["open", "paid", "expired", "cancelled", "failed"]
ShippingMethod = Literal["standard", "express"]


# ── Address ─────────────────────────────────────────────────────────
class Address(BaseModel):
    """Shipping or billing address. ISO 3166-1 alpha-2 country code."""

    name: str = Field(..., min_length=1, max_length=120)
    line1: str = Field(..., min_length=1, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str = Field(..., min_length=1, max_length=120)
    region: str | None = Field(None, max_length=120)  # state / province
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=2, max_length=2)
    phone: str | None = Field(None, max_length=32)


# ── Line snapshot (frozen at checkout time) ─────────────────────────
class CheckoutLineSnapshot(BaseModel):
    """One line as captured at checkout creation.

    Prices and titles are frozen here. Even if the catalog or fabric
    library changes between checkout creation and payment success, the
    order is created at these snapshot values — Stripe already
    authorised this exact amount.

    ``kind="custom_design"`` lines carry ``design_session_id`` instead
    of ``variant_id`` and don't reserve inventory. The tailor queue
    consumes them after the order materialises.
    """

    line_id: str
    kind: Literal["catalog", "custom_design"] = "catalog"
    product_id: str | None = None
    variant_id: str | None = None
    design_session_id: str | None = None
    sku: str = ""
    title_snapshot: str
    size: str = ""
    color: str = ""
    quantity: int = Field(..., ge=1)
    unit_price_amount: int = Field(..., ge=0)
    line_total_amount: int = Field(..., ge=0)
    currency: str
    source: str = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None


class CheckoutTotals(BaseModel):
    subtotal_amount: int = Field(..., ge=0)
    discount_amount: int = Field(0, ge=0)
    tax_amount: int = Field(0, ge=0)
    shipping_amount: int = Field(0, ge=0)
    total_amount: int = Field(..., ge=0)
    currency: str


# ── Requests ────────────────────────────────────────────────────────
class CreateCheckoutSessionRequest(BaseModel):
    lines: list[CartLineInput] = Field(..., min_length=1, max_length=99)
    guest_email: EmailStr | None = None
    shipping_address: Address
    billing_address: Address | None = None
    discount_code: str | None = None
    shipping_method: ShippingMethod = "standard"


# ── Responses ───────────────────────────────────────────────────────
class CheckoutSessionPublic(BaseModel):
    """Public-facing shape of a checkout session. ``stripe_client_secret`` is
    only populated on creation; re-reads via GET omit it."""

    checkout_session_id: str
    status: CheckoutStatus
    lines: list[CheckoutLineSnapshot]
    totals: CheckoutTotals
    shipping_address: Address
    billing_address: Address | None = None
    guest_email: str | None = None
    customer_id: str | None = None
    shipping_method: ShippingMethod = "standard"

    # Only returned on initial creation. Frontend uses this with stripe.js.
    stripe_client_secret: str | None = None
    stripe_publishable_key: str | None = None

    expires_at: datetime
    created_at: datetime
