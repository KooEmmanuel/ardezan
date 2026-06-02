"""Catalog data access.

Sits between routers/services and MongoDB. Knows about the document shape;
callers only see Pydantic schemas. Each query filters by ``status=published``
and ``deleted_at=None`` so the customer-facing API never returns drafts or
soft-deleted records.
"""
from __future__ import annotations

import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger
from app.modules.catalog.schemas import (
    ProductListItem,
    VariantPublic,
)
from app.storage import get_storage

log = get_logger(__name__)

# Long-ish TTL — catalog images are cacheable for the customer's session.
_CATALOG_IMAGE_URL_TTL_SECONDS = 60 * 60 * 24  # 24h


def _available_for_sale(variant_doc: dict[str, Any]) -> int:
    """Derived: ``stock_on_hand - held_units``.

    ``held_units`` is the denormalised counter maintained by the Inventory
    module so this read is a single atomic field lookup. ``committed_units`` is
    not subtracted because per REQ-038 ``stock_on_hand`` already drops on
    payment confirmation.
    """
    inv = variant_doc.get("inventory", {}) or {}
    stock = int(inv.get("stock_on_hand", 0))
    held = int(inv.get("held_units", 0))
    return max(0, stock - held)


def _to_list_item(
    doc: dict[str, Any], *, primary_image_url: str | None = None
) -> ProductListItem:
    return ProductListItem(
        product_id=doc["product_id"],
        slug=doc["slug"],
        title=doc["title"],
        category=doc["category"],
        gender=doc.get("gender") or "unisex",
        pricing=doc["pricing"],
        primary_media_asset_id=doc.get("primary_media_asset_id"),
        primary_image_url=primary_image_url,
        try_on_eligible=bool(doc.get("ai", {}).get("eligible", False)),
    )


def _to_variant_public(doc: dict[str, Any]) -> VariantPublic:
    return VariantPublic(
        variant_id=doc["variant_id"],
        sku=doc["sku"],
        size=doc["size"],
        color=doc["color"],
        color_hex=doc.get("color_hex"),
        pricing=doc["pricing"],
        available_for_sale=_available_for_sale(doc),
    )


# ── Base query filter for every customer-facing read ────────────────
def _published_filter() -> dict[str, Any]:
    return {"status": "published", "deleted_at": None}


class CatalogRepository:
    """All catalog DB access for the customer surface lives here."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.products = db[C.products]
        self.variants = db[C.variants]
        self.size_charts = db[C.size_charts]
        self.media_assets = db[C.media_assets]

    # ── Image signing (M+) ─────────────────────────────────
    async def _sign_media_urls(
        self, media_asset_ids: list[str]
    ) -> dict[str, str]:
        """Resolve ``media_asset_id → signed URL``.

        Returns an empty dict if storage isn't configured or every asset is
        missing — callers fall back to a placeholder image so the grid never
        breaks because of a half-seeded catalog.
        """
        unique_ids = [mid for mid in dict.fromkeys(media_asset_ids) if mid]
        if not unique_ids:
            return {}
        cursor = self.media_assets.find(
            {"media_asset_id": {"$in": unique_ids}},
            projection={
                "media_asset_id": 1,
                "storage.object_key": 1,
                "retention.deleted_at": 1,
                "_id": 0,
            },
        )
        keys: dict[str, str] = {}
        async for doc in cursor:
            if (doc.get("retention") or {}).get("deleted_at"):
                continue
            key = (doc.get("storage") or {}).get("object_key")
            if key:
                keys[doc["media_asset_id"]] = key
        if not keys:
            return {}

        storage = get_storage()
        signed: dict[str, str] = {}
        for media_id, key in keys.items():
            try:
                signed[media_id] = await storage.presigned_get_url(
                    key, expires_in=_CATALOG_IMAGE_URL_TTL_SECONDS
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "catalog.sign_failed", media_id=media_id, error=str(exc)
                )
        return signed

    # ── Listings ────────────────────────────────────────────
    async def list_products(
        self,
        *,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 24,
        cursor: str | None = None,
    ) -> tuple[list[ProductListItem], str | None]:
        """Cursor-paginated list. Cursor is the last seen ``product_id``.

        ``category`` accepts:
          - A real category, case-insensitive (``tops`` matches ``Tops``).
          - The intent ``new`` — returns the newest products, no category
            filter, sorted by ``created_at`` desc.
          - The intent ``bottoms`` — expands to ``Trousers`` OR ``Skirts``.

        Pagination is keyset-style (``product_id > cursor``) for normal
        listings. The ``new`` intent disables cursor pagination because the
        sort order differs.
        """
        query: dict[str, Any] = _published_filter()
        sort_by_newest = False

        if category:
            cat_lower = category.strip().lower()
            if cat_lower == "new":
                sort_by_newest = True
            elif cat_lower == "bottoms":
                query["category"] = {"$in": ["Trousers", "Skirts"]}
            elif cat_lower in {"women", "men"}:
                # Gender filter — unisex shows under BOTH women and men.
                query["gender"] = {"$in": [cat_lower, "unisex"]}
            else:
                # Case-insensitive exact match against the stored category.
                query["category"] = {
                    "$regex": f"^{re.escape(category.strip())}$",
                    "$options": "i",
                }
        if tags:
            query["tags"] = {"$in": tags}
        if cursor and not sort_by_newest:
            query["product_id"] = {"$gt": cursor}

        cursor_q = self.products.find(query)
        if sort_by_newest:
            cursor_q = cursor_q.sort("created_at", -1)
        else:
            cursor_q = cursor_q.sort("product_id", 1)
        docs = await cursor_q.limit(limit).to_list(limit)
        signed = await self._sign_media_urls(
            [d.get("primary_media_asset_id") for d in docs if d.get("primary_media_asset_id")]
        )
        items = [
            _to_list_item(
                d,
                # ``static_image_url`` lets a seeder publish a product whose
                # primary image is served from ``frontend/public/`` instead
                # of B2/local storage. Falls back to the standard
                # ``primary_media_asset_id`` → signed-URL pipeline.
                primary_image_url=(
                    d.get("static_image_url")
                    or signed.get(d.get("primary_media_asset_id") or "")
                ),
            )
            for d in docs
        ]
        next_cursor = items[-1].product_id if len(items) == limit else None
        return items, next_cursor

    async def list_categories(self) -> list[str]:
        cats = await self.products.distinct("category", _published_filter())
        return sorted(str(c) for c in cats if c)

    # ── Lookup ──────────────────────────────────────────────
    async def get_product_by_slug(self, slug: str) -> dict[str, Any] | None:
        return await self.products.find_one({"slug": slug, **_published_filter()})

    async def signed_urls_for(self, media_asset_ids: list[str]) -> dict[str, str]:
        """Public version of ``_sign_media_urls`` for the router."""
        return await self._sign_media_urls(media_asset_ids)

    async def variants_for_product(self, product_id: str) -> list[VariantPublic]:
        docs = await self.variants.find(
            {"product_id": product_id, "status": "active", "deleted_at": None}
        ).sort("size", 1).to_list(None)
        return [_to_variant_public(d) for d in docs]

    # ── Search (keyword, MongoDB text index — REQ-021) ──────
    async def search_products(self, query: str, *, limit: int = 24) -> list[ProductListItem]:
        """Phase 1 keyword search. Semantic/vector search is deferred (REQ-094)."""
        docs = (
            await self.products.find(
                {"$text": {"$search": query}, **_published_filter()},
                projection={"score": {"$meta": "textScore"}, **{k: 1 for k in (
                    "product_id", "slug", "title", "category", "pricing",
                    "primary_media_asset_id", "static_image_url", "ai",
                )}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
            .to_list(limit)
        )
        signed = await self._sign_media_urls(
            [d.get("primary_media_asset_id") for d in docs if d.get("primary_media_asset_id")]
        )
        return [
            _to_list_item(
                d,
                primary_image_url=(
                    d.get("static_image_url")
                    or signed.get(d.get("primary_media_asset_id") or "")
                ),
            )
            for d in docs
        ]
