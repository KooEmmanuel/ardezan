"""Admin user data access — admin_users + audit_logs."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit_log_id() -> str:
    return f"audit_{secrets.token_hex(8)}"


class AdminRepository:
    """Read/write paths for admin accounts and the audit log."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.admins = db[C.admin_users]
        self.audit_logs = db[C.audit_logs]

    # ── Admins ─────────────────────────────────────────────────
    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        return await self.admins.find_one(
            {"email": email.lower(), "deleted_at": None}
        )

    async def find_by_id(self, admin_id: str) -> dict[str, Any] | None:
        return await self.admins.find_one(
            {"admin_id": admin_id, "deleted_at": None}
        )

    async def update_last_login(self, admin_id: str) -> None:
        await self.admins.update_one(
            {"admin_id": admin_id},
            {"$set": {"last_login_at": _now(), "updated_at": _now()}},
        )

    async def insert(self, doc: dict[str, Any]) -> None:
        await self.admins.insert_one(doc)

    # ── Audit log reads ────────────────────────────────────────
    async def list_audit_logs(
        self,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if actor_type:
            query["actor_type"] = actor_type
        if actor_id:
            query["actor_id"] = actor_id
        if action:
            query["action"] = action
        if target_type:
            query["target_type"] = target_type
        if target_id:
            query["target_id"] = target_id
        if created_after or created_before:
            range_q: dict[str, Any] = {}
            if created_after:
                range_q["$gte"] = created_after
            if created_before:
                range_q["$lte"] = created_before
            query["created_at"] = range_q

        cursor = (
            self.audit_logs.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await self.audit_logs.count_documents(query)
        return items, total

    async def distinct_audit_actions(self) -> list[str]:
        actions = await self.audit_logs.distinct("action")
        return sorted(str(a) for a in actions if a)

    async def distinct_audit_target_types(self) -> list[str]:
        types = await self.audit_logs.distinct("target_type")
        return sorted(str(t) for t in types if t)

    # ── Audit logs ─────────────────────────────────────────────
    async def write_audit(
        self,
        *,
        actor_id: str | None,
        action: str,
        target_type: str | None = None,
        target_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Append-only audit entry. Never updated, never deleted."""
        await self.audit_logs.insert_one(
            {
                "audit_log_id": _audit_log_id(),
                "actor_type": "admin" if actor_id else "system",
                "actor_id": actor_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "before_summary": before,
                "after_summary": after,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": _now(),
            }
        )
