"""Order schemas — mirrors DATA_MODEL.md §8.1."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.checkout.schemas import Address, CheckoutTotals

OrderStatus = Literal[
    "pending_payment",
    "paid",
    "packed",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
    "partially_refunded",
    "return_requested",
    "returned",
    "exchanged",
]


class OrderLine(BaseModel):
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
    compare_at_price_amount: int | None = None
    line_total_amount: int = Field(..., ge=0)
    currency: str
    source: str = "catalog"
    try_on_session_id: str | None = None
    try_on_card_id: str | None = None


class OrderPayment(BaseModel):
    provider: str = "stripe"
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None  # for Stripe Checkout (unused in Phase 1)
    payment_status: str = "succeeded"
    paid_at: datetime | None = None


class OrderFulfillment(BaseModel):
    carrier: str | None = None
    service_level: str | None = None
    tracking_number: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None


class OrderRefund(BaseModel):
    refund_id: str
    provider_refund_id: str
    amount: int = Field(..., ge=0)
    reason: str | None = None
    status: str
    created_at: datetime


class OrderSupportNote(BaseModel):
    note: str
    actor_id: str
    created_at: datetime


class OrderReturnRequest(BaseModel):
    """Customer-initiated return.

    Stored on the order doc itself. When ``status="received"``, the admin
    has confirmed receipt of the goods; restock + refund happen at that
    point.
    """

    reason: str = Field(..., min_length=2, max_length=400)
    line_ids: list[str] = Field(default_factory=list)  # empty = "all lines"
    requested_at: datetime
    status: Literal["pending", "received", "rejected"] = "pending"
    note: str | None = None
    received_at: datetime | None = None
    refund_id: str | None = None  # populated when admin issues refund


# ── Public-facing order shape ───────────────────────────────────────
class OrderPublic(BaseModel):
    order_id: str
    order_number: str
    status: OrderStatus
    customer_id: str | None = None
    guest_email: str | None = None
    lines: list[OrderLine]
    totals: CheckoutTotals
    shipping_address: Address
    billing_address: Address | None = None
    payment: OrderPayment
    fulfillment: OrderFulfillment
    refunds: list[OrderRefund] = Field(default_factory=list)
    return_request: OrderReturnRequest | None = None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None

    # Only returned to guest on initial order creation (one-time claim link).
    guest_claim_token: str | None = None
    guest_claim_expires_at: datetime | None = None
