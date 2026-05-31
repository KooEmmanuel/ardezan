"""Admin product / variant / size-chart schemas.

Every PATCH model has all-optional fields so partial updates work via
``model_dump(exclude_unset=True)``. Customer-facing schemas (drafts hidden,
internal fields stripped) live in ``app.modules.catalog.schemas``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.catalog.schemas import (
    ProductAIMetadata,
    ProductDetails,
    ProductGender,
    ProductPricing,
    ProductPublication,
    ProductSEO,
    ProductStatus,
    SizeChartScope,
    VariantInventory,
    VariantMeasurements,
    VariantPricing,
    VariantStatus,
)


# ── Products ────────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    category: str = Field(..., min_length=1, max_length=80)
    subcategory: str | None = None
    gender: ProductGender = "unisex"
    tags: list[str] = Field(default_factory=list)
    slug: str | None = Field(None, min_length=1, max_length=80)
    status: ProductStatus = "draft"
    pricing: ProductPricing
    media_asset_ids: list[str] = Field(default_factory=list)
    primary_media_asset_id: str | None = None
    ai_friendly_media_asset_ids: list[str] = Field(default_factory=list)
    product_details: ProductDetails = Field(default_factory=ProductDetails)
    size_chart_id: str | None = None
    ai: ProductAIMetadata = Field(default_factory=ProductAIMetadata)
    seo: ProductSEO = Field(default_factory=ProductSEO)


class ProductUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(None, min_length=1, max_length=80)
    subcategory: str | None = None
    gender: ProductGender | None = None
    tags: list[str] | None = None
    slug: str | None = Field(None, min_length=1, max_length=80)
    status: ProductStatus | None = None
    pricing: ProductPricing | None = None
    media_asset_ids: list[str] | None = None
    primary_media_asset_id: str | None = None
    ai_friendly_media_asset_ids: list[str] | None = None
    product_details: ProductDetails | None = None
    size_chart_id: str | None = None
    ai: ProductAIMetadata | None = None
    seo: ProductSEO | None = None


class ProductAdminPublic(BaseModel):
    """Full product as the admin sees it — includes drafts and soft-deleted."""

    product_id: str
    slug: str
    title: str
    description: str | None = None
    category: str
    subcategory: str | None = None
    gender: ProductGender = "unisex"
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus
    publication: ProductPublication = Field(default_factory=ProductPublication)
    pricing: ProductPricing
    media_asset_ids: list[str] = Field(default_factory=list)
    primary_media_asset_id: str | None = None
    ai_friendly_media_asset_ids: list[str] = Field(default_factory=list)
    product_details: ProductDetails = Field(default_factory=ProductDetails)
    size_chart_id: str | None = None
    ai: ProductAIMetadata = Field(default_factory=ProductAIMetadata)
    seo: ProductSEO = Field(default_factory=ProductSEO)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ProductAdminListItem(BaseModel):
    """Compact product for the admin list view.

    Computed at read time (variants are joined, primary image is signed) so
    the table can render image + variants + stock without N+1 round-trips.
    """

    product_id: str
    slug: str
    title: str
    category: str
    subcategory: str | None = None
    gender: ProductGender = "unisex"
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus
    pricing: ProductPricing
    primary_image_url: str | None = None
    variant_count: int = 0
    stock_on_hand_total: int = 0
    low_stock_variant_count: int = 0
    out_of_stock_variant_count: int = 0
    price_min_amount: int | None = None
    price_max_amount: int | None = None
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductAdminListItem]
    total: int = 0
    next_cursor: str | None = None


class ProductAdminDetail(ProductAdminPublic):
    """Detail view returned by GET /admin/products/{id}.

    Variants are joined inline (with full inventory) and primary/all media
    URLs are signed — so the admin detail page renders in one round-trip.

    NOTE: ``variants`` is declared after ``VariantAdminPublic`` below via
    ``model_rebuild`` to dodge the forward-ref cycle.
    """

    primary_image_url: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    variants: list["VariantAdminPublic"] = Field(default_factory=list)


# ── Variants ────────────────────────────────────────────────────────
class VariantCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=80)
    title: str | None = None
    size: str = Field(..., min_length=1, max_length=20)
    color: str = Field(..., min_length=1, max_length=40)
    color_hex: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    status: VariantStatus = "active"
    pricing: VariantPricing
    inventory: VariantInventory = Field(default_factory=VariantInventory)
    measurements: VariantMeasurements = Field(default_factory=VariantMeasurements)


class VariantUpdate(BaseModel):
    sku: str | None = Field(None, min_length=1, max_length=80)
    title: str | None = None
    size: str | None = None
    color: str | None = None
    color_hex: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    status: VariantStatus | None = None
    pricing: VariantPricing | None = None
    # Inventory updates are tricky — held_units is managed by the Inventory
    # module and shouldn't be written here. The service strips it from the
    # payload on update.
    inventory: VariantInventory | None = None
    measurements: VariantMeasurements | None = None


class VariantAdminPublic(BaseModel):
    variant_id: str
    product_id: str
    sku: str
    title: str | None = None
    size: str
    color: str
    color_hex: str | None = None
    status: VariantStatus
    pricing: VariantPricing
    inventory: VariantInventory
    measurements: VariantMeasurements
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class VariantListResponse(BaseModel):
    items: list[VariantAdminPublic]


# Resolve the forward ref on ProductAdminDetail now that VariantAdminPublic exists.
ProductAdminDetail.model_rebuild()


# ── Size charts (DATA_MODEL.md §4.3) ────────────────────────────────
class SizeChartEntry(BaseModel):
    label: str = Field(..., min_length=1, max_length=20)
    body_measurements: dict[str, float] = Field(default_factory=dict)
    fit_notes: str | None = None


class SizeChartCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scope: SizeChartScope = "house"
    brand: str | None = None
    product_id: str | None = None
    unit: Literal["in", "cm"] = "cm"
    sizes: list[SizeChartEntry] = Field(..., min_length=1)
    fallback_size_chart_id: str | None = None


class SizeChartUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    scope: SizeChartScope | None = None
    brand: str | None = None
    product_id: str | None = None
    unit: Literal["in", "cm"] | None = None
    sizes: list[SizeChartEntry] | None = None
    fallback_size_chart_id: str | None = None


class SizeChartPublic(BaseModel):
    size_chart_id: str
    name: str
    scope: SizeChartScope
    brand: str | None = None
    product_id: str | None = None
    unit: Literal["in", "cm"]
    sizes: list[SizeChartEntry]
    fallback_size_chart_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SizeChartListResponse(BaseModel):
    items: list[SizeChartPublic]


# ── Audit summary helpers (used by the service) ─────────────────────
def diff_summary(
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(before_only, after_only)`` containing only fields that changed."""
    if not before:
        return {}, after
    keys = set(after.keys())
    before_only: dict[str, Any] = {}
    after_only: dict[str, Any] = {}
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            before_only[k] = b
            after_only[k] = a
    return before_only, after_only
