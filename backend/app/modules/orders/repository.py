"""Order data access — read paths and order number allocation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db import C


class OrdersRepository:
    """All order DB access lives here."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.orders = db[C.orders]
        self.settings = db[C.settings]

    # ── Reads ──────────────────────────────────────────────────
    async def find_by_id(self, order_id: str) -> dict[str, Any] | None:
        return await self.orders.find_one({"order_id": order_id})

    async def find_by_checkout_session(
        self, checkout_session_id: str
    ) -> dict[str, Any] | None:
        return await self.orders.find_one(
            {"checkout_session_id": checkout_session_id}
        )

    async def find_by_payment_intent(
        self, stripe_payment_intent_id: str
    ) -> dict[str, Any] | None:
        return await self.orders.find_one(
            {"payment.stripe_payment_intent_id": stripe_payment_intent_id}
        )

    # ── Customer-facing reads ──────────────────────────────────
    async def list_for_customer(
        self,
        customer_id: str,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Customer's own order history, newest first."""
        query = {"customer_id": customer_id}
        cursor = (
            self.orders.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await self.orders.count_documents(query)
        return items, total

    # ── Writes ─────────────────────────────────────────────────
    async def insert(self, doc: dict[str, Any]) -> None:
        """Insert an order document. Relies on the unique index on
        ``checkout_session_id`` to catch concurrent webhook duplicates."""
        await self.orders.insert_one(doc)

    async def update_status(
        self, order_id: str, *, status: str, now: datetime
    ) -> None:
        await self.orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": status, "updated_at": now}},
        )

    async def update_fields(
        self, order_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.orders.find_one_and_update(
            {"order_id": order_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    async def push_refund(
        self,
        order_id: str,
        *,
        refund_doc: dict[str, Any],
        new_status: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.orders.find_one_and_update(
            {"order_id": order_id},
            {
                "$push": {"refunds": refund_doc},
                "$set": {"status": new_status, "updated_at": now},
            },
            return_document=ReturnDocument.AFTER,
        )

    # ── Order number allocation (atomic counter via settings) ──
    async def next_order_number(self) -> str:
        """Atomically increment the counter and return the next order number.

        Uses ``find_one_and_update`` with ``upsert=True`` so the first call
        creates the counter doc. We add a 1041 offset so the first order is
        ``#1042`` (matches the prototype). ``$inc`` from a missing field
        starts at 0 + 1 = 1, so::

            first call  → counter doc {value: 1} → returns "#1042"
            second call → counter doc {value: 2} → returns "#1043"
        """
        result = await self.settings.find_one_and_update(
            {"key": "order_number_counter"},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        counter = int(result["value"])
        return f"#{1041 + counter}"
