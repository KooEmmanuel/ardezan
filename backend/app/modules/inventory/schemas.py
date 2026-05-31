"""Inventory module schemas — soft holds and availability snapshots.

Mirrors ``DATA_MODEL.md`` §7.2 (``inventory_holds`` collection).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

HoldStatus = Literal["active", "committed", "released", "expired"]


class InventoryHold(BaseModel):
    hold_id: str
    cart_id: str | None = None
    checkout_session_id: str
    customer_id: str | None = None
    guest_cart_id: str | None = None
    variant_id: str
    product_id: str
    quantity: int = Field(..., ge=1)
    status: HoldStatus = "active"
    expires_at: datetime
    committed_at: datetime | None = None
    released_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Service-level request/response shapes ───────────────────────────
class ReservationLine(BaseModel):
    """One line in a multi-variant reservation request."""

    variant_id: str
    quantity: int = Field(..., ge=1)


class Availability(BaseModel):
    """Snapshot of availability for one variant."""

    variant_id: str
    product_id: str
    stock_on_hand: int
    held_units: int
    available_for_sale: int

    @classmethod
    def from_variant_doc(cls, doc: dict[str, Any]) -> Availability:
        inv = doc.get("inventory", {}) or {}
        stock = int(inv.get("stock_on_hand", 0))
        held = int(inv.get("held_units", 0))
        return cls(
            variant_id=doc["variant_id"],
            product_id=doc["product_id"],
            stock_on_hand=stock,
            held_units=held,
            available_for_sale=max(0, stock - held),
        )
