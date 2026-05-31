"""Checkout session persistence.

The ``checkout_sessions`` collection is the source of truth for in-flight
checkouts. The webhook handler reads from this collection to drive order
creation after payment succeeds.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


class CheckoutRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.sessions = db[C.checkout_sessions]

    async def find_by_id(self, checkout_session_id: str) -> dict[str, Any] | None:
        return await self.sessions.find_one(
            {"checkout_session_id": checkout_session_id}
        )

    async def find_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None:
        return await self.sessions.find_one({"idempotency_key": idempotency_key})

    async def insert(self, doc: dict[str, Any]) -> None:
        await self.sessions.insert_one(doc)

    async def update_status(
        self,
        checkout_session_id: str,
        *,
        status: str,
        now: datetime,
    ) -> None:
        await self.sessions.update_one(
            {"checkout_session_id": checkout_session_id},
            {"$set": {"status": status, "updated_at": now}},
        )

    async def set_payment_intent(
        self,
        checkout_session_id: str,
        *,
        payment_intent_id: str,
        now: datetime,
    ) -> None:
        await self.sessions.update_one(
            {"checkout_session_id": checkout_session_id},
            {
                "$set": {
                    "stripe_payment_intent_id": payment_intent_id,
                    "updated_at": now,
                }
            },
        )
