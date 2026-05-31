"""Admin order schemas — list filters, mutations, admin-only response shape."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.checkout.schemas import Address
from app.modules.orders.schemas import (
    OrderFulfillment,
    OrderLine,
    OrderPayment,
    OrderRefund,
    OrderReturnRequest,
    OrderStatus,
    OrderSupportNote,
)

# Stripe's allowed refund reasons. Anything else goes in ``metadata``.
RefundReason = Literal["duplicate", "fraudulent", "requested_by_customer"]


# ── Mutation requests ───────────────────────────────────────────────
class StatusUpdateRequest(BaseModel):
    """Change order status. State-machine validated server-side."""

    status: OrderStatus
    # Only consulted when ``status == "shipped"``.
    tracking_number: str | None = Field(None, max_length=120)
    carrier: str | None = Field(None, max_length=80)
    service_level: str | None = Field(None, max_length=80)


class AddressUpdateRequest(BaseModel):
    """Replace the shipping (or billing) address. Pre-shipment only."""

    address: Address


class RefundCreateRequest(BaseModel):
    """If ``amount`` is omitted, refunds the remaining refundable balance."""

    amount: int | None = Field(None, ge=1)
    reason: RefundReason | None = None
    note: str | None = Field(None, max_length=400)


class SupportNoteCreateRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000)


# ── Response shapes ─────────────────────────────────────────────────
class OrderAdminPublic(BaseModel):
    """Full order document as the admin sees it."""

    order_id: str
    order_number: str
    status: OrderStatus
    customer_id: str | None = None
    guest_email: str | None = None
    checkout_session_id: str | None = None

    lines: list[OrderLine]
    totals: dict
    shipping_address: Address
    billing_address: Address | None = None
    payment: OrderPayment
    fulfillment: OrderFulfillment
    refunds: list[OrderRefund] = Field(default_factory=list)
    return_request: OrderReturnRequest | None = None
    support_notes: list[OrderSupportNote] = Field(default_factory=list)
    linked_order_ids: list[str] = Field(default_factory=list)
    shipping_method: str | None = None

    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None


class OrderListResponse(BaseModel):
    items: list[OrderAdminPublic]
    total: int
    limit: int
    offset: int


class RefundCreateResponse(BaseModel):
    refund: OrderRefund
    new_status: OrderStatus
    total_refunded_amount: int
    refundable_remaining: int


# ── Try-on provenance (fulfillment verification) ────────────────────
class OrderTryOnItem(BaseModel):
    """One garment that was part of the recommended look."""

    product_id: str
    variant_id: str
    product_title: str | None = None
    category: str | None = None
    color: str | None = None
    recommended_size: str | None = None
    selected_size: str | None = None
    price_amount: int | None = None


class OrderTryOnLook(BaseModel):
    """The AI try-on look behind a single order line.

    ``generated_look_image_url`` is the customer rendered in the recommended
    garments — what fulfillment uses to confirm the right items are packed.
    ``images_available`` is False once the artifacts have been purged (e.g.
    30+ days after the order closed).
    """

    line_id: str
    sku: str
    title_snapshot: str
    size: str | None = None
    color: str | None = None
    quantity: int
    try_on_session_id: str
    try_on_card_id: str | None = None
    outfit_name: str | None = None
    rationale: str | None = None
    generated_look_image_url: str | None = None
    source_photo_url: str | None = None
    images_available: bool = False
    session_source: str | None = None
    session_status: str | None = None
    session_created_at: datetime | None = None
    items: list[OrderTryOnItem] = Field(default_factory=list)


class OrderTryOnResponse(BaseModel):
    order_id: str
    order_number: str
    looks: list[OrderTryOnLook] = Field(default_factory=list)
