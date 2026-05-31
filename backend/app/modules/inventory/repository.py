"""Inventory data access — atomic holds and stock mutations.

Hold creation uses a single MongoDB ``find_one_and_update`` with a conditional
``$expr`` so concurrent attempts for the last unit can't both succeed. The
losing request gets ``None`` back; we raise ``OUT_OF_STOCK``.

Stock state lives in two places:
- ``variants.inventory.stock_on_hand`` (decrements on payment per REQ-038)
- ``variants.inventory.held_units`` (denormalised count of active holds —
  lets ``available_for_sale`` be computed from one document)

The ``inventory_holds`` collection is the source of truth for which holds
exist. ``held_units`` is a cached sum maintained transactionally inside this
module; the worker can re-derive it from holds during reconciliation.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.inventory.schemas import Availability, InventoryHold

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _hold_id() -> str:
    return f"hold_{secrets.token_hex(8)}"


def _to_hold(doc: dict[str, Any]) -> InventoryHold:
    return InventoryHold(**{k: v for k, v in doc.items() if k != "_id"})


class InventoryRepository:
    """All inventory DB access lives here."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.variants = db[C.variants]
        self.holds = db[C.inventory_holds]

    # ── Availability ───────────────────────────────────────────
    async def get_availability(self, variant_id: str) -> Availability | None:
        doc = await self.variants.find_one(
            {"variant_id": variant_id, "deleted_at": None}
        )
        if not doc:
            return None
        return Availability.from_variant_doc(doc)

    async def get_availabilities(
        self, variant_ids: list[str]
    ) -> dict[str, Availability]:
        if not variant_ids:
            return {}
        cursor = self.variants.find(
            {"variant_id": {"$in": variant_ids}, "deleted_at": None}
        )
        result: dict[str, Availability] = {}
        async for doc in cursor:
            result[doc["variant_id"]] = Availability.from_variant_doc(doc)
        return result

    # ── Hold lifecycle ─────────────────────────────────────────
    async def create_hold(
        self,
        *,
        variant_id: str,
        quantity: int,
        checkout_session_id: str,
        ttl_minutes: int,
        cart_id: str | None = None,
        guest_cart_id: str | None = None,
        customer_id: str | None = None,
    ) -> InventoryHold:
        """Reserve ``quantity`` units of ``variant_id`` for a checkout session.

        Atomic: a single ``find_one_and_update`` checks stock and increments
        ``held_units`` in one operation. Two concurrent requests for the last
        unit can't both succeed (REQ-040).
        """
        if quantity < 1:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Hold quantity must be at least 1.",
            )

        now = _now()
        expires_at = now + timedelta(minutes=ttl_minutes)

        # 1. Atomic stock check + held_units increment.
        variant = await self.variants.find_one_and_update(
            filter={
                "variant_id": variant_id,
                "status": "active",
                "deleted_at": None,
                "$expr": {
                    "$gte": [
                        {
                            "$subtract": [
                                {"$ifNull": ["$inventory.stock_on_hand", 0]},
                                {"$ifNull": ["$inventory.held_units", 0]},
                            ]
                        },
                        quantity,
                    ]
                },
            },
            update={"$inc": {"inventory.held_units": quantity}},
            return_document=ReturnDocument.AFTER,
        )
        if variant is None:
            # Either the variant doesn't exist/is inactive, or not enough stock.
            existing = await self.variants.find_one(
                {"variant_id": variant_id, "deleted_at": None}
            )
            if existing is None:
                raise ApiError(
                    ErrorCode.NOT_FOUND,
                    f"Variant not found: {variant_id}",
                    http_status=404,
                )
            raise ApiError(
                ErrorCode.OUT_OF_STOCK,
                "This item just sold out.",
                http_status=409,
                details={"variant_id": variant_id, "requested": quantity},
            )

        # 2. Insert the hold doc. If this fails, compensate by reversing the
        # held_units increment so we don't leak stock.
        hold_doc: dict[str, Any] = {
            "hold_id": _hold_id(),
            "cart_id": cart_id,
            "checkout_session_id": checkout_session_id,
            "customer_id": customer_id,
            "guest_cart_id": guest_cart_id,
            "variant_id": variant_id,
            "product_id": variant["product_id"],
            "quantity": quantity,
            "status": "active",
            "expires_at": expires_at,
            "committed_at": None,
            "released_at": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self.holds.insert_one(hold_doc)
        except Exception:
            # Roll back the held_units bump so we don't strand stock.
            await self.variants.update_one(
                {"variant_id": variant_id},
                {"$inc": {"inventory.held_units": -quantity}},
            )
            raise

        log.info(
            "inventory.hold_created",
            hold_id=hold_doc["hold_id"],
            variant_id=variant_id,
            quantity=quantity,
            checkout_session_id=checkout_session_id,
            expires_at=expires_at.isoformat(),
        )
        return _to_hold(hold_doc)

    async def release_hold(self, hold_id: str, *, reason: str = "released") -> bool:
        """Mark an active hold as released/expired; decrement ``held_units``.

        Returns ``True`` if the hold was active and is now released, ``False``
        if it was already non-active (idempotent — safe to call twice).
        """
        now = _now()
        terminal_status = "expired" if reason == "expired" else "released"
        result = await self.holds.find_one_and_update(
            filter={"hold_id": hold_id, "status": "active"},
            update={
                "$set": {
                    "status": terminal_status,
                    "released_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.BEFORE,
        )
        if result is None:
            return False

        # Decrement the denormalised counter on the variant.
        await self.variants.update_one(
            {"variant_id": result["variant_id"]},
            {"$inc": {"inventory.held_units": -int(result["quantity"])}},
        )
        log.info(
            "inventory.hold_released",
            hold_id=hold_id,
            variant_id=result["variant_id"],
            quantity=result["quantity"],
            reason=reason,
        )
        return True

    async def commit_hold(self, hold_id: str) -> bool:
        """Convert an active hold into a stock decrement.

        Called by the payment webhook handler after successful payment.
        Atomically:
        - Marks the hold ``committed``.
        - Decrements ``held_units`` (the hold is no longer "in flight").
        - Decrements ``stock_on_hand`` by the held quantity (REQ-038).

        Returns ``True`` if committed, ``False`` if the hold wasn't active
        (already committed/released/expired).
        """
        now = _now()
        hold = await self.holds.find_one_and_update(
            filter={"hold_id": hold_id, "status": "active"},
            update={
                "$set": {
                    "status": "committed",
                    "committed_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.BEFORE,
        )
        if hold is None:
            return False

        qty = int(hold["quantity"])
        updated_variant = await self.variants.find_one_and_update(
            {"variant_id": hold["variant_id"]},
            {
                "$inc": {
                    "inventory.held_units": -qty,
                    "inventory.stock_on_hand": -qty,
                }
            },
            return_document=ReturnDocument.AFTER,
            projection={
                "variant_id": 1,
                "product_id": 1,
                "inventory.stock_on_hand": 1,
            },
        )

        # Record the movement so the ledger shows "order X consumed N units".
        # Imported lazily to avoid a cycle with the inventory service.
        if updated_variant is not None:
            from app.modules.inventory.movements import record_movement

            await record_movement(
                self.db,
                variant_id=hold["variant_id"],
                product_id=updated_variant.get("product_id"),
                delta=-qty,
                quantity_after=int(
                    (updated_variant.get("inventory") or {}).get("stock_on_hand", 0)
                ),
                reason="payment_decrement",
                source_type="checkout",
                source_id=hold.get("checkout_session_id"),
            )

        log.info(
            "inventory.hold_committed",
            hold_id=hold_id,
            variant_id=hold["variant_id"],
            quantity=qty,
        )
        return True

    async def find_active_for_checkout(
        self, checkout_session_id: str
    ) -> list[InventoryHold]:
        cursor = self.holds.find(
            {"checkout_session_id": checkout_session_id, "status": "active"}
        )
        return [_to_hold(doc) async for doc in cursor]

    # ── Expiry sweep (used by the worker cron) ─────────────────
    async def find_expired_hold_ids(self, *, limit: int = 500) -> list[str]:
        cursor = self.holds.find(
            {"status": "active", "expires_at": {"$lte": _now()}},
            projection={"hold_id": 1, "_id": 0},
        ).limit(limit)
        return [doc["hold_id"] async for doc in cursor]
