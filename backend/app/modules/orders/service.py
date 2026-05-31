"""Order creation orchestration.

``create_from_checkout`` is called by the Stripe webhook handler after
``payment_intent.succeeded``. It is idempotent at three levels:

1. ``payment_events`` unique index (provider, provider_event_id) — the webhook
   handler returns early on a duplicate event.
2. ``orders`` unique sparse index on ``checkout_session_id`` — a concurrent
   second call raises ``DuplicateKeyError``; we recover by returning the
   existing order.
3. ``checkout_sessions.status`` transition — once a session is ``paid`` we
   don't re-process.

Inventory holds are committed (held_units → stock_on_hand decrement) inside
this flow per REQ-038.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from itsdangerous import URLSafeTimedSerializer
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.checkout.repository import CheckoutRepository
from app.modules.checkout.schemas import Address
from app.modules.checkout.stripe_client import get_stripe_client
from app.modules.inventory.service import InventoryService
from app.modules.orders.repository import OrdersRepository
from app.queue import get_queue
from app.modules.orders.schemas import (
    OrderFulfillment,
    OrderLine,
    OrderPayment,
    OrderPublic,
    OrderRefund,
    OrderReturnRequest,
)

log = get_logger(__name__)

GUEST_TOKEN_SALT = "atelier-guest-order-v1"
GUEST_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days (REQ-046)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _order_id() -> str:
    return f"ord_{secrets.token_hex(12)}"


def _issue_guest_token(order_id: str, secret: str) -> tuple[str, str, datetime]:
    """Return ``(raw_token, sha256_hash, expires_at)``.

    The raw token is given to the customer in the confirmation email. The hash
    is stored on the order; raw is never persisted. itsdangerous embeds an
    expiry so verification can reject stale tokens without a DB read.
    """
    serializer = URLSafeTimedSerializer(secret, salt=GUEST_TOKEN_SALT)
    raw = serializer.dumps({"order_id": order_id, "purpose": "manage"})
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires_at = _now() + timedelta(seconds=GUEST_TOKEN_TTL_SECONDS)
    return raw, hashed, expires_at


def verify_guest_token(token: str, secret: str) -> str | None:
    """Verify a guest token and return the ``order_id`` it was issued for."""
    serializer = URLSafeTimedSerializer(secret, salt=GUEST_TOKEN_SALT)
    try:
        data = serializer.loads(token, max_age=GUEST_TOKEN_TTL_SECONDS)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("order_id") if data.get("purpose") == "manage" else None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class OrdersService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = OrdersRepository(db)
        self.checkout_repo = CheckoutRepository(db)
        self.inventory = InventoryService(db)

    # ── Reads ──────────────────────────────────────────────────
    async def get(self, order_id: str) -> OrderPublic:
        doc = await self.repo.find_by_id(order_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        return _to_public(doc, include_guest_token=False)

    async def find_by_payment_intent(
        self, payment_intent_id: str
    ) -> dict[str, Any] | None:
        """Lookup the raw order doc by Stripe payment_intent.

        Used by the post-Stripe-redirect pending page that polls until the
        webhook has had time to materialize the order. Returns the raw doc so
        the caller can choose to authorize (cookie vs guest token).
        """
        return await self.repo.find_by_payment_intent(payment_intent_id)

    async def materialize_from_payment_intent(
        self, payment_intent_id: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fallback for the by-payment-intent lookup endpoint.

        If the webhook hasn't fired (or won't — common in local dev
        without ``stripe listen``), fetch the PaymentIntent directly
        from Stripe. If it really did succeed and carries the
        ``checkout_session_id`` we stamped in its metadata, run the
        same idempotent ``create_from_checkout`` path the webhook uses.

        Returns ``(order_doc, raw_guest_token)`` on success. The raw
        guest token is non-None only on first materialization of a
        guest order (it's never persisted; only the hash is stored).
        """
        from app.modules.checkout.stripe_client import StripeClient

        stripe_client = StripeClient(self.settings)
        intent = await stripe_client.retrieve_payment_intent(payment_intent_id)
        if not intent:
            return None, None
        status = intent.get("status")
        if status != "succeeded":
            # User got redirected back but the PI isn't actually paid yet
            # (e.g. 3-D Secure still pending). Tell the client to keep polling.
            return None, None
        metadata = intent.get("metadata") or {}
        checkout_session_id = metadata.get("checkout_session_id")
        if not checkout_session_id:
            return None, None
        try:
            public = await self.create_from_checkout(
                checkout_session_id,
                stripe_payment_intent_id=payment_intent_id,
            )
        except ApiError as exc:
            log.warning(
                "order.materialize_fallback_failed",
                payment_intent_id=payment_intent_id,
                checkout_session_id=checkout_session_id,
                code=exc.code,
                message=str(exc),
            )
            return None, None
        # create_from_checkout returns OrderPublic; ``guest_claim_token`` is
        # populated only on first creation of a guest order (idempotent
        # re-call returns the existing order without the raw token).
        raw_token = getattr(public, "guest_claim_token", None)
        doc = await self.repo.find_by_payment_intent(payment_intent_id)
        return doc, raw_token

    async def get_for_guest(self, order_id: str, token: str) -> OrderPublic:
        """Lookup with a signed guest token. Token validated *and* compared
        against the stored hash."""
        order_id_from_token = verify_guest_token(token, self.settings.guest_token_secret)
        if not order_id_from_token or order_id_from_token != order_id:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Invalid or expired guest token.",
                http_status=401,
            )
        doc = await self.repo.find_by_id(order_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        stored_hash = doc.get("guest_management_token_hash")
        if not stored_hash or stored_hash != _hash_token(token):
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Token does not match this order.",
                http_status=401,
            )
        return _to_public(doc, include_guest_token=False)

    # ── Create (called by webhook on payment_intent.succeeded) ─
    async def create_from_checkout(
        self,
        checkout_session_id: str,
        *,
        stripe_payment_intent_id: str,
    ) -> OrderPublic:
        """Idempotent. Returns the order whether we just created it or it
        already existed for this checkout session."""
        # 0. Short-circuit: order already exists?
        existing = await self.repo.find_by_checkout_session(checkout_session_id)
        if existing:
            log.info(
                "order.idempotent_skip",
                order_id=existing["order_id"],
                checkout_session_id=checkout_session_id,
                reason="order_already_exists",
            )
            return _to_public(existing, include_guest_token=False)

        # 1. Look up the checkout session.
        session = await self.checkout_repo.find_by_id(checkout_session_id)
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Checkout session not found: {checkout_session_id}",
                http_status=404,
            )

        # 2. Build the order document.
        now = _now()
        order_id = _order_id()
        order_number = await self.repo.next_order_number()

        order_lines: list[dict[str, Any]] = []
        for line in session["lines"]:
            order_lines.append(
                OrderLine(
                    line_id=line["line_id"],
                    kind=line.get("kind", "catalog"),
                    product_id=line.get("product_id"),
                    variant_id=line.get("variant_id"),
                    design_session_id=line.get("design_session_id"),
                    sku=line.get("sku", ""),
                    title_snapshot=line["title_snapshot"],
                    size=line.get("size", ""),
                    color=line.get("color", ""),
                    quantity=line["quantity"],
                    unit_price_amount=line["unit_price_amount"],
                    line_total_amount=line["line_total_amount"],
                    currency=line["currency"],
                    source=line.get("source", "catalog"),
                    try_on_session_id=line.get("try_on_session_id"),
                    try_on_card_id=line.get("try_on_card_id"),
                ).model_dump()
            )

        payment = OrderPayment(
            provider="stripe",
            stripe_payment_intent_id=stripe_payment_intent_id,
            payment_status="succeeded",
            paid_at=now,
        ).model_dump()

        # Guest claim token (only if no logged-in customer).
        guest_token_raw: str | None = None
        guest_token_hash: str | None = None
        guest_claim_expires_at: datetime | None = None
        if not session.get("customer_id") and session.get("guest_email"):
            guest_token_raw, guest_token_hash, guest_claim_expires_at = _issue_guest_token(
                order_id, self.settings.guest_token_secret
            )

        order_doc: dict[str, Any] = {
            "order_id": order_id,
            "order_number": order_number,
            "checkout_session_id": checkout_session_id,
            "customer_id": session.get("customer_id"),
            "guest_email": session.get("guest_email"),
            "guest_management_token_hash": guest_token_hash,
            "guest_claim_expires_at": guest_claim_expires_at,
            "status": "paid",
            "lines": order_lines,
            "totals": session["totals"],
            "shipping_address": session["shipping_address"],
            "billing_address": session.get("billing_address"),
            "payment": payment,
            "fulfillment": OrderFulfillment().model_dump(),
            "refunds": [],
            "support_notes": [],
            "linked_order_ids": [],
            "shipping_method": session.get("shipping_method", "standard"),
            "created_at": now,
            "updated_at": now,
            "cancelled_at": None,
        }

        # 3. Insert. Unique index on checkout_session_id catches a racing
        # duplicate webhook; we recover by returning the existing order.
        try:
            await self.repo.insert(order_doc)
        except DuplicateKeyError:
            existing_after_race = await self.repo.find_by_checkout_session(
                checkout_session_id
            )
            if existing_after_race:
                log.info(
                    "order.idempotent_race",
                    order_id=existing_after_race["order_id"],
                    checkout_session_id=checkout_session_id,
                )
                return _to_public(existing_after_race, include_guest_token=False)
            raise

        # 4. Commit inventory holds (held_units → stock_on_hand decrement).
        committed = await self.inventory.commit_checkout(checkout_session_id)

        # 5. Mark the checkout session paid.
        await self.checkout_repo.update_status(
            checkout_session_id, status="paid", now=now
        )

        # 5b. Pin any AI try-on artifacts behind the order's lines so the
        # fulfillment team can view the generated look + source photo. Best-
        # effort — a failure here must never block order creation.
        try:
            from app.modules.orders.tryon_retention import pin_order_tryon_artifacts

            await pin_order_tryon_artifacts(self.db, order_doc)
        except Exception:
            log.exception("order.tryon_pin_failed", order_id=order_id)

        log.info(
            "order.created",
            order_id=order_id,
            order_number=order_number,
            checkout_session_id=checkout_session_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
            total=order_doc["totals"]["total_amount"],
            currency=order_doc["totals"]["currency"],
            committed_holds=committed,
            is_guest=bool(session.get("guest_email") and not session.get("customer_id")),
        )

        # 6. Enqueue the confirmation email. We send async so the webhook
        # handler returns 200 to Stripe fast — never blocked on SMTP.
        try:
            queue = get_queue()
            await queue.enqueue_job(
                "send_order_confirmation",
                order_id,
                guest_token_raw,  # may be None for logged-in customers
            )
        except Exception:  # noqa: BLE001
            # Don't fail the whole webhook just because the queue is down.
            # The order exists; the email can be retried later (M3 ops tool).
            log.exception("order.email_enqueue_failed", order_id=order_id)

        # 7. Return — include the one-time guest token on initial creation only.
        public = _to_public(order_doc, include_guest_token=True)
        if guest_token_raw:
            public.guest_claim_token = guest_token_raw
            public.guest_claim_expires_at = guest_claim_expires_at
        return public

    # ── M5.3 customer-facing operations ────────────────────────
    async def list_for_customer(
        self,
        customer_id: str,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[OrderPublic], int]:
        items, total = await self.repo.list_for_customer(
            customer_id, limit=limit, offset=offset
        )
        return (
            [_to_public(d, include_guest_token=False) for d in items],
            total,
        )

    async def get_for_customer(
        self, order_id: str, customer_id: str
    ) -> OrderPublic:
        """Return the order only if it belongs to ``customer_id``. Otherwise
        404 — we don't reveal whether the order exists to non-owners."""
        doc = await self.repo.find_by_id(order_id)
        if not doc or doc.get("customer_id") != customer_id:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        return _to_public(doc, include_guest_token=False)

    async def cancel_for_customer(
        self, order_id: str, customer_id: str
    ) -> OrderPublic:
        """Customer-initiated cancellation. Allowed only pre-``packed``
        (REQ-049 + SPECS §5.3). Issues a Stripe refund for the remaining
        refundable balance, restocks inventory, and flips status."""
        doc = await self.repo.find_by_id(order_id)
        if not doc or doc.get("customer_id") != customer_id:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        if doc["status"] != "paid":
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Can't cancel — current status is '{doc['status']}'. "
                "Contact support after the order is packed.",
                http_status=409,
                details={"status": doc["status"]},
            )

        return await self._refund_and_cancel(doc, reason="requested_by_customer")

    async def request_return(
        self,
        order_id: str,
        *,
        reason: str,
        line_ids: list[str] | None,
        customer_id: str | None,
        guest_token: str | None,
    ) -> OrderPublic:
        """Customer or guest opens a return request.

        Allowed when the order is ``shipped`` or ``delivered`` (per the
        admin state machine ``shipped → return_requested`` and
        ``delivered → return_requested``). Idempotent: re-requesting on
        an already-pending return just updates the reason.
        """
        doc = await self.repo.find_by_id(order_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )

        # Authorize: signed-in owner OR matching guest token.
        if customer_id:
            if doc.get("customer_id") != customer_id:
                raise ApiError(
                    ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
                )
        elif guest_token:
            order_id_from_token = verify_guest_token(
                guest_token, self.settings.guest_token_secret
            )
            if not order_id_from_token or order_id_from_token != order_id:
                raise ApiError(
                    ErrorCode.UNAUTHENTICATED,
                    "Invalid or expired claim token.",
                    http_status=401,
                )
            if doc.get("guest_management_token_hash") != _hash_token(guest_token):
                raise ApiError(
                    ErrorCode.UNAUTHENTICATED,
                    "Token does not match this order.",
                    http_status=401,
                )
        else:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Sign in or provide a guest claim token.",
                http_status=401,
            )

        if doc["status"] not in {"shipped", "delivered", "return_requested"}:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Returns are only available after delivery. Current status: {doc['status']}.",
                http_status=409,
                details={"status": doc["status"]},
            )

        # Validate line_ids belong to this order (defence against probing).
        valid_line_ids = {lin["line_id"] for lin in doc.get("lines", [])}
        chosen_lines = [lid for lid in (line_ids or []) if lid in valid_line_ids]

        now = _now()
        return_doc = {
            "reason": reason.strip()[:400],
            "line_ids": chosen_lines,
            "requested_at": now,
            "status": "pending",
            "note": None,
            "received_at": None,
            "refund_id": None,
        }
        updated = await self.repo.update_fields(
            order_id,
            {
                "return_request": return_doc,
                "status": "return_requested",
                "updated_at": now,
            },
        )
        assert updated is not None

        # Best-effort email enqueue. Both notifications are optional —
        # the return is recorded either way.
        try:
            queue = get_queue()
            await queue.enqueue_job(
                "send_return_requested",
                order_id,
            )
        except Exception:  # noqa: BLE001
            log.exception("order.return_email_enqueue_failed", order_id=order_id)

        log.info(
            "order.return_requested",
            order_id=order_id,
            customer_id=customer_id,
            line_count=len(chosen_lines),
        )
        return _to_public(updated, include_guest_token=False)

    async def update_shipping_address_for_customer(
        self,
        order_id: str,
        customer_id: str,
        address: Address,
    ) -> OrderPublic:
        """Pre-shipment address edit (allowed while status ≤ packed)."""
        doc = await self.repo.find_by_id(order_id)
        if not doc or doc.get("customer_id") != customer_id:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        if doc["status"] not in {"paid", "packed"}:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Address can't be edited at status '{doc['status']}'.",
                http_status=409,
            )
        now = _now()
        updated = await self.repo.update_fields(
            order_id,
            {
                "shipping_address": address.model_dump(),
                "updated_at": now,
            },
        )
        assert updated is not None
        log.info(
            "order.customer_address_updated",
            order_id=order_id,
            customer_id=customer_id,
        )
        return _to_public(updated, include_guest_token=False)

    async def claim_guest_order(
        self,
        order_id: str,
        token: str,
        customer_id: str,
    ) -> OrderPublic:
        """Convert a guest order into a registered account.

        Verifies the signed token + the SHA-256 hash stored on the order, then
        sets ``customer_id`` and clears ``guest_management_token_hash`` so the
        token is single-use. The claim window is the 7-day token TTL from M2.
        """
        order_id_from_token = verify_guest_token(token, self.settings.guest_token_secret)
        if not order_id_from_token or order_id_from_token != order_id:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Invalid or expired claim token.",
                http_status=401,
            )
        doc = await self.repo.find_by_id(order_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        stored_hash = doc.get("guest_management_token_hash")
        if not stored_hash or stored_hash != _hash_token(token):
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Token does not match this order.",
                http_status=401,
            )
        # If the order is already claimed by someone else, reject.
        existing_owner = doc.get("customer_id")
        if existing_owner and existing_owner != customer_id:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Order is already linked to another account.",
                http_status=409,
            )
        # Already mine — idempotent.
        if existing_owner == customer_id:
            return _to_public(doc, include_guest_token=False)

        now = _now()
        updated = await self.repo.update_fields(
            order_id,
            {
                "customer_id": customer_id,
                "guest_management_token_hash": None,
                "guest_claim_expires_at": None,
                "updated_at": now,
            },
        )
        assert updated is not None
        log.info(
            "order.claimed_by_customer",
            order_id=order_id,
            customer_id=customer_id,
            previously_guest_email=doc.get("guest_email"),
        )
        return _to_public(updated, include_guest_token=False)

    # ── Internal: shared refund + cancel flow ─────────────────
    async def _refund_and_cancel(
        self,
        doc: dict[str, Any],
        *,
        reason: str,
    ) -> OrderPublic:
        order_id = doc["order_id"]
        payment = doc.get("payment") or {}
        if payment.get("payment_status") != "succeeded":
            raise ApiError(
                ErrorCode.CONFLICT,
                "Order can't be refunded yet — payment hasn't settled.",
                http_status=409,
            )
        payment_intent_id = payment.get("stripe_payment_intent_id")
        if not payment_intent_id:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Order has no payment intent on record.",
                http_status=409,
            )

        total = int(doc["totals"]["total_amount"])
        already_refunded = sum(
            int(r.get("amount", 0)) for r in doc.get("refunds", [])
        )
        amount = total - already_refunded
        if amount <= 0:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Order has already been fully refunded.",
                http_status=409,
            )

        stripe = get_stripe_client()
        idempotency_key = f"customer_cancel_{order_id}"
        stripe_refund = await stripe.create_refund(
            payment_intent_id=payment_intent_id,
            amount=amount,
            idempotency_key=idempotency_key,
            reason=reason if reason in {"duplicate", "fraudulent", "requested_by_customer"} else "requested_by_customer",
            metadata={
                "order_id": order_id,
                "order_number": doc.get("order_number", ""),
                "initiator": "customer",
            },
        )

        # Restock inventory.
        for line in doc.get("lines", []):
            variant_id = line.get("variant_id")
            qty = int(line.get("quantity", 0))
            if variant_id and qty > 0:
                await self.inventory.restock(variant_id, qty)

        # Append refund + flip status.
        now = _now()
        refund_doc = {
            "refund_id": f"ref_{secrets.token_hex(8)}",
            "provider_refund_id": stripe_refund.get("id", ""),
            "amount": amount,
            "reason": reason,
            "status": stripe_refund.get("status", "pending"),
            "created_at": now,
        }
        updated = await self.repo.push_refund(
            order_id,
            refund_doc=refund_doc,
            new_status="cancelled",
            now=now,
        )
        assert updated is not None
        await self.repo.update_fields(order_id, {"cancelled_at": now})

        # Order closed — start the 30-day purge clock on pinned try-on artifacts.
        try:
            from app.modules.orders.tryon_retention import set_order_tryon_expiry

            await set_order_tryon_expiry(self.db, order_id, closed_at=now)
        except Exception:
            log.exception("order.tryon_expiry_failed", order_id=order_id)

        log.info(
            "order.customer_cancelled",
            order_id=order_id,
            amount=amount,
            stripe_refund_id=stripe_refund.get("id"),
        )
        # Re-read so the response includes cancelled_at.
        final = await self.repo.find_by_id(order_id)
        assert final is not None
        return _to_public(final, include_guest_token=False)


# ── Doc → public projection ─────────────────────────────────────────
def _to_public(doc: dict[str, Any], *, include_guest_token: bool) -> OrderPublic:
    from app.modules.checkout.schemas import Address, CheckoutTotals

    public = OrderPublic(
        order_id=doc["order_id"],
        order_number=doc["order_number"],
        status=doc["status"],
        customer_id=doc.get("customer_id"),
        guest_email=doc.get("guest_email"),
        lines=[OrderLine(**lin) for lin in doc.get("lines", [])],
        totals=CheckoutTotals(**doc["totals"]),
        shipping_address=Address(**doc["shipping_address"]),
        billing_address=(
            Address(**doc["billing_address"]) if doc.get("billing_address") else None
        ),
        payment=OrderPayment(**doc["payment"]),
        fulfillment=OrderFulfillment(**(doc.get("fulfillment") or {})),
        refunds=[OrderRefund(**r) for r in (doc.get("refunds") or [])],
        return_request=(
            OrderReturnRequest(**doc["return_request"])
            if doc.get("return_request")
            else None
        ),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        cancelled_at=doc.get("cancelled_at"),
    )
    # The actual raw token is never stored — only returned at create time by
    # the caller. Expiry is fine to expose.
    if include_guest_token and doc.get("guest_claim_expires_at"):
        public.guest_claim_expires_at = doc["guest_claim_expires_at"]
    return public
