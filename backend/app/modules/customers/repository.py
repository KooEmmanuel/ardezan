"""Customer DB access — read/write the ``customers`` collection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.customers = db[C.customers]

    # ── Reads ──────────────────────────────────────────────────
    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        return await self.customers.find_one(
            {"email": email.lower().strip(), "deleted_at": None}
        )

    async def find_by_id(self, customer_id: str) -> dict[str, Any] | None:
        return await self.customers.find_one(
            {"customer_id": customer_id, "deleted_at": None}
        )

    # ── Writes ─────────────────────────────────────────────────
    async def insert(self, doc: dict[str, Any]) -> None:
        await self.customers.insert_one(doc)

    async def update_last_login(self, customer_id: str) -> None:
        await self.customers.update_one(
            {"customer_id": customer_id},
            {"$set": {"last_login_at": _now(), "updated_at": _now()}},
        )

    async def update_password_hash(self, customer_id: str, new_hash: str) -> None:
        await self.customers.update_one(
            {"customer_id": customer_id},
            {"$set": {"password_hash": new_hash, "updated_at": _now()}},
        )

    # ── Email verification (M6.4) ──────────────────────────────
    async def mark_email_verified(self, customer_id: str) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        now = _now()
        return await self.customers.find_one_and_update(
            {"customer_id": customer_id, "email_verified_at": None},
            {"$set": {"email_verified_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )

    # ── Password reset (M6.4) ──────────────────────────────────
    async def set_password_reset(
        self, customer_id: str, *, token_hash: str, expires_at: datetime
    ) -> None:
        """Record the hash + expiry of the latest reset token. Overwrites
        any previous unconsumed token — only one reset link is ever live."""
        await self.customers.update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "password_reset": {
                        "token_hash": token_hash,
                        "expires_at": expires_at,
                    },
                    "updated_at": _now(),
                }
            },
        )

    async def consume_password_reset(
        self, customer_id: str, *, new_hash: str
    ) -> None:
        """Atomically clear the reset token and update the password hash."""
        await self.customers.update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "password_hash": new_hash,
                    "password_reset": {"token_hash": None, "expires_at": None},
                    "updated_at": _now(),
                }
            },
        )

    async def update_profile(
        self, customer_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        fields["updated_at"] = _now()
        return await self.customers.find_one_and_update(
            {"customer_id": customer_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
