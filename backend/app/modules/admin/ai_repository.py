"""Admin AI data access — settings keys, ai_jobs reads, analytics aggregations.

The ``settings`` collection stores one document per key (DATA_MODEL §10.3).
Resolved values fall back to environment defaults when no row exists so the
worker has sensible defaults from day one — admin only needs to set what
they want to override.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.db import C


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Mapping from admin-API key → settings collection key.
SETTINGS_KEY_MAP = {
    "kill_switch_enabled": "ai.kill_switch",
    "daily_spend_ceiling_amount": "ai.daily_spend_ceiling_amount",
    "anonymous_daily_limit": "ai.anonymous_daily_limit",
    "registered_weekly_limit": "ai.registered_weekly_limit",
}


class AiSettingsRepository:
    """Read/write the AI runtime-tunable settings."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings_coll = db[C.settings]

    async def _read(self, key: str) -> Any | None:
        doc = await self.settings_coll.find_one({"key": key})
        return doc["value"] if doc and "value" in doc else None

    async def get_resolved(self) -> dict[str, Any]:
        """Resolve all four AI settings — DB value where set, env default otherwise."""
        env: Settings = get_settings()

        kill = await self._read("ai.kill_switch")
        ceiling = await self._read("ai.daily_spend_ceiling_amount")
        anon_limit = await self._read("ai.anonymous_daily_limit")
        reg_limit = await self._read("ai.registered_weekly_limit")

        return {
            "kill_switch_enabled": bool(kill) if kill is not None else env.ai_kill_switch,
            "daily_spend_ceiling_amount": (
                int(ceiling)
                if ceiling is not None
                else int(env.ai_daily_spend_ceiling_usd * 100)
            ),
            "anonymous_daily_limit": (
                int(anon_limit)
                if anon_limit is not None
                else env.ai_anonymous_daily_limit
            ),
            "registered_weekly_limit": (
                int(reg_limit)
                if reg_limit is not None
                else env.ai_registered_weekly_limit
            ),
            "currency": env.store_currency,
        }

    async def set_value(self, key: str, value: Any, admin_id: str) -> None:
        await self.settings_coll.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "value": value,
                    "updated_by_admin_id": admin_id,
                    "updated_at": _now(),
                }
            },
            upsert=True,
        )


class AiJobsRepository:
    """Read-only access to ai_jobs for the admin UI."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.ai_jobs = db[C.ai_jobs]

    async def list(
        self,
        *,
        status: str | None = None,
        customer_id: str | None = None,
        anonymous_session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if customer_id:
            query["customer_id"] = customer_id
        if anonymous_session_id:
            query["anonymous_session_id"] = anonymous_session_id
        cursor = (
            self.ai_jobs.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await self.ai_jobs.count_documents(query)
        return items, total

    async def find_by_id(self, job_id: str) -> dict[str, Any] | None:
        return await self.ai_jobs.find_one({"job_id": job_id})


class AnalyticsRepository:
    """Pre-canned aggregations for the admin dashboard."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.orders = db[C.orders]
        self.variants = db[C.variants]
        self.ai_jobs = db[C.ai_jobs]

    # ── Overview ───────────────────────────────────────────────
    async def revenue_and_orders(
        self,
        completed_statuses: list[str],
        *,
        today_start: datetime,
        seven_days_ago: datetime,
    ) -> dict[str, Any]:
        pipeline = [
            {"$facet": {
                "revenue": [
                    {"$match": {"status": {"$in": completed_statuses}}},
                    {"$group": {
                        "_id": None,
                        "amount": {"$sum": "$totals.total_amount"},
                        "currency": {"$first": "$totals.currency"},
                    }},
                ],
                "total_orders": [
                    {"$count": "n"},
                ],
                "orders_today": [
                    {"$match": {"created_at": {"$gte": today_start}}},
                    {"$count": "n"},
                ],
                "orders_7d": [
                    {"$match": {"created_at": {"$gte": seven_days_ago}}},
                    {"$count": "n"},
                ],
            }},
        ]
        result = await self.orders.aggregate(pipeline).to_list(1)
        bucket = result[0] if result else {}
        rev = (bucket.get("revenue") or [{}])[0]
        return {
            "revenue_amount": int(rev.get("amount", 0) or 0),
            "revenue_currency": rev.get("currency") or "USD",
            "orders_total": int((bucket.get("total_orders") or [{}])[0].get("n", 0)),
            "orders_today": int((bucket.get("orders_today") or [{}])[0].get("n", 0)),
            "orders_7d": int((bucket.get("orders_7d") or [{}])[0].get("n", 0)),
        }

    async def top_products(
        self, completed_statuses: list[str], *, limit: int = 5
    ) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"status": {"$in": completed_statuses}}},
            {"$unwind": "$lines"},
            {"$group": {
                "_id": "$lines.product_id",
                "title": {"$first": "$lines.title_snapshot"},
                "quantity_sold": {"$sum": "$lines.quantity"},
                "revenue_amount": {"$sum": "$lines.line_total_amount"},
            }},
            {"$sort": {"quantity_sold": -1}},
            {"$limit": limit},
        ]
        rows = await self.orders.aggregate(pipeline).to_list(limit)
        return [
            {
                "product_id": r["_id"],
                "title": r.get("title") or "",
                "quantity_sold": int(r.get("quantity_sold", 0)),
                "revenue_amount": int(r.get("revenue_amount", 0)),
            }
            for r in rows
            if r.get("_id")
        ]

    async def low_stock_variants(self, *, limit: int = 20) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {
                "status": "active",
                "deleted_at": None,
                "inventory.track_inventory": True,
            }},
            {"$addFields": {
                "available_for_sale": {
                    "$max": [
                        0,
                        {"$subtract": [
                            {"$ifNull": ["$inventory.stock_on_hand", 0]},
                            {"$ifNull": ["$inventory.held_units", 0]},
                        ]},
                    ]
                },
                "threshold": {"$ifNull": ["$inventory.low_stock_threshold", 5]},
            }},
            {"$match": {
                "$expr": {"$lte": ["$available_for_sale", "$threshold"]}
            }},
            {"$sort": {"available_for_sale": 1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "variant_id": 1,
                "product_id": 1,
                "sku": 1,
                "size": 1,
                "color": 1,
                "available_for_sale": 1,
                "low_stock_threshold": "$threshold",
            }},
        ]
        return await self.variants.aggregate(pipeline).to_list(limit)

    # ── AI analytics ───────────────────────────────────────────
    async def ai_today_spend(self, today_start: datetime) -> int:
        pipeline = [
            {"$match": {"created_at": {"$gte": today_start}}},
            {"$group": {
                "_id": None,
                "spend": {"$sum": "$cost.estimated_total_amount"},
            }},
        ]
        rows = await self.ai_jobs.aggregate(pipeline).to_list(1)
        return int((rows[0].get("spend") if rows else 0) or 0)

    async def ai_status_counts(self, since: datetime) -> dict[str, int]:
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]
        rows = await self.ai_jobs.aggregate(pipeline).to_list(None)
        return {r["_id"]: int(r["n"]) for r in rows if r.get("_id")}

    async def ai_recent_failed(self, *, limit: int = 10) -> list[dict[str, Any]]:
        cursor = (
            self.ai_jobs.find(
                {"status": {"$in": ["failed", "expired", "cancelled"]}}
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(limit)
