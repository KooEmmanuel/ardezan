"""Admin order data access — list/filter, partial updates, list-field appends."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


class AdminOrdersRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.orders = db[C.orders]

    # ── Reads ──────────────────────────────────────────────────
    async def find_by_id(self, order_id: str) -> dict[str, Any] | None:
        return await self.orders.find_one({"order_id": order_id})

    async def list(
        self,
        *,
        status: str | None = None,
        customer_id: str | None = None,
        guest_email: str | None = None,
        order_number: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        has_custom_design: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if customer_id:
            query["customer_id"] = customer_id
        if guest_email:
            query["guest_email"] = guest_email.lower()
        if order_number:
            query["order_number"] = order_number
        if created_after or created_before:
            range_q: dict[str, Any] = {}
            if created_after:
                range_q["$gte"] = created_after
            if created_before:
                range_q["$lte"] = created_before
            query["created_at"] = range_q
        if has_custom_design is True:
            query["lines.kind"] = "custom_design"
        elif has_custom_design is False:
            query["lines.kind"] = {"$ne": "custom_design"}

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

    async def push_support_note(
        self,
        order_id: str,
        *,
        note_doc: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.orders.find_one_and_update(
            {"order_id": order_id},
            {
                "$push": {"support_notes": note_doc},
                "$set": {"updated_at": now},
            },
            return_document=ReturnDocument.AFTER,
        )
