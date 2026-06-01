"""Admin order management — status state machine, refunds, address edits.

Every mutation writes an ``audit_logs`` entry. Status transitions are
validated against an allow-list per REQ-047 + REQ-049:

    pending_payment   → (webhook only — admin can't move out of this)
    paid              → packed, cancelled
    packed            → shipped, cancelled
    shipped           → delivered, return_requested
    delivered         → return_requested
    return_requested  → returned, exchanged
    returned          → refunded, partially_refunded
    partially_refunded → refunded   (escalate to full)
    exchanged | cancelled | refunded → terminal

Refunds go through Stripe with a caller-supplied ``Idempotency-Key`` so
retries don't double-refund. The status on the order flips automatically
to ``partially_refunded`` or ``refunded`` based on remaining balance.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.orders_repository import AdminOrdersRepository
from app.queue import get_queue
from app.modules.admin.orders_schemas import (
    AddressUpdateRequest,
    RefundCreateRequest,
    StatusUpdateRequest,
    SupportNoteCreateRequest,
)
from app.modules.admin.repository import AdminRepository
from app.modules.checkout.stripe_client import StripeClient, get_stripe_client

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refund_id() -> str:
    return f"ref_{secrets.token_hex(8)}"


# ── Allowed status transitions ──────────────────────────────────────
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending_payment": set(),
    "paid": {"packed", "cancelled"},
    "packed": {"shipped", "cancelled"},
    "shipped": {"delivered", "return_requested"},
    "delivered": {"return_requested"},
    "return_requested": {"returned", "exchanged", "refunded", "partially_refunded"},
    "returned": {"refunded", "partially_refunded"},
    "exchanged": set(),
    "cancelled": set(),
    "refunded": set(),
    "partially_refunded": {"refunded"},
}

_ADDRESS_EDITABLE_STATUSES = {"paid", "packed"}


class AdminOrdersService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = AdminOrdersRepository(db)
        self.admin_repo = AdminRepository(db)
        self.stripe: StripeClient = get_stripe_client()

    # ── Reads ──────────────────────────────────────────────────
    async def list_orders(
        self,
        *,
        status: str | None,
        customer_id: str | None,
        guest_email: str | None,
        order_number: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        has_custom_design: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self.repo.list(
            status=status,
            customer_id=customer_id,
            guest_email=guest_email,
            order_number=order_number,
            created_after=created_after,
            created_before=created_before,
            has_custom_design=has_custom_design,
            limit=limit,
            offset=offset,
        )

    async def get_custom_designs(self, order_id: str) -> list[dict[str, Any]]:
        """Look up the design sessions referenced by an order's lines.

        Returns one entry per custom_design line, each carrying the
        brief, fabric snapshot, complexity, and a freshly-signed URL for
        the rendered image. The tailor's panel reads this for every
        custom order.
        """
        order = await self.repo.find_by_id(order_id)
        if not order:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        custom_lines = [
            l for l in order.get("lines", []) if l.get("kind") == "custom_design"
        ]
        if not custom_lines:
            return []

        design_ids = [
            l["design_session_id"] for l in custom_lines if l.get("design_session_id")
        ]
        cursor = self.db[C.design_sessions].find(
            {"design_session_id": {"$in": design_ids}}, projection={"_id": 0}
        )
        sessions: dict[str, dict[str, Any]] = {
            d["design_session_id"]: d async for d in cursor
        }

        # Re-sign the rendered image URL for each session so the admin
        # panel doesn't rely on cached URLs that have likely expired.
        from app.storage import get_storage

        storage = get_storage()
        results: list[dict[str, Any]] = []
        for line in custom_lines:
            s = sessions.get(line.get("design_session_id"))
            if not s:
                # Order has a custom_design line but the design session
                # was deleted — render a stub so the admin still sees it.
                results.append(
                    {
                        "line_id": line["line_id"],
                        "design_session_id": line.get("design_session_id"),
                        "status": "missing",
                        "title_snapshot": line.get("title_snapshot"),
                        "image_url": None,
                    }
                )
                continue

            async def _signed_for(media_asset_id: str | None) -> str | None:
                if not media_asset_id:
                    return None
                media = await self.db[C.media_assets].find_one(
                    {"media_asset_id": media_asset_id},
                    projection={"storage": 1, "_id": 0},
                )
                key = (media or {}).get("storage", {}).get("object_key")
                if not key:
                    return None
                return await storage.presigned_get_url(key, expires_in=3600)

            image_url = await _signed_for(s.get("generated_media_asset_id"))
            reference_image_url = await _signed_for(s.get("reference_media_asset_id"))

            results.append(
                {
                    "line_id": line["line_id"],
                    "design_session_id": s["design_session_id"],
                    "status": s["status"],
                    "title_snapshot": line.get("title_snapshot"),
                    "fabric": s.get("fabric_snapshot"),
                    "piece_type": s.get("piece_type"),
                    "complexity": s.get("complexity"),
                    "brief": s.get("brief"),
                    "fit_note": s.get("fit_note"),
                    "estimate": s.get("estimate"),
                    "image_url": image_url,
                    "reference_image_url": reference_image_url,
                    "unit_price_amount": line.get("unit_price_amount"),
                    "created_at": s.get("created_at"),
                }
            )
        return results

    async def get_order(self, order_id: str) -> dict[str, Any]:
        doc = await self.repo.find_by_id(order_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Order not found: {order_id}", http_status=404
            )
        return doc

    # ── Try-on provenance (fulfillment verification) ───────────
    async def get_order_try_ons(self, order_id: str) -> dict[str, Any]:
        """Return the AI try-on look(s) behind an order's lines.

        For every line that came from a try-on, resolves the generated look
        image (customer rendered in the garments) + the source photo + the
        recommended items, signing image URLs fresh. Admin-scoped: no
        ownership filter, since the operator legitimately sees every order.
        """
        order = await self.get_order(order_id)
        tryon_lines = [
            lin for lin in order.get("lines", []) if lin.get("try_on_session_id")
        ]
        base = {
            "order_id": order["order_id"],
            "order_number": order["order_number"],
            "looks": [],
        }
        if not tryon_lines:
            return base

        session_ids = sorted({lin["try_on_session_id"] for lin in tryon_lines})
        sessions: dict[str, dict[str, Any]] = {}
        cursor = self.db[C.try_on_sessions].find(
            {"try_on_session_id": {"$in": session_ids}}
        )
        async for sess in cursor:
            sessions[sess["try_on_session_id"]] = sess

        # Gather every image we may need to sign in two batches.
        gen_image_ids: set[str] = set()
        source_media_ids: set[str] = set()
        for sess in sessions.values():
            if sess.get("uploaded_media_asset_id"):
                source_media_ids.add(sess["uploaded_media_asset_id"])
            for card in sess.get("result_cards") or []:
                if card.get("generated_image_id"):
                    gen_image_ids.add(card["generated_image_id"])

        media_by_gen = await self._media_ids_for_generated_images(
            sorted(gen_image_ids)
        )
        all_media = set(media_by_gen.values()) | source_media_ids
        signed = await self._sign_media_assets(sorted(all_media))

        looks: list[dict[str, Any]] = []
        for line in tryon_lines:
            sess = sessions.get(line["try_on_session_id"])
            outfit_name = rationale = gen_url = source_url = None
            items: list[dict[str, Any]] = []
            session_source = session_status = None
            session_created_at = None

            if sess:
                session_source = sess.get("source")
                session_status = sess.get("status")
                session_created_at = sess.get("created_at")
                source_mid = sess.get("uploaded_media_asset_id")
                source_url = signed.get(source_mid) if source_mid else None

                card = next(
                    (
                        c
                        for c in (sess.get("result_cards") or [])
                        if c.get("card_id") == line.get("try_on_card_id")
                    ),
                    None,
                )
                if card:
                    outfit_name = card.get("outfit_name")
                    rationale = card.get("rationale")
                    items = card.get("items") or []
                    gid = card.get("generated_image_id")
                    if gid:
                        mid = media_by_gen.get(gid)
                        gen_url = signed.get(mid) if mid else None

            looks.append(
                {
                    "line_id": line["line_id"],
                    "sku": line.get("sku", ""),
                    "title_snapshot": line.get("title_snapshot", ""),
                    "size": line.get("size"),
                    "color": line.get("color"),
                    "quantity": line.get("quantity", 1),
                    "try_on_session_id": line["try_on_session_id"],
                    "try_on_card_id": line.get("try_on_card_id"),
                    "outfit_name": outfit_name,
                    "rationale": rationale,
                    "generated_look_image_url": gen_url,
                    "source_photo_url": source_url,
                    "images_available": bool(gen_url or source_url),
                    "session_source": session_source,
                    "session_status": session_status,
                    "session_created_at": session_created_at,
                    "items": items,
                }
            )

        base["looks"] = looks
        return base

    async def _media_ids_for_generated_images(
        self, generated_image_ids: list[str]
    ) -> dict[str, str]:
        if not generated_image_ids:
            return {}
        cursor = self.db[C.generated_images].find(
            {"generated_image_id": {"$in": generated_image_ids}},
            projection={"generated_image_id": 1, "media_asset_id": 1, "_id": 0},
        )
        return {
            doc["generated_image_id"]: doc["media_asset_id"]
            async for doc in cursor
            if doc.get("media_asset_id")
        }

    async def _sign_media_assets(
        self, media_asset_ids: list[str], *, expires_in: int = 3600
    ) -> dict[str, str]:
        """Sign GET URLs for media assets, skipping any that were purged."""
        if not media_asset_ids:
            return {}
        from app.storage import get_storage

        cursor = self.db[C.media_assets].find(
            {"media_asset_id": {"$in": media_asset_ids}},
            projection={
                "media_asset_id": 1,
                "storage.object_key": 1,
                "retention.deleted_at": 1,
                "storage_object_deleted_at": 1,
                "_id": 0,
            },
        )
        keys: dict[str, str] = {}
        async for doc in cursor:
            if (doc.get("retention") or {}).get("deleted_at") or doc.get(
                "storage_object_deleted_at"
            ):
                continue
            key = (doc.get("storage") or {}).get("object_key")
            if key:
                keys[doc["media_asset_id"]] = key

        storage = get_storage()
        signed: dict[str, str] = {}
        for media_id, key in keys.items():
            try:
                signed[media_id] = await storage.presigned_get_url(
                    key, expires_in=expires_in
                )
            except Exception as exc:
                log.warning(
                    "admin.order_tryon_sign_failed",
                    media_id=media_id,
                    error=str(exc),
                )
        return signed

    # ── Status transitions ────────────────────────────────────
    async def update_status(
        self,
        order_id: str,
        body: StatusUpdateRequest,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self.get_order(order_id)
        current = existing["status"]
        target = body.status

        if target == current:
            return existing  # idempotent

        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Cannot transition order from '{current}' to '{target}'.",
                http_status=409,
                details={"current": current, "allowed_next": sorted(allowed)},
            )

        now = _now()
        fields: dict[str, Any] = {"status": target, "updated_at": now}

        # Special fulfillment side effects.
        fulfillment = dict(existing.get("fulfillment") or {})
        if target == "shipped":
            if not body.tracking_number:
                raise ApiError(
                    ErrorCode.VALIDATION_ERROR,
                    "tracking_number is required when transitioning to 'shipped'.",
                    http_status=400,
                )
            fulfillment["carrier"] = body.carrier or fulfillment.get("carrier")
            fulfillment["service_level"] = body.service_level or fulfillment.get(
                "service_level"
            )
            fulfillment["tracking_number"] = body.tracking_number
            fulfillment["shipped_at"] = now
            fields["fulfillment"] = fulfillment
        elif target == "delivered":
            fulfillment["delivered_at"] = now
            fields["fulfillment"] = fulfillment
        elif target == "cancelled":
            fields["cancelled_at"] = now

        updated = await self.repo.update_fields(order_id, fields)
        assert updated is not None
        await self._audit(
            admin,
            action="order.status_changed",
            target_id=order_id,
            before={"status": current},
            after={
                "status": target,
                **{
                    k: v
                    for k, v in fields.items()
                    if k in {"cancelled_at", "fulfillment"}
                },
            },
        )
        log.info(
            "admin.order_status_changed",
            order_id=order_id,
            order_number=existing.get("order_number"),
            from_status=current,
            to_status=target,
        )

        # When the order closes, start (or refresh) the 30-day purge clock on
        # any pinned try-on artifacts. Best-effort — never block the transition.
        from app.modules.orders.tryon_retention import (
            CLOSING_STATUSES,
            set_order_tryon_expiry,
        )

        if target in CLOSING_STATUSES:
            try:
                await set_order_tryon_expiry(self.db, order_id, closed_at=now)
            except Exception:
                log.exception("admin.order_tryon_expiry_failed", order_id=order_id)

        # Notify the customer asynchronously on shipping milestones. The
        # queue may not be initialised in some test paths, so we swallow
        # errors here — the status update itself is the authoritative
        # event, the email is best-effort.
        try:
            queue = get_queue()
            if target == "shipped":
                await queue.enqueue_job("send_order_shipped", order_id)
            elif target == "delivered":
                await queue.enqueue_job("send_order_delivered", order_id)
        except RuntimeError as exc:
            log.warning(
                "admin.order_status_email_enqueue_failed",
                order_id=order_id,
                to_status=target,
                error=str(exc),
            )

        return updated

    # ── Address update ─────────────────────────────────────────
    async def update_shipping_address(
        self,
        order_id: str,
        body: AddressUpdateRequest,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self.get_order(order_id)
        if existing["status"] not in _ADDRESS_EDITABLE_STATUSES:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Address can't be edited at status '{existing['status']}' — must be "
                f"one of {sorted(_ADDRESS_EDITABLE_STATUSES)}.",
                http_status=409,
            )
        before = existing.get("shipping_address")
        fields = {
            "shipping_address": body.address.model_dump(),
            "updated_at": _now(),
        }
        updated = await self.repo.update_fields(order_id, fields)
        assert updated is not None
        await self._audit(
            admin,
            action="order.shipping_address_updated",
            target_id=order_id,
            before={"shipping_address": before},
            after={"shipping_address": fields["shipping_address"]},
        )
        log.info("admin.order_address_updated", order_id=order_id)
        return updated

    # ── Refunds ────────────────────────────────────────────────
    async def create_refund(
        self,
        order_id: str,
        body: RefundCreateRequest,
        *,
        idempotency_key: str,
        admin: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Create a Stripe refund and append it to the order. Returns
        ``(refund_doc, updated_order_doc)``."""
        existing = await self.get_order(order_id)
        payment = existing.get("payment") or {}
        if payment.get("payment_status") != "succeeded":
            raise ApiError(
                ErrorCode.CONFLICT,
                "Cannot refund an order whose payment hasn't succeeded.",
                http_status=409,
                details={"payment_status": payment.get("payment_status")},
            )
        payment_intent_id = payment.get("stripe_payment_intent_id")
        if not payment_intent_id:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Order has no payment intent on record.",
                http_status=409,
            )

        total = int(existing["totals"]["total_amount"])
        already_refunded = sum(int(r.get("amount", 0)) for r in existing.get("refunds", []))
        refundable_remaining = total - already_refunded
        if refundable_remaining <= 0:
            raise ApiError(
                ErrorCode.CONFLICT,
                "This order has already been fully refunded.",
                http_status=409,
                details={"already_refunded": already_refunded, "total": total},
            )

        amount = int(body.amount) if body.amount is not None else refundable_remaining
        if amount <= 0 or amount > refundable_remaining:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                f"Refund amount must be between 1 and {refundable_remaining}.",
                http_status=400,
                details={"refundable_remaining": refundable_remaining},
            )

        stripe_refund = await self.stripe.create_refund(
            payment_intent_id=payment_intent_id,
            amount=amount,
            idempotency_key=idempotency_key,
            reason=body.reason,
            metadata={
                "order_id": order_id,
                "order_number": existing.get("order_number", ""),
                "admin_id": admin["admin_id"],
                "note": (body.note or "")[:400],
            },
        )

        new_status = (
            "refunded" if amount + already_refunded >= total else "partially_refunded"
        )
        # An admin choosing to fully refund a non-shipped order doesn't
        # restock automatically — admin can adjust stock via PATCH variant
        # if they want. Documented in code so behaviour is explicit.

        now = _now()
        refund_doc = {
            "refund_id": _refund_id(),
            "provider_refund_id": stripe_refund.get("id", ""),
            "amount": amount,
            "reason": body.reason,
            "status": stripe_refund.get("status", "pending"),
            "created_at": now,
        }
        updated = await self.repo.push_refund(
            order_id, refund_doc=refund_doc, new_status=new_status, now=now
        )
        assert updated is not None

        await self._audit(
            admin,
            action="order.refund_issued",
            target_id=order_id,
            before={"status": existing["status"], "already_refunded": already_refunded},
            after={
                "status": new_status,
                "refund_amount": amount,
                "stripe_refund_id": stripe_refund.get("id"),
            },
        )
        log.info(
            "admin.order_refund_issued",
            order_id=order_id,
            amount=amount,
            new_status=new_status,
            stripe_refund_id=stripe_refund.get("id"),
        )
        return refund_doc, updated

    async def receive_return(
        self,
        order_id: str,
        *,
        admin: dict[str, Any],
        refund_amount: int | None,
        refund_reason: str | None,
        restock: bool,
        note: str | None,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Mark a return as received.

        - Transitions ``return_requested`` → ``returned`` (or
          ``refunded`` / ``partially_refunded`` when ``refund_amount`` is set).
        - If ``restock`` is True, increments ``stock_on_hand`` for every
          variant on the lines in ``return_request.line_ids`` (or every line
          on the order when the list is empty) and records inventory
          movements.
        - If ``refund_amount`` is provided, issues a Stripe refund.
        - Stamps ``return_request.received_at`` / ``status=received`` and
          optionally the ``refund_id``.
        """
        existing = await self.get_order(order_id)
        if existing["status"] not in {"return_requested", "shipped", "delivered"}:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"Can't receive a return at status '{existing['status']}'.",
                http_status=409,
                details={"status": existing["status"]},
            )

        now = _now()
        return_request = dict(existing.get("return_request") or {})
        if not return_request:
            # Customer never opened a return formally — record an admin-
            # initiated one for the audit trail.
            return_request = {
                "reason": note or "Admin-initiated return processing.",
                "line_ids": [],
                "requested_at": now,
                "status": "pending",
                "note": None,
                "received_at": None,
                "refund_id": None,
            }

        # ── 1. Restock (variant-by-variant; records inventory_movements) ──
        restocked_variants: list[str] = []
        if restock:
            chosen_line_ids = set(return_request.get("line_ids") or [])
            lines_to_restock = [
                lin
                for lin in existing.get("lines", [])
                if not chosen_line_ids or lin["line_id"] in chosen_line_ids
            ]
            for lin in lines_to_restock:
                variant_doc = await self.db[C.variants].find_one(
                    {"variant_id": lin["variant_id"]}
                )
                if not variant_doc:
                    continue
                qty = int(lin.get("quantity", 0))
                if qty <= 0:
                    continue
                prev_stock = int(
                    (variant_doc.get("inventory") or {}).get("stock_on_hand", 0)
                )
                new_stock = prev_stock + qty
                await self.db[C.variants].update_one(
                    {"variant_id": lin["variant_id"]},
                    {
                        "$set": {
                            "inventory.stock_on_hand": new_stock,
                            "updated_at": now,
                        }
                    },
                )
                from app.modules.inventory.movements import record_movement

                await record_movement(
                    self.db,
                    variant_id=lin["variant_id"],
                    product_id=lin.get("product_id"),
                    delta=qty,
                    quantity_after=new_stock,
                    reason="refund_restock",
                    source_type="admin",
                    source_id=order_id,
                    actor_id=admin["admin_id"],
                    note=f"Return for {existing['order_number']}",
                )
                restocked_variants.append(lin["variant_id"])

        # ── 2. Refund if amount provided ──
        refund_doc_id: str | None = None
        new_status_after_refund: str | None = None
        if refund_amount and refund_amount > 0:
            payment = existing.get("payment") or {}
            payment_intent_id = payment.get("stripe_payment_intent_id")
            if not payment_intent_id:
                raise ApiError(
                    ErrorCode.CONFLICT,
                    "Order has no payment intent on record.",
                    http_status=409,
                )
            total = int(existing["totals"]["total_amount"])
            already_refunded = sum(
                int(r.get("amount", 0)) for r in existing.get("refunds", [])
            )
            remaining = total - already_refunded
            if refund_amount > remaining:
                raise ApiError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Refund amount exceeds refundable remaining ({remaining}).",
                    http_status=400,
                )
            stripe_refund = await self.stripe.create_refund(
                payment_intent_id=payment_intent_id,
                amount=refund_amount,
                idempotency_key=idempotency_key or f"return_{order_id}_{now.isoformat()}",
                reason=refund_reason or "requested_by_customer",
                metadata={
                    "order_id": order_id,
                    "order_number": existing.get("order_number", ""),
                    "admin_id": admin["admin_id"],
                    "trigger": "return_received",
                },
            )
            refund_doc = {
                "refund_id": _refund_id(),
                "provider_refund_id": stripe_refund.get("id", ""),
                "amount": refund_amount,
                "reason": refund_reason or "requested_by_customer",
                "status": stripe_refund.get("status", "pending"),
                "created_at": now,
            }
            refund_doc_id = refund_doc["refund_id"]
            new_status_after_refund = (
                "refunded"
                if refund_amount + already_refunded >= total
                else "partially_refunded"
            )
            await self.repo.push_refund(
                order_id,
                refund_doc=refund_doc,
                new_status=new_status_after_refund,
                now=now,
            )

        # ── 3. Stamp return_request as received and final status ──
        return_request["status"] = "received"
        return_request["received_at"] = now
        if note:
            return_request["note"] = note
        if refund_doc_id:
            return_request["refund_id"] = refund_doc_id

        final_status = new_status_after_refund or "returned"
        updated = await self.repo.update_fields(
            order_id,
            {
                "return_request": return_request,
                "status": final_status,
                "updated_at": now,
            },
        )
        assert updated is not None

        # Return processed → order closed. Start the try-on purge clock.
        from app.modules.orders.tryon_retention import set_order_tryon_expiry

        try:
            await set_order_tryon_expiry(self.db, order_id, closed_at=now)
        except Exception:
            log.exception("admin.order_tryon_expiry_failed", order_id=order_id)

        await self._audit(
            admin,
            action="order.return_received",
            target_id=order_id,
            before={"status": existing["status"]},
            after={
                "status": final_status,
                "restocked_variants": restocked_variants,
                "refund_amount": refund_amount or 0,
                "refund_id": refund_doc_id,
            },
        )
        log.info(
            "admin.order_return_received",
            order_id=order_id,
            restocked=len(restocked_variants),
            refund_amount=refund_amount or 0,
            final_status=final_status,
        )
        return updated

    # ── Support notes ──────────────────────────────────────────
    async def add_support_note(
        self,
        order_id: str,
        body: SupportNoteCreateRequest,
        admin: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        existing = await self.get_order(order_id)
        now = _now()
        note_doc = {
            "note": body.note,
            "actor_id": admin["admin_id"],
            "created_at": now,
        }
        updated = await self.repo.push_support_note(
            order_id, note_doc=note_doc, now=now
        )
        assert updated is not None
        await self._audit(
            admin,
            action="order.support_note_added",
            target_id=order_id,
            after={"note_length": len(body.note)},
        )
        log.info(
            "admin.order_support_note_added",
            order_id=order_id,
            order_number=existing.get("order_number"),
        )
        return note_doc, updated

    # ── Audit helper ───────────────────────────────────────────
    async def _audit(
        self,
        admin: dict[str, Any],
        *,
        action: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        meta = admin.get("_request_meta", {})
        await self.admin_repo.write_audit(
            actor_id=admin["admin_id"],
            action=action,
            target_type="order",
            target_id=target_id,
            before=before,
            after=after,
            ip_address=meta.get("ip"),
            user_agent=meta.get("ua"),
        )
