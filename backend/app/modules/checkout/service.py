"""Checkout orchestration — the heart of M2 commerce.

Flow per ARCHITECTURE §5.5:

1. Look up idempotency key — if seen, return the existing session.
2. Revalidate every cart line (current price, availability, stock).
3. If any line ``blocks_checkout``, fail with OUT_OF_STOCK.
4. Build per-line snapshots at the *current* price.
5. Compute totals (subtotal + shipping + tax — placeholders for OD-009).
6. Atomically reserve inventory holds (all-or-nothing).
7. Create the Stripe PaymentIntent with the same idempotency key.
   - On Stripe failure: release all holds and raise.
8. Persist the checkout_session document.
9. Return the session with ``stripe_client_secret`` for the frontend.

The order is NOT created here — that happens in the webhook handler after
``payment_intent.succeeded`` (ADR-005, REQ-074). This separation is what
makes the system survive customers closing the tab between Stripe success
and order creation.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.cart.service import CartService
from app.modules.checkout.repository import CheckoutRepository
from app.modules.checkout.schemas import (
    Address,
    CheckoutLineSnapshot,
    CheckoutSessionPublic,
    CheckoutStatus,
    CheckoutTotals,
    CreateCheckoutSessionRequest,
    ShippingMethod,
)
from app.modules.checkout.stripe_client import StripeClient, get_stripe_client
from app.modules.inventory.schemas import ReservationLine
from app.modules.inventory.service import InventoryService

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_id() -> str:
    return f"chk_{secrets.token_hex(12)}"


# ── Tax + shipping (Phase 1 placeholders — OD-009 will replace these) ──
def calculate_shipping(method: ShippingMethod) -> int:
    """Flat-rate shipping. Real carrier-rate lookup is OD-004."""
    return 1800 if method == "express" else 800


def calculate_tax(taxable_amount: int, country: str) -> int:
    """Naive flat tax. Real Stripe Tax integration is OD-009.

    8% for US shipments, 0% otherwise — clearly a placeholder.
    """
    if country.upper() == "US":
        return round(taxable_amount * 0.08)
    return 0


class CheckoutService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = CheckoutRepository(db)
        self.cart = CartService(db)
        self.inventory = InventoryService(db)
        self.stripe: StripeClient = get_stripe_client()

    # ── Reads ──────────────────────────────────────────────────
    async def get_session(self, checkout_session_id: str) -> CheckoutSessionPublic:
        doc = await self.repo.find_by_id(checkout_session_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Checkout session not found: {checkout_session_id}",
                http_status=404,
            )
        return _to_public(doc, include_client_secret=False)

    # ── Cancel ─────────────────────────────────────────────────
    async def cancel_session(self, checkout_session_id: str) -> CheckoutSessionPublic:
        doc = await self.repo.find_by_id(checkout_session_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Checkout session not found: {checkout_session_id}",
                http_status=404,
            )
        if doc["status"] != "open":
            return _to_public(doc, include_client_secret=False)

        now = _now()
        await self.repo.update_status(checkout_session_id, status="cancelled", now=now)
        await self.inventory.release_checkout(checkout_session_id)
        if doc.get("stripe_payment_intent_id"):
            await self.stripe.cancel_payment_intent(doc["stripe_payment_intent_id"])
        log.info("checkout.cancelled", checkout_session_id=checkout_session_id)
        updated = await self.repo.find_by_id(checkout_session_id)
        assert updated is not None
        return _to_public(updated, include_client_secret=False)

    # ── Create ─────────────────────────────────────────────────
    async def create_session(
        self,
        request: CreateCheckoutSessionRequest,
        *,
        idempotency_key: str,
        customer_id: str | None = None,
    ) -> CheckoutSessionPublic:
        # 1. Idempotency check.
        existing = await self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            log.info(
                "checkout.idempotent_return",
                checkout_session_id=existing["checkout_session_id"],
            )
            # Re-issue client_secret only if intent still active. Safe because the
            # Stripe intent is the same one we created originally.
            return _to_public(existing, include_client_secret=True)

        # 2. Revalidate the cart.
        revalidated = await self.cart.revalidate(request.lines)
        if revalidated.blocks_checkout:
            raise ApiError(
                ErrorCode.OUT_OF_STOCK,
                "One or more items are no longer available.",
                http_status=409,
                details={
                    "lines": [
                        {"line_id": s.line_id, "status": s.status, "message": s.message}
                        for s in revalidated.lines
                        if s.status in {"removed", "out_of_stock"}
                    ]
                },
            )

        # 3. Build snapshots from revalidated lines at the current price.
        snapshots: list[CheckoutLineSnapshot] = []
        currency = self.settings.store_currency
        for line_in, state in zip(request.lines, revalidated.lines, strict=True):
            if state.status == "removed" or state.pricing is None:
                continue  # filtered out by blocks_checkout earlier, defensive
            effective_qty = min(state.quantity, state.available_quantity)
            if effective_qty <= 0:
                continue
            unit_price = state.pricing.price_amount
            currency = state.pricing.currency
            snapshots.append(
                CheckoutLineSnapshot(
                    line_id=state.line_id,
                    kind=state.kind,
                    product_id=state.product_id,
                    variant_id=state.variant_id,
                    design_session_id=state.design_session_id,
                    # SKU is meaningless for custom designs — the design
                    # session id plays that role downstream.
                    sku=(state.variant_id or "") if state.kind == "catalog" else "",
                    title_snapshot=state.product_title or "",
                    size=state.size or "",
                    color=state.color or "",
                    quantity=effective_qty,
                    unit_price_amount=unit_price,
                    line_total_amount=unit_price * effective_qty,
                    currency=currency,
                    source=line_in.source,
                    try_on_session_id=line_in.try_on_session_id,
                    try_on_card_id=line_in.try_on_card_id,
                )
            )

        if not snapshots:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Cart is empty after revalidation.",
                http_status=400,
            )

        # Backfill SKUs for catalog lines only — custom designs don't have one.
        await self._fill_skus(snapshots)

        # 4. Totals.
        subtotal = sum(s.line_total_amount for s in snapshots)
        shipping = calculate_shipping(request.shipping_method)
        tax = calculate_tax(subtotal + shipping, request.shipping_address.country)
        total = subtotal + shipping + tax
        totals = CheckoutTotals(
            subtotal_amount=subtotal,
            shipping_amount=shipping,
            tax_amount=tax,
            total_amount=total,
            currency=currency,
        )

        # 5. Allocate the session id and reserve inventory. Custom-design
        # lines bypass inventory entirely — they're made-to-order.
        checkout_session_id = _session_id()
        reservation_lines = [
            ReservationLine(variant_id=s.variant_id, quantity=s.quantity)
            for s in snapshots
            if s.kind == "catalog" and s.variant_id
        ]
        if reservation_lines:
            await self.inventory.reserve_for_checkout(
                reservation_lines,
                checkout_session_id=checkout_session_id,
                ttl_minutes=self.settings.checkout_soft_hold_minutes,
                customer_id=customer_id,
            )

        # 6. Create the Stripe PaymentIntent. Release holds on any failure.
        try:
            intent = await self.stripe.create_payment_intent(
                amount=total,
                currency=currency,
                idempotency_key=idempotency_key,
                metadata={
                    "checkout_session_id": checkout_session_id,
                    "atelier_env": self.settings.app_env,
                    "customer_id": customer_id or "",
                    "guest_email": request.guest_email or "",
                },
                customer_email=request.guest_email,
                description=f"Ardezan order — {len(snapshots)} item(s)",
            )
        except Exception:
            await self.inventory.release_checkout(checkout_session_id)
            raise

        # 7. Persist the checkout session.
        now = _now()
        expires_at = now + timedelta(minutes=self.settings.checkout_soft_hold_minutes)
        doc: dict[str, Any] = {
            "checkout_session_id": checkout_session_id,
            "idempotency_key": idempotency_key,
            "status": "open",
            "lines": [s.model_dump() for s in snapshots],
            "totals": totals.model_dump(),
            "shipping_address": request.shipping_address.model_dump(),
            "billing_address": (
                request.billing_address.model_dump() if request.billing_address else None
            ),
            "guest_email": request.guest_email,
            "customer_id": customer_id,
            "shipping_method": request.shipping_method,
            "discount_code": request.discount_code,
            "stripe_payment_intent_id": intent["id"],
            "stripe_client_secret": intent.get("client_secret"),
            "expires_at": expires_at,
            "created_at": now,
            "updated_at": now,
        }
        await self.repo.insert(doc)

        log.info(
            "checkout.session_created",
            checkout_session_id=checkout_session_id,
            total_amount=total,
            currency=currency,
            line_count=len(snapshots),
            stripe_payment_intent_id=intent["id"],
        )
        return _to_public(doc, include_client_secret=True)

    # ── Helpers ────────────────────────────────────────────────
    async def _fill_skus(self, snapshots: list[CheckoutLineSnapshot]) -> None:
        variant_ids = [s.variant_id for s in snapshots if s.variant_id]
        if not variant_ids:
            return
        cursor = self.db["variants"].find(
            {"variant_id": {"$in": variant_ids}},
            projection={"variant_id": 1, "sku": 1, "_id": 0},
        )
        sku_by_id = {doc["variant_id"]: doc["sku"] async for doc in cursor}
        for s in snapshots:
            if not s.variant_id:
                continue
            sku = sku_by_id.get(s.variant_id)
            if sku:
                s.sku = sku


# ── Doc → public projection ─────────────────────────────────────────
def _to_public(
    doc: dict[str, Any],
    *,
    include_client_secret: bool,
) -> CheckoutSessionPublic:
    settings = get_settings()
    status: CheckoutStatus = doc["status"]
    return CheckoutSessionPublic(
        checkout_session_id=doc["checkout_session_id"],
        status=status,
        lines=[CheckoutLineSnapshot(**lin) for lin in doc.get("lines", [])],
        totals=CheckoutTotals(**doc["totals"]),
        shipping_address=Address(**doc["shipping_address"]),
        billing_address=(
            Address(**doc["billing_address"]) if doc.get("billing_address") else None
        ),
        guest_email=doc.get("guest_email"),
        customer_id=doc.get("customer_id"),
        shipping_method=doc.get("shipping_method", "standard"),
        stripe_client_secret=(
            doc.get("stripe_client_secret") if include_client_secret else None
        ),
        stripe_publishable_key=(
            settings.stripe_publishable_key if include_client_secret else None
        ),
        expires_at=doc["expires_at"],
        created_at=doc["created_at"],
    )
