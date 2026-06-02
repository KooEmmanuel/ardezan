"""Customer-facing catalog routes (per ``API.md`` §6).

Read-only. Admin product CRUD lands in M3 under ``app/modules/admin``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import (
    CategoryListResponse,
    ProductDetail,
    ProductListResponse,
)

router = APIRouter()


def get_repo(db: DbDep) -> CatalogRepository:
    return CatalogRepository(db)


RepoDep = Annotated[CatalogRepository, Depends(get_repo)]


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List published products",
)
async def list_products(
    repo: RepoDep,
    category: Annotated[
        str | None,
        Query(description="Exact category match (e.g. 'Outerwear')"),
    ] = None,
    tag: Annotated[
        list[str] | None,
        Query(description="Filter by tag (repeatable)"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
    cursor: Annotated[
        str | None,
        Query(description="Pagination cursor - pass back next_cursor"),
    ] = None,
) -> ProductListResponse:
    items, next_cursor = await repo.list_products(
        category=category,
        tags=tag,
        limit=limit,
        cursor=cursor,
    )
    return ProductListResponse(items=items, next_cursor=next_cursor)


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    summary="List published product categories",
)
async def list_categories(repo: RepoDep) -> CategoryListResponse:
    return CategoryListResponse(categories=await repo.list_categories())


@router.get(
    "/search",
    response_model=ProductListResponse,
    summary="Keyword search across product titles, descriptions, and tags",
)
async def search(
    repo: RepoDep,
    q: Annotated[str, Query(min_length=1, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
) -> ProductListResponse:
    items = await repo.search_products(q, limit=limit)
    # Search results are ranked by text score — pagination here would need a
    # different cursor strategy; deferred until the volume justifies it.
    return ProductListResponse(items=items, next_cursor=None)


@router.get(
    "/products/{slug}",
    response_model=ProductDetail,
    summary="Single product by slug, including in-stock variants",
)
async def get_product(slug: str, repo: RepoDep) -> ProductDetail:
    doc = await repo.get_product_by_slug(slug)
    if not doc:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Product not found: {slug}",
            http_status=404,
        )
    variants = await repo.variants_for_product(doc["product_id"])
    media_ids = doc.get("media_asset_ids", []) or []
    primary_id = doc.get("primary_media_asset_id")
    all_ids = list(dict.fromkeys([*media_ids, primary_id])) if primary_id else list(media_ids)
    signed = await repo.signed_urls_for(all_ids)
    # ``static_image_url`` / ``static_media_urls`` let a seeder publish a
    # product whose images live in ``frontend/public/`` (CDN-served by
    # Vercel, no B2 egress cap). Fall back to B2-signed URLs for any
    # product that uses the media-asset pipeline.
    static_primary = doc.get("static_image_url")
    static_media = doc.get("static_media_urls", []) or []
    media_urls = list(static_media) or [signed[mid] for mid in media_ids if mid in signed]
    primary_image_url = static_primary or (signed.get(primary_id) if primary_id else None)
    return ProductDetail(
        product_id=doc["product_id"],
        slug=doc["slug"],
        title=doc["title"],
        description=doc.get("description"),
        category=doc["category"],
        subcategory=doc.get("subcategory"),
        tags=doc.get("tags", []),
        pricing=doc["pricing"],
        media_asset_ids=media_ids,
        primary_media_asset_id=primary_id,
        media_urls=media_urls,
        primary_image_url=primary_image_url,
        ai_friendly_media_asset_ids=doc.get("ai_friendly_media_asset_ids", []),
        product_details=doc.get("product_details", {}) or {},
        variants=variants,
        size_chart_id=doc.get("size_chart_id"),
        try_on_eligible=bool(doc.get("ai", {}).get("eligible", False)),
    )
