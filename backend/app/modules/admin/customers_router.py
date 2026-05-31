"""Admin customer routes — list + detail.

These are READ-only for now. Anything that mutates a customer (name change,
manual email verify, password reset) happens through the customer's own
endpoints. We surface the same data here so the operator can answer
"who is this person" without leaving the admin shell.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import C
from app.deps import DbDep
from app.modules.admin.deps import AdminDep

router = APIRouter()


# ── Response shapes ────────────────────────────────────────────────
class CustomerAdminListItem(BaseModel):
    customer_id: str
    email: str
    name: str
    email_verified: bool = False
    accepts_marketing: bool = False
    has_saved_photo: bool = False
    body_profile_opted_in: bool = False
    addresses_count: int = 0
    orders_count: int = 0
    lifetime_spend_amount: int = 0
    last_order_at: datetime | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class CustomerAdminListResponse(BaseModel):
    items: list[CustomerAdminListItem]
    total: int = 0
    limit: int = 50
    offset: int = 0
    currency: str


class AddressShape(BaseModel):
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    is_default: bool | None = None


class CustomerAdminDetail(BaseModel):
    customer_id: str
    email: str
    name: str
    email_verified_at: datetime | None = None
    accepts_marketing: bool = False
    has_saved_photo: bool = False
    body_profile_opted_in: bool = False
    addresses: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    last_login_at: datetime | None = None
    orders_count: int = 0
    lifetime_spend_amount: int = 0
    last_order_at: datetime | None = None
    currency: str


# ── Helpers ────────────────────────────────────────────────────────
REVENUE_STATUSES = ["paid", "packed", "shipped", "delivered"]


async def _aggregate_customer_stats(
    db, customer_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not customer_ids:
        return {}
    pipeline: list[dict[str, Any]] = [
        {
            "$match": {
                "customer_id": {"$in": customer_ids},
            }
        },
        {
            "$group": {
                "_id": "$customer_id",
                "orders_count": {"$sum": 1},
                "lifetime_spend_amount": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", REVENUE_STATUSES]},
                            "$totals.total_amount",
                            0,
                        ]
                    }
                },
                "last_order_at": {"$max": "$created_at"},
            }
        },
    ]
    out: dict[str, dict[str, Any]] = {}
    async for doc in db[C.orders].aggregate(pipeline):
        out[doc["_id"]] = doc
    return out


# ── Routes ─────────────────────────────────────────────────────────
@router.get(
    "/customers",
    response_model=CustomerAdminListResponse,
    summary="List registered customers (admin)",
)
async def list_customers(
    db: DbDep,
    admin: AdminDep,
    q: Annotated[str | None, Query(description="Search email or name")] = None,
    verified: Annotated[
        str | None,
        Query(description="any | yes | no — email verified filter"),
    ] = None,
    marketing: Annotated[
        str | None,
        Query(description="any | yes | no — marketing opt-in filter"),
    ] = None,
    sort: Annotated[
        str,
        Query(description="recent | spend | orders"),
    ] = "recent",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerAdminListResponse:
    settings = get_settings()

    match: dict[str, Any] = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        match["$or"] = [{"email": rx}, {"name": rx}]
    if verified == "yes":
        match["email_verified_at"] = {"$ne": None}
    elif verified == "no":
        match["email_verified_at"] = None
    if marketing == "yes":
        match["accepts_marketing"] = True
    elif marketing == "no":
        match["accepts_marketing"] = {"$ne": True}

    total = await db[C.customers].count_documents(match)

    base_sort_field = "created_at"
    sort_order = -1
    if sort == "recent":
        base_sort_field = "created_at"
    elif sort == "spend":
        # Spend is computed via $lookup in pipeline below.
        base_sort_field = "lifetime_spend_amount"
    elif sort == "orders":
        base_sort_field = "orders_count"

    # Stage 1: filter + paginate the base list (cheap).
    pipeline: list[dict[str, Any]] = [
        {"$match": match},
        {"$sort": {"created_at": -1}},
    ]
    if sort == "recent":
        pipeline.append({"$skip": offset})
        pipeline.append({"$limit": limit})

    pipeline.append(
        {
            "$lookup": {
                "from": C.orders,
                "let": {"cid": "$customer_id"},
                "as": "_orders",
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$customer_id", "$$cid"]}}},
                    {
                        "$group": {
                            "_id": None,
                            "orders_count": {"$sum": 1},
                            "lifetime_spend_amount": {
                                "$sum": {
                                    "$cond": [
                                        {"$in": ["$status", REVENUE_STATUSES]},
                                        "$totals.total_amount",
                                        0,
                                    ]
                                }
                            },
                            "last_order_at": {"$max": "$created_at"},
                        }
                    },
                ],
            }
        }
    )
    pipeline.append(
        {
            "$addFields": {
                "_agg": {"$arrayElemAt": ["$_orders", 0]},
                "orders_count": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$_orders.orders_count", 0]},
                        0,
                    ]
                },
                "lifetime_spend_amount": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$_orders.lifetime_spend_amount", 0]},
                        0,
                    ]
                },
                "last_order_at": {
                    "$arrayElemAt": ["$_orders.last_order_at", 0]
                },
                "addresses_count": {"$size": {"$ifNull": ["$addresses", []]}},
            }
        }
    )
    pipeline.append({"$project": {"_id": 0, "_orders": 0, "_agg": 0}})

    if sort in {"spend", "orders"}:
        pipeline.append({"$sort": {base_sort_field: sort_order}})
        pipeline.append({"$skip": offset})
        pipeline.append({"$limit": limit})

    docs = await db[C.customers].aggregate(pipeline).to_list(limit)

    items: list[CustomerAdminListItem] = []
    for d in docs:
        items.append(
            CustomerAdminListItem(
                customer_id=d["customer_id"],
                email=d["email"],
                name=d.get("name") or "",
                email_verified=d.get("email_verified_at") is not None,
                accepts_marketing=bool(d.get("accepts_marketing")),
                has_saved_photo=bool(d.get("has_saved_photo")),
                body_profile_opted_in=bool(d.get("body_profile_opted_in")),
                addresses_count=int(d.get("addresses_count") or 0),
                orders_count=int(d.get("orders_count") or 0),
                lifetime_spend_amount=int(d.get("lifetime_spend_amount") or 0),
                last_order_at=d.get("last_order_at"),
                created_at=d["created_at"],
                last_login_at=d.get("last_login_at"),
            )
        )

    return CustomerAdminListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        currency=settings.store_currency,
    )


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerAdminDetail,
    summary="Customer detail with order aggregates",
)
async def get_customer(
    customer_id: str,
    db: DbDep,
    admin: AdminDep,
) -> CustomerAdminDetail:
    from fastapi import HTTPException

    settings = get_settings()

    doc = await db[C.customers].find_one({"customer_id": customer_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")

    stats = await _aggregate_customer_stats(db, [customer_id])
    s = stats.get(customer_id, {})

    return CustomerAdminDetail(
        customer_id=doc["customer_id"],
        email=doc["email"],
        name=doc.get("name") or "",
        email_verified_at=doc.get("email_verified_at"),
        accepts_marketing=bool(doc.get("accepts_marketing")),
        has_saved_photo=bool(doc.get("has_saved_photo")),
        body_profile_opted_in=bool(doc.get("body_profile_opted_in")),
        addresses=list(doc.get("addresses") or []),
        created_at=doc["created_at"],
        last_login_at=doc.get("last_login_at"),
        orders_count=int(s.get("orders_count") or 0),
        lifetime_spend_amount=int(s.get("lifetime_spend_amount") or 0),
        last_order_at=s.get("last_order_at"),
        currency=settings.store_currency,
    )


@router.get(
    "/customers/{customer_id}/orders",
    summary="Recent orders for a customer",
)
async def list_customer_orders(
    customer_id: str,
    db: DbDep,
    admin: AdminDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    cursor = (
        db[C.orders]
        .find(
            {"customer_id": customer_id},
            projection={"_id": 0},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    items = await cursor.to_list(limit)
    # Project just what the customer detail page needs.
    trimmed: list[dict[str, Any]] = []
    for o in items:
        trimmed.append(
            {
                "order_id": o.get("order_id"),
                "order_number": o.get("order_number"),
                "status": o.get("status"),
                "created_at": o.get("created_at"),
                "total_amount": (o.get("totals") or {}).get("total_amount", 0),
                "currency": (o.get("totals") or {}).get("currency", "USD"),
                "line_count": len(o.get("lines") or []),
            }
        )
    return {"items": trimmed, "total": len(trimmed)}
