"""Admin product / variant / size-chart business logic.

Every mutation:
1. Captures the ``before`` state (for the audit log).
2. Applies the change.
3. Writes an ``audit_logs`` entry via ``AdminRepository.write_audit``.

Slug generation is automatic for products on create. If a collision occurs
with an existing product, we append a short random suffix.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.products_repository import AdminProductsRepository
from app.modules.admin.products_schemas import (
    ProductCreate,
    ProductUpdate,
    SizeChartCreate,
    SizeChartUpdate,
    VariantCreate,
    VariantUpdate,
    diff_summary,
)
from app.modules.admin.repository import AdminRepository

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _product_id() -> str:
    return f"prod_{secrets.token_hex(8)}"


def _variant_id() -> str:
    return f"var_{secrets.token_hex(8)}"


def _size_chart_id() -> str:
    return f"size_{secrets.token_hex(8)}"


def slugify(text: str) -> str:
    """Conservative slug: lowercase ASCII letters/digits, hyphens for breaks."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text[:80] or f"product-{secrets.token_hex(3)}"


class AdminProductsService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = AdminProductsRepository(db)
        self.admin_repo = AdminRepository(db)

    # ── PRODUCT operations ────────────────────────────────────
    async def list_products(
        self,
        *,
        status: str | None,
        category: str | None,
        include_deleted: bool,
        q: str | None = None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        docs = await self.repo.list_products(
            status=status,
            category=category,
            include_deleted=include_deleted,
            q=q,
            limit=limit,
            cursor=cursor,
        )
        total = await self.repo.count_products(
            status=status,
            category=category,
            include_deleted=include_deleted,
            q=q,
        )

        # Aggregate variant stats once for the whole page (one round-trip).
        product_ids = [d["product_id"] for d in docs]
        stats = await self.repo.aggregate_variant_stats(product_ids)

        # Sign primary images in one batch via the catalog repo's helper —
        # this is the canonical place URL signing lives.
        from app.modules.catalog.repository import CatalogRepository

        catalog_repo = CatalogRepository(self.db)
        media_ids = [
            d["primary_media_asset_id"]
            for d in docs
            if d.get("primary_media_asset_id")
        ]
        signed = await catalog_repo._sign_media_urls(media_ids)  # noqa: SLF001

        enriched: list[dict[str, Any]] = []
        for d in docs:
            s = stats.get(d["product_id"], {})
            primary_id = d.get("primary_media_asset_id")
            enriched.append(
                {
                    "product_id": d["product_id"],
                    "slug": d["slug"],
                    "title": d["title"],
                    "category": d["category"],
                    "subcategory": d.get("subcategory"),
                    "gender": d.get("gender") or "unisex",
                    "tags": d.get("tags", []),
                    "status": d["status"],
                    "pricing": d["pricing"],
                    "primary_image_url": signed.get(primary_id) if primary_id else None,
                    "variant_count": int(s.get("variant_count", 0)),
                    "stock_on_hand_total": int(s.get("stock_on_hand_total", 0)),
                    "low_stock_variant_count": int(s.get("low_stock_variant_count", 0)),
                    "out_of_stock_variant_count": int(
                        s.get("out_of_stock_variant_count", 0)
                    ),
                    "price_min_amount": s.get("price_min"),
                    "price_max_amount": s.get("price_max"),
                    "updated_at": d["updated_at"],
                }
            )

        next_cursor = docs[-1]["product_id"] if len(docs) == limit else None
        return enriched, total, next_cursor

    async def get_product(self, product_id: str) -> dict[str, Any]:
        doc = await self.repo.find_product(product_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Product not found: {product_id}", http_status=404
            )
        return doc

    async def create_product(
        self,
        body: ProductCreate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        # Resolve slug — auto-generate from title; ensure uniqueness.
        base_slug = body.slug or slugify(body.title)
        slug = base_slug
        if await self.repo.find_product_by_slug(slug):
            slug = f"{base_slug}-{secrets.token_hex(3)}"

        now = _now()
        product_id = _product_id()
        doc: dict[str, Any] = {
            "product_id": product_id,
            "slug": slug,
            "title": body.title,
            "description": body.description,
            "category": body.category,
            "subcategory": body.subcategory,
            "gender": body.gender,
            "tags": body.tags,
            "status": body.status,
            "publication": {
                "published_at": now if body.status == "published" else None,
                "unpublished_at": None,
            },
            "pricing": body.pricing.model_dump(),
            "media_asset_ids": body.media_asset_ids,
            "primary_media_asset_id": body.primary_media_asset_id,
            "ai_friendly_media_asset_ids": body.ai_friendly_media_asset_ids,
            "product_details": body.product_details.model_dump(),
            "size_chart_id": body.size_chart_id,
            "ai": body.ai.model_dump(),
            "seo": body.seo.model_dump(),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "created_by_admin_id": admin["admin_id"],
            "updated_by_admin_id": admin["admin_id"],
        }

        try:
            await self.repo.insert_product(doc)
        except DuplicateKeyError as exc:
            raise ApiError(
                ErrorCode.CONFLICT,
                "A product with this slug already exists.",
                http_status=409,
            ) from exc

        await self._audit(
            admin,
            action="product.create",
            target_type="product",
            target_id=product_id,
            after={"slug": slug, "title": body.title, "status": body.status},
        )
        log.info("admin.product_created", product_id=product_id, slug=slug)
        return doc

    async def update_product(
        self,
        product_id: str,
        body: ProductUpdate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self.get_product(product_id)
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            return existing

        # If publication transitions to "published" for the first time, stamp it.
        if fields.get("status") == "published" and not existing.get("publication", {}).get(
            "published_at"
        ):
            fields["publication"] = {
                "published_at": _now(),
                "unpublished_at": existing.get("publication", {}).get("unpublished_at"),
            }
        elif fields.get("status") in {"draft", "archived"}:
            pub = dict(existing.get("publication") or {})
            pub["unpublished_at"] = _now()
            fields["publication"] = pub

        fields["updated_at"] = _now()
        fields["updated_by_admin_id"] = admin["admin_id"]

        try:
            updated = await self.repo.update_product(product_id, fields)
        except DuplicateKeyError as exc:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Another product is already using that slug.",
                http_status=409,
            ) from exc
        assert updated is not None

        before_summary, after_summary = diff_summary(existing, fields)
        await self._audit(
            admin,
            action="product.update",
            target_type="product",
            target_id=product_id,
            before=before_summary,
            after=after_summary,
        )
        log.info("admin.product_updated", product_id=product_id, fields=list(fields))
        return updated

    async def delete_product(
        self, product_id: str, admin: dict[str, Any]
    ) -> None:
        existing = await self.get_product(product_id)
        if existing.get("deleted_at"):
            return  # idempotent
        ok = await self.repo.soft_delete_product(product_id, _now())
        if not ok:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Product not found: {product_id}", http_status=404
            )
        await self._audit(
            admin,
            action="product.delete",
            target_type="product",
            target_id=product_id,
            before={"status": existing.get("status")},
            after={"status": "archived", "deleted": True},
        )
        log.info("admin.product_deleted", product_id=product_id)

    # ── VARIANT operations ────────────────────────────────────
    async def list_variants(
        self, product_id: str, *, include_deleted: bool
    ) -> list[dict[str, Any]]:
        # Sanity: ensure product exists (404 if not)
        await self.get_product(product_id)
        return await self.repo.list_variants_for_product(
            product_id, include_deleted=include_deleted
        )

    async def get_variant(self, variant_id: str) -> dict[str, Any]:
        doc = await self.repo.find_variant(variant_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"Variant not found: {variant_id}", http_status=404
            )
        return doc

    async def create_variant(
        self,
        product_id: str,
        body: VariantCreate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        # Ensure product exists.
        await self.get_product(product_id)

        # Defensive: clear held_units in the inbound payload — that field is
        # managed by the Inventory module, not by the admin form.
        inventory_in = body.inventory.model_dump()
        inventory_in["held_units"] = 0

        now = _now()
        variant_id = _variant_id()
        doc: dict[str, Any] = {
            "variant_id": variant_id,
            "product_id": product_id,
            "sku": body.sku,
            "title": body.title,
            "size": body.size,
            "color": body.color,
            "color_hex": body.color_hex,
            "status": body.status,
            "pricing": body.pricing.model_dump(),
            "inventory": inventory_in,
            "measurements": body.measurements.model_dump(),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "created_by_admin_id": admin["admin_id"],
            "updated_by_admin_id": admin["admin_id"],
        }

        try:
            await self.repo.insert_variant(doc)
        except DuplicateKeyError as exc:
            raise ApiError(
                ErrorCode.CONFLICT,
                f"A variant with SKU '{body.sku}' already exists.",
                http_status=409,
            ) from exc

        await self._audit(
            admin,
            action="variant.create",
            target_type="variant",
            target_id=variant_id,
            after={"sku": body.sku, "size": body.size, "color": body.color},
        )
        log.info(
            "admin.variant_created",
            variant_id=variant_id,
            product_id=product_id,
            sku=body.sku,
        )
        return doc

    async def update_variant(
        self,
        variant_id: str,
        body: VariantUpdate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self.get_variant(variant_id)
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            return existing

        # Sanitise inventory updates — held_units stays under Inventory module control.
        if "inventory" in fields and fields["inventory"] is not None:
            inv = dict(fields["inventory"])
            inv.pop("held_units", None)
            # Preserve the live held_units value from the existing doc.
            inv["held_units"] = int(
                (existing.get("inventory") or {}).get("held_units", 0)
            )
            fields["inventory"] = inv

        fields["updated_at"] = _now()
        fields["updated_by_admin_id"] = admin["admin_id"]

        try:
            updated = await self.repo.update_variant(variant_id, fields)
        except DuplicateKeyError as exc:
            raise ApiError(
                ErrorCode.CONFLICT,
                "Another variant is already using that SKU.",
                http_status=409,
            ) from exc
        assert updated is not None

        before_summary, after_summary = diff_summary(existing, fields)
        await self._audit(
            admin,
            action="variant.update",
            target_type="variant",
            target_id=variant_id,
            before=before_summary,
            after=after_summary,
        )

        # Record an inventory movement when stock_on_hand actually changes.
        # Keeps the inventory_movements ledger authoritative for the
        # "why did stock go from X to Y?" question.
        if "inventory" in fields and isinstance(fields["inventory"], dict):
            before_stock = int(
                (existing.get("inventory") or {}).get("stock_on_hand", 0) or 0
            )
            after_stock = int(fields["inventory"].get("stock_on_hand", before_stock))
            if after_stock != before_stock:
                from app.modules.inventory.movements import record_movement

                await record_movement(
                    self.db,
                    variant_id=variant_id,
                    product_id=existing.get("product_id"),
                    delta=after_stock - before_stock,
                    quantity_after=after_stock,
                    reason="admin_adjustment",
                    source_type="admin",
                    source_id=admin["admin_id"],
                    actor_id=admin["admin_id"],
                )

        log.info("admin.variant_updated", variant_id=variant_id, fields=list(fields))
        return updated

    async def delete_variant(self, variant_id: str, admin: dict[str, Any]) -> None:
        existing = await self.get_variant(variant_id)
        if existing.get("deleted_at"):
            return
        await self.repo.soft_delete_variant(variant_id, _now())
        await self._audit(
            admin,
            action="variant.delete",
            target_type="variant",
            target_id=variant_id,
            before={"status": existing.get("status")},
            after={"status": "archived", "deleted": True},
        )
        log.info("admin.variant_deleted", variant_id=variant_id)

    # ── SIZE CHART operations ─────────────────────────────────
    async def list_size_charts(self) -> list[dict[str, Any]]:
        return await self.repo.list_size_charts()

    async def get_size_chart(self, size_chart_id: str) -> dict[str, Any]:
        doc = await self.repo.find_size_chart(size_chart_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Size chart not found: {size_chart_id}",
                http_status=404,
            )
        return doc

    async def create_size_chart(
        self, body: SizeChartCreate, admin: dict[str, Any]
    ) -> dict[str, Any]:
        now = _now()
        size_chart_id = _size_chart_id()
        doc: dict[str, Any] = {
            "size_chart_id": size_chart_id,
            "name": body.name,
            "scope": body.scope,
            "brand": body.brand,
            "product_id": body.product_id,
            "unit": body.unit,
            "sizes": [s.model_dump() for s in body.sizes],
            "fallback_size_chart_id": body.fallback_size_chart_id,
            "created_at": now,
            "updated_at": now,
        }
        await self.repo.insert_size_chart(doc)
        await self._audit(
            admin,
            action="size_chart.create",
            target_type="size_chart",
            target_id=size_chart_id,
            after={"name": body.name, "scope": body.scope},
        )
        log.info("admin.size_chart_created", size_chart_id=size_chart_id, name=body.name)
        return doc

    async def update_size_chart(
        self,
        size_chart_id: str,
        body: SizeChartUpdate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self.get_size_chart(size_chart_id)
        fields = body.model_dump(exclude_unset=True)
        if "sizes" in fields and fields["sizes"] is not None:
            fields["sizes"] = [s if isinstance(s, dict) else s.model_dump() for s in fields["sizes"]]
        if not fields:
            return existing
        fields["updated_at"] = _now()
        updated = await self.repo.update_size_chart(size_chart_id, fields)
        assert updated is not None
        before_summary, after_summary = diff_summary(existing, fields)
        await self._audit(
            admin,
            action="size_chart.update",
            target_type="size_chart",
            target_id=size_chart_id,
            before=before_summary,
            after=after_summary,
        )
        log.info("admin.size_chart_updated", size_chart_id=size_chart_id)
        return updated

    async def delete_size_chart(
        self, size_chart_id: str, admin: dict[str, Any]
    ) -> None:
        existing = await self.get_size_chart(size_chart_id)
        await self.repo.delete_size_chart(size_chart_id)
        await self._audit(
            admin,
            action="size_chart.delete",
            target_type="size_chart",
            target_id=size_chart_id,
            before={"name": existing.get("name"), "scope": existing.get("scope")},
        )
        log.info("admin.size_chart_deleted", size_chart_id=size_chart_id)

    # ── Audit helper ──────────────────────────────────────────
    async def _audit(
        self,
        admin: dict[str, Any],
        *,
        action: str,
        target_type: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        meta = admin.get("_request_meta", {})
        await self.admin_repo.write_audit(
            actor_id=admin["admin_id"],
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            ip_address=meta.get("ip"),
            user_agent=meta.get("ua"),
        )
