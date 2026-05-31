"""Admin order routes (per API.md §12.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from pydantic import BaseModel, Field

from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.admin.deps import AdminDep
from app.modules.admin.orders_schemas import (
    AddressUpdateRequest,
    OrderAdminPublic,
    OrderListResponse,
    OrderTryOnResponse,
    RefundCreateRequest,
    RefundCreateResponse,
    StatusUpdateRequest,
    SupportNoteCreateRequest,
)
from app.modules.admin.orders_service import AdminOrdersService
from app.modules.orders.schemas import OrderRefund

router = APIRouter()


def get_service(db: DbDep) -> AdminOrdersService:
    return AdminOrdersService(db)


ServiceDep = Annotated[AdminOrdersService, Depends(get_service)]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", description="Required for refund creation"),
]


def _to_public(doc: dict) -> OrderAdminPublic:
    return OrderAdminPublic(**doc)


# ── List + read ─────────────────────────────────────────────────────
@router.get(
    "/orders",
    response_model=OrderListResponse,
    summary="List orders with admin filters",
)
async def list_orders(
    service: ServiceDep,
    admin: AdminDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    customer_id: Annotated[str | None, Query()] = None,
    guest_email: Annotated[str | None, Query()] = None,
    order_number: Annotated[str | None, Query()] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    has_custom_design: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderListResponse:
    items, total = await service.list_orders(
        status=status_filter,
        customer_id=customer_id,
        guest_email=guest_email,
        order_number=order_number,
        created_after=created_after,
        created_before=created_before,
        has_custom_design=has_custom_design,
        limit=limit,
        offset=offset,
    )
    return OrderListResponse(
        items=[_to_public(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/orders/{order_id}/custom-designs",
    summary="Inspect the custom-design brief, fabric, and render for an order",
)
async def get_order_custom_designs(
    order_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> dict[str, object]:
    items = await service.get_custom_designs(order_id)
    return {"items": items}


@router.get(
    "/orders/{order_id}",
    response_model=OrderAdminPublic,
    summary="Read a single order (admin — full document)",
)
async def get_order(
    order_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> OrderAdminPublic:
    doc = await service.get_order(order_id)
    return _to_public(doc)


@router.get(
    "/orders/{order_id}/try-ons",
    response_model=OrderTryOnResponse,
    summary="View the AI try-on look(s) + customer photo behind an order's lines",
)
async def get_order_try_ons(
    order_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> OrderTryOnResponse:
    data = await service.get_order_try_ons(order_id)
    return OrderTryOnResponse(**data)


# ── Status ──────────────────────────────────────────────────────────
@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderAdminPublic,
    summary="Move order status — state-machine validated",
)
async def update_status(
    order_id: str,
    body: StatusUpdateRequest,
    service: ServiceDep,
    admin: AdminDep,
) -> OrderAdminPublic:
    updated = await service.update_status(order_id, body, admin)
    return _to_public(updated)


# ── Inventory movements (ledger) ────────────────────────────────────
@router.get(
    "/inventory/movements",
    summary="Inventory movement ledger — newest first",
)
async def list_inventory_movements(
    db: DbDep,
    admin: AdminDep,
    variant_id: Annotated[str | None, Query()] = None,
    product_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    from app.db import C as _C

    query: dict[str, object] = {}
    if variant_id:
        query["variant_id"] = variant_id
    if product_id:
        query["product_id"] = product_id
    total = await db[_C.inventory_movements].count_documents(query)
    cursor = (
        db[_C.inventory_movements]
        .find(query, projection={"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    items = await cursor.to_list(limit)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ── Inventory: current stock per variant ───────────────────────────
@router.get(
    "/inventory/variants",
    summary="Variants with current stock + product context",
)
async def list_inventory_variants(
    db: DbDep,
    admin: AdminDep,
    health: Annotated[
        str | None,
        Query(description="all | low | oos | healthy | untracked"),
    ] = None,
    q: Annotated[str | None, Query(description="Search SKU, title, color")] = None,
    product_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    """Aggregation that joins variants → products and computes a stock_state
    string so the UI can filter by health without recomputing on the client.
    """
    import re as _re
    from app.db import C as _C
    from app.modules.catalog.repository import CatalogRepository

    match: dict[str, object] = {"deleted_at": None}
    if product_id:
        match["product_id"] = product_id
    if q:
        rx = {"$regex": _re.escape(q), "$options": "i"}
        match["$or"] = [
            {"sku": rx},
            {"title": rx},
            {"color": rx},
            {"size": rx},
        ]

    pipeline: list[dict[str, object]] = [
        {"$match": match},
        {
            "$addFields": {
                "stock_on_hand": {"$ifNull": ["$inventory.stock_on_hand", 0]},
                "held_units": {"$ifNull": ["$inventory.held_units", 0]},
                "low_stock_threshold": {
                    "$ifNull": ["$inventory.low_stock_threshold", 5]
                },
                "track_inventory": {
                    "$ifNull": ["$inventory.track_inventory", True]
                },
            }
        },
        {
            "$addFields": {
                "stock_state": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {"$eq": ["$track_inventory", False]},
                                "then": "untracked",
                            },
                            {
                                "case": {"$eq": ["$stock_on_hand", 0]},
                                "then": "oos",
                            },
                            {
                                "case": {
                                    "$lte": [
                                        "$stock_on_hand",
                                        "$low_stock_threshold",
                                    ]
                                },
                                "then": "low",
                            },
                        ],
                        "default": "healthy",
                    }
                }
            }
        },
    ]

    if health and health != "all":
        pipeline.append({"$match": {"stock_state": health}})

    pipeline += [
        {
            "$lookup": {
                "from": _C.products,
                "localField": "product_id",
                "foreignField": "product_id",
                "as": "product",
                "pipeline": [
                    {
                        "$project": {
                            "_id": 0,
                            "title": 1,
                            "slug": 1,
                            "category": 1,
                            "primary_media_asset_id": 1,
                            "status": 1,
                        }
                    }
                ],
            }
        },
        {
            "$addFields": {
                "product": {"$arrayElemAt": ["$product", 0]},
            }
        },
        {
            "$facet": {
                "items": [
                    # Sort: out-of-stock first, then low, then healthy.
                    {
                        "$addFields": {
                            "_state_rank": {
                                "$switch": {
                                    "branches": [
                                        {"case": {"$eq": ["$stock_state", "oos"]}, "then": 0},
                                        {"case": {"$eq": ["$stock_state", "low"]}, "then": 1},
                                        {"case": {"$eq": ["$stock_state", "healthy"]}, "then": 2},
                                    ],
                                    "default": 3,
                                }
                            }
                        }
                    },
                    {"$sort": {"_state_rank": 1, "stock_on_hand": 1}},
                    {"$skip": offset},
                    {"$limit": limit},
                    {"$project": {"_id": 0, "_state_rank": 0}},
                ],
                "total": [{"$count": "n"}],
            }
        },
    ]

    cursor = db[_C.variants].aggregate(pipeline)
    docs = await cursor.to_list(1)
    facet = docs[0] if docs else {"items": [], "total": []}
    items: list[dict[str, object]] = list(facet.get("items") or [])
    total = (facet.get("total") or [{}])[0].get("n", 0) if facet.get("total") else 0

    # Sign product images in one batch.
    catalog_repo = CatalogRepository(db)
    media_ids: list[str] = []
    for it in items:
        prod = it.get("product") or {}
        mid = prod.get("primary_media_asset_id")
        if mid:
            media_ids.append(mid)
    signed = await catalog_repo._sign_media_urls(media_ids)  # noqa: SLF001
    for it in items:
        prod = it.get("product") or {}
        mid = prod.get("primary_media_asset_id")
        prod["primary_image_url"] = signed.get(mid) if mid else None
        it["product"] = prod

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


# ── Shipping address ────────────────────────────────────────────────
@router.patch(
    "/orders/{order_id}/shipping-address",
    response_model=OrderAdminPublic,
    summary="Edit shipping address (pre-shipment only)",
)
async def update_shipping_address(
    order_id: str,
    body: AddressUpdateRequest,
    service: ServiceDep,
    admin: AdminDep,
) -> OrderAdminPublic:
    updated = await service.update_shipping_address(order_id, body, admin)
    return _to_public(updated)


# ── Refunds ─────────────────────────────────────────────────────────
@router.post(
    "/orders/{order_id}/refunds",
    response_model=RefundCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a Stripe refund — Idempotency-Key required",
)
async def create_refund(
    order_id: str,
    body: RefundCreateRequest,
    service: ServiceDep,
    admin: AdminDep,
    idempotency_key: IdempotencyKey = None,
) -> RefundCreateResponse:
    if not idempotency_key:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Missing required Idempotency-Key header.",
            http_status=400,
        )
    refund_doc, updated = await service.create_refund(
        order_id, body, idempotency_key=idempotency_key, admin=admin
    )
    total = int(updated["totals"]["total_amount"])
    total_refunded = sum(int(r["amount"]) for r in updated.get("refunds", []))
    return RefundCreateResponse(
        refund=OrderRefund(**refund_doc),
        new_status=updated["status"],
        total_refunded_amount=total_refunded,
        refundable_remaining=max(0, total - total_refunded),
    )


# ── Returns (admin marks received + auto-refund + restock) ──────────
class ReturnReceiveRequest(BaseModel):
    refund_amount: int | None = Field(
        None,
        ge=0,
        description=(
            "If provided, issues a Stripe refund of this many cents (in"
            " minor units) before transitioning. If omitted, no refund"
            " is issued — admin can refund separately."
        ),
    )
    refund_reason: str | None = Field(None, max_length=80)
    restock: bool = Field(
        True,
        description="When True, restocks the variants on the order's return_request.line_ids.",
    )
    note: str | None = Field(None, max_length=400)


@router.post(
    "/orders/{order_id}/returns/receive",
    response_model=OrderAdminPublic,
    summary="Mark a return as received — restocks + optionally refunds",
)
async def receive_return(
    order_id: str,
    body: ReturnReceiveRequest,
    service: ServiceDep,
    admin: AdminDep,
    idempotency_key: IdempotencyKey = None,
) -> OrderAdminPublic:
    if body.refund_amount and not idempotency_key:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Idempotency-Key header is required when refund_amount is set.",
            http_status=400,
        )
    updated = await service.receive_return(
        order_id,
        admin=admin,
        refund_amount=body.refund_amount,
        refund_reason=body.refund_reason,
        restock=body.restock,
        note=body.note,
        idempotency_key=idempotency_key,
    )
    return _to_public(updated)


# ── Support notes ───────────────────────────────────────────────────
@router.post(
    "/orders/{order_id}/support-notes",
    response_model=OrderAdminPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Append a support note to the order",
)
async def add_support_note(
    order_id: str,
    body: SupportNoteCreateRequest,
    service: ServiceDep,
    admin: AdminDep,
) -> OrderAdminPublic:
    _, updated = await service.add_support_note(order_id, body, admin)
    return _to_public(updated)
