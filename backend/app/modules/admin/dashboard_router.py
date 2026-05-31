"""Admin dashboard metrics endpoint.

Single round-trip ``GET /admin/dashboard`` aggregates the KPIs the shell
shows at the top of the home page. Heavy reads stay server-side and the
client renders KPI tiles + a sparkline without N+1 calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import C
from app.deps import DbDep
from app.modules.admin.deps import AdminDep

router = APIRouter()


class DashboardMetrics(BaseModel):
    currency: str
    revenue_today_amount: int = 0
    revenue_week_amount: int = 0
    orders_today_count: int = 0
    orders_week_count: int = 0
    orders_pending_fulfillment: int = 0
    orders_pending_payment: int = 0
    low_stock_variant_count: int = 0
    out_of_stock_variant_count: int = 0
    active_products_count: int = 0
    draft_products_count: int = 0
    refunds_pending_count: int = 0
    revenue_sparkline: list[int] = Field(
        default_factory=list,
        description="Last 14 days of revenue totals (oldest first).",
    )


REVENUE_STATUSES = ["paid", "packed", "shipped", "delivered"]
PENDING_FULFILLMENT_STATUSES = ["paid", "packed"]


def get_db(db: DbDep) -> AsyncIOMotorDatabase[Any]:
    return db


DbAdminDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_db)]


@router.get(
    "/dashboard",
    response_model=DashboardMetrics,
    summary="Aggregated dashboard KPIs",
)
async def get_dashboard_metrics(
    db: DbAdminDep,
    admin: AdminDep,
) -> DashboardMetrics:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)
    sparkline_start = today_start - timedelta(days=13)

    orders = db[C.orders]
    products = db[C.products]
    variants = db[C.variants]

    # ── Revenue & order counts (today + last 7d) ──
    revenue_pipeline: list[dict[str, Any]] = [
        {
            "$match": {
                "created_at": {"$gte": week_start},
                "status": {"$in": REVENUE_STATUSES},
            }
        },
        {
            "$group": {
                "_id": {
                    "is_today": {"$gte": ["$created_at", today_start]},
                },
                "total": {"$sum": "$totals.total_amount"},
                "count": {"$sum": 1},
            }
        },
    ]
    revenue_today = 0
    revenue_week = 0
    orders_today = 0
    orders_week = 0
    async for doc in orders.aggregate(revenue_pipeline):
        revenue_week += int(doc.get("total") or 0)
        orders_week += int(doc.get("count") or 0)
        if (doc.get("_id") or {}).get("is_today"):
            revenue_today += int(doc.get("total") or 0)
            orders_today += int(doc.get("count") or 0)

    # ── Pending fulfillment + pending payment ──
    orders_pending_fulfillment = await orders.count_documents(
        {"status": {"$in": PENDING_FULFILLMENT_STATUSES}}
    )
    orders_pending_payment = await orders.count_documents(
        {"status": "pending_payment"}
    )

    # ── Refunds pending (return_requested orders not yet refunded) ──
    refunds_pending = await orders.count_documents({"status": "return_requested"})

    # ── Variant stock health ──
    stock_pipeline: list[dict[str, Any]] = [
        {"$match": {"deleted_at": None}},
        {
            "$project": {
                "_id": 0,
                "stock_on_hand": {
                    "$ifNull": ["$inventory.stock_on_hand", 0]
                },
                "low_stock_threshold": {
                    "$ifNull": ["$inventory.low_stock_threshold", 5]
                },
                "track_inventory": {
                    "$ifNull": ["$inventory.track_inventory", True]
                },
            }
        },
        {
            "$group": {
                "_id": None,
                "low": {
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
                "oos": {
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
            }
        },
    ]
    low_stock = 0
    oos_count = 0
    async for doc in variants.aggregate(stock_pipeline):
        low_stock = int(doc.get("low") or 0)
        oos_count = int(doc.get("oos") or 0)

    # ── Product counts ──
    active_products = await products.count_documents(
        {"status": "published", "deleted_at": None}
    )
    draft_products = await products.count_documents(
        {"status": "draft", "deleted_at": None}
    )

    # ── 14-day revenue sparkline ──
    sparkline_pipeline: list[dict[str, Any]] = [
        {
            "$match": {
                "created_at": {"$gte": sparkline_start},
                "status": {"$in": REVENUE_STATUSES},
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                    }
                },
                "total": {"$sum": "$totals.total_amount"},
            }
        },
    ]
    by_day: dict[str, int] = {}
    async for doc in orders.aggregate(sparkline_pipeline):
        by_day[doc["_id"]] = int(doc.get("total") or 0)
    sparkline: list[int] = []
    for offset in range(14):
        day = (sparkline_start + timedelta(days=offset)).strftime("%Y-%m-%d")
        sparkline.append(by_day.get(day, 0))

    return DashboardMetrics(
        currency=settings.store_currency,
        revenue_today_amount=revenue_today,
        revenue_week_amount=revenue_week,
        orders_today_count=orders_today,
        orders_week_count=orders_week,
        orders_pending_fulfillment=orders_pending_fulfillment,
        orders_pending_payment=orders_pending_payment,
        low_stock_variant_count=low_stock,
        out_of_stock_variant_count=oos_count,
        active_products_count=active_products,
        draft_products_count=draft_products,
        refunds_pending_count=refunds_pending,
        revenue_sparkline=sparkline,
    )
