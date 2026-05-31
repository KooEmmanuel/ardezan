"""Shared test fixtures.

Provides an in-memory MongoDB (via ``mongomock-motor``) so the inventory,
cart, and webhook suites can exercise real persistence logic — atomic holds,
unique-index idempotency, cursor reads — without a live database.

The mock database is also bound to ``app.db`` module globals so code paths
that call ``get_db()`` directly (e.g. the webhook handler) see the same
instance as code paths that take ``db`` as a constructor argument.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from pymongo import ASCENDING, IndexModel

import app.db as appdb
from app.db import C


def _now() -> datetime:
    return datetime.now(UTC)


# Only the indexes the tests rely on. We avoid the full INDEXES list because
# mongomock does not implement text indexes, and the suites here only need
# uniqueness guarantees (idempotency) and ordinary lookups.
_TEST_INDEXES: list[tuple[str, list[IndexModel]]] = [
    (
        C.payment_events,
        [
            IndexModel(
                [("provider", ASCENDING), ("provider_event_id", ASCENDING)],
                unique=True,
                name="ux_provider_event",
            ),
        ],
    ),
    (
        C.variants,
        [IndexModel([("variant_id", ASCENDING)], unique=True, name="ux_variant_id")],
    ),
    (
        C.products,
        [IndexModel([("product_id", ASCENDING)], unique=True, name="ux_product_id")],
    ),
    (
        C.inventory_holds,
        [IndexModel([("hold_id", ASCENDING)], unique=True, name="ux_hold_id")],
    ),
]


@pytest_asyncio.fixture
async def mock_db() -> AsyncIterator[Any]:
    """Fresh in-memory database per test, bound to ``app.db`` globals."""
    client: Any = AsyncMongoMockClient()
    db = client["ardezan_test"]

    for collection_name, indexes in _TEST_INDEXES:
        await db[collection_name].create_indexes(indexes)

    prev_client, prev_db = appdb._client, appdb._db
    appdb._client, appdb._db = client, db
    try:
        yield db
    finally:
        appdb._client, appdb._db = prev_client, prev_db


def make_variant(
    *,
    variant_id: str = "var_test_m_black",
    product_id: str = "prod_test",
    sku: str = "TEST-BLK-M",
    size: str = "M",
    color: str = "Black",
    price_amount: int = 12900,
    stock_on_hand: int = 5,
    held_units: int = 0,
    status: str = "active",
) -> dict[str, Any]:
    """A variant document shaped like the catalog fixtures expect."""
    now = _now()
    return {
        "variant_id": variant_id,
        "product_id": product_id,
        "sku": sku,
        "title": None,
        "size": size,
        "color": color,
        "color_hex": "#0a0a0a",
        "status": status,
        "pricing": {
            "price_amount": price_amount,
            "compare_at_price_amount": None,
            "currency": "USD",
        },
        "inventory": {
            "stock_on_hand": stock_on_hand,
            "held_units": held_units,
            "committed_units": 0,
            "low_stock_threshold": 3,
            "track_inventory": True,
        },
        "measurements": {"unit": "cm"},
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def make_product(
    *,
    product_id: str = "prod_test",
    slug: str = "test-product",
    title: str = "Test Product",
    price_amount: int = 12900,
    status: str = "published",
) -> dict[str, Any]:
    now = _now()
    return {
        "product_id": product_id,
        "slug": slug,
        "title": title,
        "description": "A test product.",
        "category": "Outerwear",
        "subcategory": None,
        "tags": ["test"],
        "status": status,
        "publication": {"published_at": now, "unpublished_at": None},
        "pricing": {
            "base_price_amount": price_amount,
            "compare_at_price_amount": None,
            "currency": "USD",
        },
        "media_asset_ids": [],
        "primary_media_asset_id": None,
        "ai_friendly_media_asset_ids": [],
        "product_details": {},
        "size_chart_id": None,
        "ai": {"eligible": True},
        "seo": {},
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
