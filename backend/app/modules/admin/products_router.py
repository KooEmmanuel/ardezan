"""Admin product / variant / size-chart routes (per API.md §12.1–§12.2).

All endpoints require admin auth via the ``AdminDep`` dependency. Every
mutation writes an entry to ``audit_logs`` (see ``products_service``).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile, status

from app.deps import DbDep
from app.modules.admin.deps import AdminDep
from app.modules.admin.media_service import AdminMediaService
from app.modules.admin.products_schemas import (
    ProductAdminDetail,
    ProductAdminListItem,
    ProductAdminPublic,
    ProductCreate,
    ProductListResponse,
    ProductUpdate,
    SizeChartCreate,
    SizeChartListResponse,
    SizeChartPublic,
    SizeChartUpdate,
    VariantAdminPublic,
    VariantCreate,
    VariantListResponse,
    VariantUpdate,
)
from app.modules.admin.products_service import AdminProductsService

router = APIRouter()


def get_service(db: DbDep) -> AdminProductsService:
    return AdminProductsService(db)


def get_media_service(db: DbDep) -> AdminMediaService:
    return AdminMediaService(db)


ServiceDep = Annotated[AdminProductsService, Depends(get_service)]
MediaServiceDep = Annotated[AdminMediaService, Depends(get_media_service)]


# ── Products ────────────────────────────────────────────────────────
@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List products (admin — includes drafts and archived)",
)
async def list_products(
    service: ServiceDep,
    admin: AdminDep,
    status_filter: Annotated[
        str | None, Query(alias="status", description="Filter by status")
    ] = None,
    category: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(description="Search title/slug/tags")] = None,
    include_deleted: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> ProductListResponse:
    items, total, next_cursor = await service.list_products(
        status=status_filter,
        category=category,
        include_deleted=include_deleted,
        q=q,
        limit=limit,
        cursor=cursor,
    )
    return ProductListResponse(
        items=[ProductAdminListItem(**d) for d in items],
        total=total,
        next_cursor=next_cursor,
    )


@router.post(
    "/products",
    response_model=ProductAdminPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product (status defaults to draft)",
)
async def create_product(
    body: ProductCreate,
    service: ServiceDep,
    admin: AdminDep,
) -> ProductAdminPublic:
    doc = await service.create_product(body, admin)
    return ProductAdminPublic(**doc)


@router.get(
    "/products/{product_id}",
    response_model=ProductAdminDetail,
    summary="Read a product (admin view — includes variants + signed media URLs)",
)
async def get_product(
    product_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> ProductAdminDetail:
    doc = await service.get_product(product_id)
    variants = await service.list_variants(product_id, include_deleted=False)

    # Sign primary + all media in one batch.
    from app.modules.catalog.repository import CatalogRepository

    catalog_repo = CatalogRepository(service.db)
    media_ids = list(doc.get("media_asset_ids") or [])
    primary_id = doc.get("primary_media_asset_id")
    if primary_id and primary_id not in media_ids:
        media_ids.insert(0, primary_id)
    signed = await catalog_repo._sign_media_urls(media_ids)  # noqa: SLF001

    payload = dict(doc)
    payload["primary_image_url"] = signed.get(primary_id) if primary_id else None
    payload["media_urls"] = [
        signed[mid] for mid in (doc.get("media_asset_ids") or []) if signed.get(mid)
    ]
    payload["variants"] = variants
    return ProductAdminDetail(**payload)


@router.patch(
    "/products/{product_id}",
    response_model=ProductAdminPublic,
    summary="Update a product — partial; only fields sent are changed",
)
async def update_product(
    product_id: str,
    body: ProductUpdate,
    service: ServiceDep,
    admin: AdminDep,
) -> ProductAdminPublic:
    doc = await service.update_product(product_id, body, admin)
    return ProductAdminPublic(**doc)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a product (sets deleted_at + status=archived)",
)
async def delete_product(
    product_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> None:
    await service.delete_product(product_id, admin)


# ── Media ───────────────────────────────────────────────────────────
@router.post(
    "/products/{product_id}/media",
    status_code=status.HTTP_201_CREATED,
    summary="Attach an uploaded image to a product",
)
async def upload_product_media(
    product_id: str,
    media_service: MediaServiceDep,
    admin: AdminDep,
    file: Annotated[UploadFile, File(description="Product image (JPEG/PNG/WebP)")],
    set_as_primary: Annotated[bool, Form()] = True,
) -> dict[str, object]:
    body = await file.read()
    result = await media_service.attach_uploaded(
        product_id=product_id,
        file_bytes=body,
        content_type=file.content_type or "application/octet-stream",
        set_as_primary=set_as_primary,
        admin=admin,
    )
    return {
        "media_asset_id": result["media_asset_id"],
        "object_key": result["storage"]["object_key"],
        "is_primary": result["is_primary"],
        "ai_generated": False,
    }


@router.post(
    "/products/{product_id}/media/ai-generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a catalog image via Gemini and attach it to the product",
)
async def ai_generate_product_media(
    product_id: str,
    media_service: MediaServiceDep,
    admin: AdminDep,
    set_as_primary: Annotated[bool, Body(embed=True)] = True,
) -> dict[str, object]:
    result = await media_service.attach_ai_generated(
        product_id=product_id,
        set_as_primary=set_as_primary,
        admin=admin,
    )
    return {
        "media_asset_id": result["media_asset_id"],
        "object_key": result["storage"]["object_key"],
        "is_primary": result["is_primary"],
        "ai_generated": True,
    }


# ── Variants ────────────────────────────────────────────────────────
@router.get(
    "/products/{product_id}/variants",
    response_model=VariantListResponse,
    summary="List variants for a product",
)
async def list_variants(
    product_id: str,
    service: ServiceDep,
    admin: AdminDep,
    include_deleted: Annotated[bool, Query()] = False,
) -> VariantListResponse:
    docs = await service.list_variants(product_id, include_deleted=include_deleted)
    return VariantListResponse(items=[VariantAdminPublic(**d) for d in docs])


@router.post(
    "/products/{product_id}/variants",
    response_model=VariantAdminPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a variant for a product",
)
async def create_variant(
    product_id: str,
    body: VariantCreate,
    service: ServiceDep,
    admin: AdminDep,
) -> VariantAdminPublic:
    doc = await service.create_variant(product_id, body, admin)
    return VariantAdminPublic(**doc)


@router.get(
    "/variants/{variant_id}",
    response_model=VariantAdminPublic,
    summary="Read a variant",
)
async def get_variant(
    variant_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> VariantAdminPublic:
    doc = await service.get_variant(variant_id)
    return VariantAdminPublic(**doc)


@router.patch(
    "/variants/{variant_id}",
    response_model=VariantAdminPublic,
    summary="Update a variant — partial; held_units cannot be set directly",
)
async def update_variant(
    variant_id: str,
    body: VariantUpdate,
    service: ServiceDep,
    admin: AdminDep,
) -> VariantAdminPublic:
    doc = await service.update_variant(variant_id, body, admin)
    return VariantAdminPublic(**doc)


@router.delete(
    "/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a variant (sets deleted_at + status=archived)",
)
async def delete_variant(
    variant_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> None:
    await service.delete_variant(variant_id, admin)


# ── Size charts ─────────────────────────────────────────────────────
@router.get(
    "/size-charts",
    response_model=SizeChartListResponse,
    summary="List size charts",
)
async def list_size_charts(
    service: ServiceDep,
    admin: AdminDep,
) -> SizeChartListResponse:
    docs = await service.list_size_charts()
    return SizeChartListResponse(items=[SizeChartPublic(**d) for d in docs])


@router.post(
    "/size-charts",
    response_model=SizeChartPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a size chart",
)
async def create_size_chart(
    body: SizeChartCreate,
    service: ServiceDep,
    admin: AdminDep,
) -> SizeChartPublic:
    doc = await service.create_size_chart(body, admin)
    return SizeChartPublic(**doc)


@router.get(
    "/size-charts/{size_chart_id}",
    response_model=SizeChartPublic,
    summary="Read a size chart",
)
async def get_size_chart(
    size_chart_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> SizeChartPublic:
    doc = await service.get_size_chart(size_chart_id)
    return SizeChartPublic(**doc)


@router.patch(
    "/size-charts/{size_chart_id}",
    response_model=SizeChartPublic,
    summary="Update a size chart — partial",
)
async def update_size_chart(
    size_chart_id: str,
    body: SizeChartUpdate,
    service: ServiceDep,
    admin: AdminDep,
) -> SizeChartPublic:
    doc = await service.update_size_chart(size_chart_id, body, admin)
    return SizeChartPublic(**doc)


@router.delete(
    "/size-charts/{size_chart_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete a size chart",
)
async def delete_size_chart(
    size_chart_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> None:
    await service.delete_size_chart(size_chart_id, admin)
