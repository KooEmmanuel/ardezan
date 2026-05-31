"""Pydantic schemas for catalog entities.

Mirrors ``DATA_MODEL.md`` §4 (products), §4.2 (variants), §4.3 (size charts).
Money values are integer minor units (per ``DATA_MODEL.md`` §2.4) — never floats.

Two layers of models:
- ``Product`` / ``Variant`` — the persisted shape, also used for input where the
  full document is needed.
- ``ProductListItem`` / ``ProductDetail`` / ``VariantPublic`` — the trimmed
  customer-facing shapes the API returns. They drop internal-only fields like
  inventory counters and audit timestamps.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── Status enums ────────────────────────────────────────────────────
ProductStatus = Literal["draft", "published", "archived"]
VariantStatus = Literal["active", "inactive", "archived"]
SizeChartScope = Literal["house", "brand", "product"]
ProductGender = Literal["women", "men", "unisex"]


# ── Sub-models ──────────────────────────────────────────────────────
class ProductPricing(BaseModel):
    base_price_amount: int = Field(..., ge=0)
    compare_at_price_amount: int | None = None
    currency: str = Field(..., min_length=3, max_length=3)


class ProductPublication(BaseModel):
    published_at: datetime | None = None
    unpublished_at: datetime | None = None


class ProductDetails(BaseModel):
    material: str | None = None
    care_instructions: str | None = None
    fit_notes: str | None = None
    return_eligible: bool = True
    final_sale: bool = False


class ProductAIMetadata(BaseModel):
    eligible: bool = True
    fabric_type: str | None = None
    formality: str | None = None
    fit_shape: str | None = None
    season: str | None = None
    color_palette: list[str] = Field(default_factory=list)
    body_suitability: list[str] = Field(default_factory=list)
    occasion_suitability: list[str] = Field(default_factory=list)
    layering_compatibility: list[str] = Field(default_factory=list)
    compatibility_tags: list[str] = Field(default_factory=list)


class ProductSEO(BaseModel):
    title: str | None = None
    description: str | None = None
    canonical_path: str | None = None


class VariantPricing(BaseModel):
    price_amount: int = Field(..., ge=0)
    compare_at_price_amount: int | None = None
    currency: str = Field(..., min_length=3, max_length=3)


class VariantInventory(BaseModel):
    stock_on_hand: int = Field(0, ge=0)
    # Denormalised count of units locked by active inventory_holds — kept on
    # the variant doc so availability checks are a single atomic op (Inventory §).
    held_units: int = Field(0, ge=0)
    # Reserved for future "paid but not yet shipped" tracking. Unused in Phase 1
    # because per REQ-038 stock_on_hand decrements on payment confirmation.
    committed_units: int = Field(0, ge=0)
    low_stock_threshold: int = Field(5, ge=0)
    track_inventory: bool = True


class VariantMeasurements(BaseModel):
    garment_chest: float | None = None
    garment_waist: float | None = None
    garment_hip: float | None = None
    garment_inseam: float | None = None
    garment_length: float | None = None
    unit: Literal["in", "cm"] = "cm"


# ── Storage shapes (full documents) ─────────────────────────────────
class Product(BaseModel):
    product_id: str
    slug: str
    title: str
    description: str | None = None
    category: str
    subcategory: str | None = None
    gender: ProductGender = "unisex"
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus = "draft"
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


class Variant(BaseModel):
    variant_id: str
    product_id: str
    sku: str
    title: str | None = None
    size: str
    color: str
    color_hex: str | None = None
    status: VariantStatus = "active"
    pricing: VariantPricing
    inventory: VariantInventory = Field(default_factory=VariantInventory)
    measurements: VariantMeasurements = Field(default_factory=VariantMeasurements)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# ── Customer-facing API shapes ──────────────────────────────────────
class VariantPublic(BaseModel):
    """The variant as customers see it. ``available_for_sale`` is derived from
    inventory and committed_units; raw counters are never exposed."""

    variant_id: str
    sku: str
    size: str
    color: str
    color_hex: str | None = None
    pricing: VariantPricing
    available_for_sale: int = Field(..., ge=0)


class ProductListItem(BaseModel):
    """Compact product for grids/listings."""

    product_id: str
    slug: str
    title: str
    category: str
    gender: ProductGender = "unisex"
    pricing: ProductPricing
    primary_media_asset_id: str | None = None
    # Pre-signed URL the frontend can drop straight into <img src=>. Optional
    # so unseeded products still render (the grid falls back to a placeholder).
    primary_image_url: str | None = None
    try_on_eligible: bool


class ProductDetail(BaseModel):
    """Full product as shown on the product detail page."""

    product_id: str
    slug: str
    title: str
    description: str | None = None
    category: str
    subcategory: str | None = None
    tags: list[str]
    pricing: ProductPricing
    media_asset_ids: list[str]
    primary_media_asset_id: str | None = None
    # Pre-signed URLs in the same order as ``media_asset_ids`` so the gallery
    # can render without per-asset lookups. ``primary_image_url`` is also
    # included separately for the hero image.
    media_urls: list[str] = Field(default_factory=list)
    primary_image_url: str | None = None
    ai_friendly_media_asset_ids: list[str]
    product_details: ProductDetails
    variants: list[VariantPublic]
    size_chart_id: str | None = None
    try_on_eligible: bool


# ── Response envelopes ──────────────────────────────────────────────
class ProductListResponse(BaseModel):
    items: list[ProductListItem]
    next_cursor: str | None = None


class CategoryListResponse(BaseModel):
    categories: list[str]
