"""Server-side cart DB access (carts collection, DATA_MODEL §7.1)."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.db import C


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cart_id() -> str:
    return f"cart_{secrets.token_hex(8)}"


def _line_id() -> str:
    return f"line_{secrets.token_hex(6)}"


class CartRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.carts = db[C.carts]

    # ── Reads ──────────────────────────────────────────────────
    async def find_active_for_customer(
        self, customer_id: str
    ) -> dict[str, Any] | None:
        return await self.carts.find_one(
            {"customer_id": customer_id, "status": "active"}
        )

    async def find_by_id(self, cart_id: str) -> dict[str, Any] | None:
        return await self.carts.find_one({"cart_id": cart_id})

    # ── Writes ─────────────────────────────────────────────────
    async def create_for_customer(self, customer_id: str) -> dict[str, Any]:
        now = _now()
        cart_id = _cart_id()
        doc = {
            "cart_id": cart_id,
            "customer_id": customer_id,
            "status": "active",
            "lines": [],
            "last_validated_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.carts.insert_one(doc)
        return doc

    async def push_line(
        self, cart_id: str, line_doc: dict[str, Any]
    ) -> dict[str, Any] | None:
        return await self.carts.find_one_and_update(
            {"cart_id": cart_id},
            {"$push": {"lines": line_doc}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def update_line_quantity(
        self, cart_id: str, line_id: str, *, quantity: int
    ) -> dict[str, Any] | None:
        return await self.carts.find_one_and_update(
            {"cart_id": cart_id, "lines.line_id": line_id},
            {
                "$set": {
                    "lines.$.quantity": quantity,
                    "updated_at": _now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def remove_line(
        self, cart_id: str, line_id: str
    ) -> dict[str, Any] | None:
        return await self.carts.find_one_and_update(
            {"cart_id": cart_id},
            {"$pull": {"lines": {"line_id": line_id}}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )


def new_line_id() -> str:
    """Exposed so the service can mint line ids before pushing."""
    return _line_id()
