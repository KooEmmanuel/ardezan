"""Admin DB access for products, variants, and size charts.

Mutations go through this layer so audit logging in the service layer always
captures the exact ``before`` state in one place.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


class AdminProductsRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.products = db[C.products]
        self.variants = db[C.variants]
        self.size_charts = db[C.size_charts]

    # ── Products ───────────────────────────────────────────────
    async def find_product(self, product_id: str) -> dict[str, Any] | None:
        return await self.products.find_one({"product_id": product_id})

    async def find_product_by_slug(self, slug: str) -> dict[str, Any] | None:
        return await self.products.find_one({"slug": slug})

    def _list_query(
        self,
        *,
        status: str | None,
        category: str | None,
        include_deleted: bool,
        q: str | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if not include_deleted:
            query["deleted_at"] = None
        if status:
            query["status"] = status
        if category:
            query["category"] = category
        if q:
            # Case-insensitive contains over title + slug + tags.
            query["$or"] = [
                {"title": {"$regex": re.escape(q), "$options": "i"}},
                {"slug": {"$regex": re.escape(q), "$options": "i"}},
                {"tags": {"$regex": re.escape(q), "$options": "i"}},
            ]
        return query

    async def list_products(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        include_deleted: bool = False,
        q: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        query = self._list_query(
            status=status, category=category, include_deleted=include_deleted, q=q
        )
        if cursor:
            query["product_id"] = {"$gt": cursor}
        cursor_q = self.products.find(query).sort("product_id", 1).limit(limit)
        return await cursor_q.to_list(limit)

    async def distinct_categories(self) -> list[str]:
        cats = await self.products.distinct(
            "category", {"deleted_at": None}
        )
        return sorted([c for c in cats if c])

    async def count_products(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        include_deleted: bool = False,
        q: str | None = None,
    ) -> int:
        query = self._list_query(
            status=status, category=category, include_deleted=include_deleted, q=q
        )
        return await self.products.count_documents(query)

    async def aggregate_variant_stats(
        self, product_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """For each product_id, return variant_count, stock_on_hand_total,
        low_stock_variant_count, out_of_stock_variant_count, price_min, price_max.

        Single $group aggregation — one round-trip regardless of list size.
        Variants with ``deleted_at`` set are excluded.
        """
        if not product_ids:
            return {}
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "product_id": {"$in": product_ids},
                    "deleted_at": None,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "product_id": 1,
                    "stock_on_hand": {
                        "$ifNull": ["$inventory.stock_on_hand", 0]
                    },
                    "low_stock_threshold": {
                        "$ifNull": ["$inventory.low_stock_threshold", 5]
                    },
                    "track_inventory": {
                        "$ifNull": ["$inventory.track_inventory", True]
                    },
                    "price_amount": "$pricing.price_amount",
                }
            },
            {
                "$group": {
                    "_id": "$product_id",
                    "variant_count": {"$sum": 1},
                    "stock_on_hand_total": {"$sum": "$stock_on_hand"},
                    "low_stock_variant_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$track_inventory", True]},
                                        {"$gt": ["$stock_on_hand", 0]},
                                        {
                                            "$lte": [
                                                "$stock_on_hand",
                                                "$low_stock_threshold",
                                            ]
                                        },
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "out_of_stock_variant_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$track_inventory", True]},
                                        {"$eq": ["$stock_on_hand", 0]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "price_min": {"$min": "$price_amount"},
                    "price_max": {"$max": "$price_amount"},
                }
            },
        ]
        out: dict[str, dict[str, Any]] = {}
        async for doc in self.variants.aggregate(pipeline):
            pid = doc.pop("_id")
            out[pid] = doc
        return out

    async def insert_product(self, doc: dict[str, Any]) -> None:
        await self.products.insert_one(doc)

    async def update_product(
        self, product_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.products.find_one_and_update(
            {"product_id": product_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    async def soft_delete_product(self, product_id: str, now: datetime) -> bool:
        result = await self.products.update_one(
            {"product_id": product_id, "deleted_at": None},
            {"$set": {"deleted_at": now, "status": "archived", "updated_at": now}},
        )
        return result.matched_count > 0

    # ── Variants ───────────────────────────────────────────────
    async def find_variant(self, variant_id: str) -> dict[str, Any] | None:
        return await self.variants.find_one({"variant_id": variant_id})

    async def find_variant_by_sku(self, sku: str) -> dict[str, Any] | None:
        return await self.variants.find_one({"sku": sku})

    async def list_variants_for_product(
        self, product_id: str, *, include_deleted: bool = False
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"product_id": product_id}
        if not include_deleted:
            query["deleted_at"] = None
        cursor = self.variants.find(query).sort("size", 1)
        return await cursor.to_list(None)

    async def insert_variant(self, doc: dict[str, Any]) -> None:
        await self.variants.insert_one(doc)

    async def update_variant(
        self, variant_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.variants.find_one_and_update(
            {"variant_id": variant_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    async def soft_delete_variant(self, variant_id: str, now: datetime) -> bool:
        result = await self.variants.update_one(
            {"variant_id": variant_id, "deleted_at": None},
            {"$set": {"deleted_at": now, "status": "archived", "updated_at": now}},
        )
        return result.matched_count > 0

    # ── Size charts ────────────────────────────────────────────
    async def find_size_chart(self, size_chart_id: str) -> dict[str, Any] | None:
        return await self.size_charts.find_one({"size_chart_id": size_chart_id})

    async def list_size_charts(self) -> list[dict[str, Any]]:
        return await self.size_charts.find().sort("name", 1).to_list(None)

    async def insert_size_chart(self, doc: dict[str, Any]) -> None:
        await self.size_charts.insert_one(doc)

    async def update_size_chart(
        self, size_chart_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        from pymongo import ReturnDocument

        return await self.size_charts.find_one_and_update(
            {"size_chart_id": size_chart_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    async def delete_size_chart(self, size_chart_id: str) -> bool:
        result = await self.size_charts.delete_one({"size_chart_id": size_chart_id})
        return result.deleted_count > 0
