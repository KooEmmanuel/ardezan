"""MongoDB client lifecycle and index setup.

Every collection name lives in :class:`C` so there's a single place to rename
anything. ``init_db()`` connects and creates indexes idempotently — MongoDB
no-ops when an index with the same name and spec already exists.

Index list mirrors ``DATA_MODEL.md`` sections 4-10. Each entry is
``(collection_name, [IndexModel, ...])``.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo import TEXT as MONGO_TEXT

from app.config import get_settings
from app.logging_setup import get_logger

log = get_logger(__name__)


# ── Collection names (the only place these strings should appear) ───
class C:
    """Canonical collection names."""

    products = "products"
    variants = "variants"
    size_charts = "size_charts"
    media_assets = "media_assets"
    customers = "customers"
    admin_users = "admin_users"
    carts = "carts"
    inventory_holds = "inventory_holds"
    inventory_movements = "inventory_movements"
    checkout_sessions = "checkout_sessions"
    orders = "orders"
    payment_events = "payment_events"
    try_on_sessions = "try_on_sessions"
    ai_jobs = "ai_jobs"
    generated_images = "generated_images"
    audit_logs = "audit_logs"
    analytics_events = "analytics_events"
    settings = "settings"
    fabrics = "fabrics"
    design_sessions = "design_sessions"


# ── Index declarations (mirrors DATA_MODEL.md sections 4-10) ────────
INDEXES: list[tuple[str, list[IndexModel]]] = [
    (
        C.products,
        [
            IndexModel([("product_id", ASCENDING)], unique=True, name="ux_product_id"),
            IndexModel([("slug", ASCENDING)], unique=True, name="ux_slug"),
            IndexModel(
                [("status", ASCENDING), ("category", ASCENDING)], name="ix_status_category"
            ),
            IndexModel([("status", ASCENDING), ("tags", ASCENDING)], name="ix_status_tags"),
            IndexModel(
                [("ai.eligible", ASCENDING), ("status", ASCENDING)],
                name="ix_ai_eligible_status",
            ),
            IndexModel(
                [("title", MONGO_TEXT), ("description", MONGO_TEXT), ("tags", MONGO_TEXT)],
                name="tx_search",
                default_language="english",
            ),
        ],
    ),
    (
        C.variants,
        [
            IndexModel([("variant_id", ASCENDING)], unique=True, name="ux_variant_id"),
            IndexModel([("sku", ASCENDING)], unique=True, name="ux_sku"),
            IndexModel(
                [("product_id", ASCENDING), ("status", ASCENDING)], name="ix_product_status"
            ),
            IndexModel(
                [("product_id", ASCENDING), ("size", ASCENDING), ("color", ASCENDING)],
                name="ix_product_size_color",
            ),
            IndexModel(
                [("status", ASCENDING), ("inventory.stock_on_hand", DESCENDING)],
                name="ix_status_stock",
            ),
        ],
    ),
    (
        C.size_charts,
        [
            IndexModel([("size_chart_id", ASCENDING)], unique=True, name="ux_size_chart_id"),
            IndexModel([("scope", ASCENDING), ("brand", ASCENDING)], name="ix_scope_brand"),
            IndexModel([("product_id", ASCENDING)], name="ix_product"),
        ],
    ),
    (
        C.media_assets,
        [
            IndexModel([("media_asset_id", ASCENDING)], unique=True, name="ux_media_asset_id"),
            IndexModel(
                [("owner_type", ASCENDING), ("owner_id", ASCENDING)], name="ix_owner"
            ),
            IndexModel(
                [("purpose", ASCENDING), ("retention.expires_at", ASCENDING)],
                name="ix_purpose_expiry",
            ),
            IndexModel([("retention.expires_at", ASCENDING)], name="ix_expiry"),
            # Find pinned try-on artifacts for an order when it closes.
            IndexModel(
                [("retention.order_id", ASCENDING)],
                name="ix_retention_order",
                sparse=True,
            ),
        ],
    ),
    (
        C.customers,
        [
            IndexModel([("customer_id", ASCENDING)], unique=True, name="ux_customer_id"),
            IndexModel([("email", ASCENDING)], unique=True, name="ux_email"),
            IndexModel([("deleted_at", ASCENDING)], name="ix_deleted_at"),
        ],
    ),
    (
        C.admin_users,
        [
            IndexModel([("admin_id", ASCENDING)], unique=True, name="ux_admin_id"),
            IndexModel([("email", ASCENDING)], unique=True, name="ux_email"),
            IndexModel(
                [("role", ASCENDING), ("status", ASCENDING)], name="ix_role_status"
            ),
        ],
    ),
    (
        C.carts,
        [
            IndexModel([("cart_id", ASCENDING)], unique=True, name="ux_cart_id"),
            IndexModel(
                [("customer_id", ASCENDING), ("status", ASCENDING)],
                name="ix_customer_status",
            ),
            IndexModel([("updated_at", DESCENDING)], name="ix_updated_at"),
        ],
    ),
    (
        C.inventory_holds,
        [
            IndexModel([("hold_id", ASCENDING)], unique=True, name="ux_hold_id"),
            IndexModel(
                [("checkout_session_id", ASCENDING), ("status", ASCENDING)],
                name="ix_checkout_status",
            ),
            IndexModel(
                [("variant_id", ASCENDING), ("status", ASCENDING)], name="ix_variant_status"
            ),
            IndexModel(
                [("status", ASCENDING), ("expires_at", ASCENDING)],
                name="ix_status_expiry",
            ),
        ],
    ),
    (
        C.inventory_movements,
        [
            IndexModel(
                [("movement_id", ASCENDING)],
                unique=True,
                name="ux_movement_id",
            ),
            # Time-ordered scans for the ledger viewer + product page.
            IndexModel(
                [("variant_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_variant_created_desc",
            ),
            IndexModel(
                [("product_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_product_created_desc",
            ),
            IndexModel([("created_at", DESCENDING)], name="ix_created_desc"),
            IndexModel(
                [("source_type", ASCENDING), ("source_id", ASCENDING)],
                name="ix_source",
            ),
        ],
    ),
    (
        # Not in DATA_MODEL.md §3 originally — added here so in-flight checkout
        # state has a clear home. The webhook handler reads from this collection
        # to drive order creation.
        C.checkout_sessions,
        [
            IndexModel(
                [("checkout_session_id", ASCENDING)],
                unique=True,
                name="ux_checkout_session_id",
            ),
            # Idempotency — same Idempotency-Key returns the same session.
            IndexModel(
                [("idempotency_key", ASCENDING)],
                unique=True,
                sparse=True,
                name="ux_idempotency_key",
            ),
            IndexModel(
                [("stripe_payment_intent_id", ASCENDING)],
                sparse=True,
                name="ix_stripe_intent",
            ),
            IndexModel(
                [("status", ASCENDING), ("expires_at", ASCENDING)],
                name="ix_status_expiry",
            ),
            IndexModel(
                [("customer_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_customer_created",
            ),
            IndexModel(
                [("guest_email", ASCENDING), ("created_at", DESCENDING)],
                name="ix_guest_created",
            ),
        ],
    ),
    (
        C.orders,
        [
            IndexModel([("order_id", ASCENDING)], unique=True, name="ux_order_id"),
            IndexModel([("order_number", ASCENDING)], unique=True, name="ux_order_number"),
            # Second-level idempotency safeguard: a duplicate webhook for the
            # same checkout session can't create two orders. Sparse because
            # manual admin-created orders (M3+) won't carry this field.
            IndexModel(
                [("checkout_session_id", ASCENDING)],
                unique=True,
                sparse=True,
                name="ux_checkout_session_id",
            ),
            IndexModel(
                [("customer_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_customer_created",
            ),
            IndexModel(
                [("guest_email", ASCENDING), ("created_at", DESCENDING)],
                name="ix_guest_created",
            ),
            IndexModel(
                [("status", ASCENDING), ("created_at", DESCENDING)],
                name="ix_status_created",
            ),
            IndexModel(
                [("payment.stripe_payment_intent_id", ASCENDING)], name="ix_stripe_intent"
            ),
            IndexModel(
                [("fulfillment.tracking_number", ASCENDING)], name="ix_tracking"
            ),
        ],
    ),
    (
        C.payment_events,
        [
            # Idempotency: a Stripe replay of the same event must be a no-op (REQ-043).
            IndexModel(
                [("provider", ASCENDING), ("provider_event_id", ASCENDING)],
                unique=True,
                name="ux_provider_event",
            ),
            IndexModel([("related_order_id", ASCENDING)], name="ix_order"),
            IndexModel(
                [("status", ASCENDING), ("received_at", DESCENDING)],
                name="ix_status_received",
            ),
        ],
    ),
    (
        C.try_on_sessions,
        [
            IndexModel(
                [("try_on_session_id", ASCENDING)], unique=True, name="ux_try_on_session_id"
            ),
            IndexModel(
                [("customer_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_customer_created",
            ),
            IndexModel(
                [("anonymous_session_id", ASCENDING), ("expires_at", ASCENDING)],
                name="ix_anon_expiry",
            ),
            IndexModel(
                [("status", ASCENDING), ("expires_at", ASCENDING)],
                name="ix_status_expiry",
            ),
            # Find sessions pinned for an order when it closes.
            IndexModel(
                [("order_evidence_pin.order_id", ASCENDING)],
                name="ix_order_evidence_pin",
                sparse=True,
            ),
        ],
    ),
    (
        C.ai_jobs,
        [
            IndexModel([("job_id", ASCENDING)], unique=True, name="ux_job_id"),
            IndexModel([("try_on_session_id", ASCENDING)], name="ix_session"),
            IndexModel(
                [("customer_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_customer_created",
            ),
            IndexModel(
                [("anonymous_session_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_anon_created",
            ),
            IndexModel(
                [("status", ASCENDING), ("created_at", DESCENDING)],
                name="ix_status_created",
            ),
            IndexModel([("expires_at", ASCENDING)], name="ix_expiry"),
        ],
    ),
    (
        C.generated_images,
        [
            IndexModel(
                [("generated_image_id", ASCENDING)], unique=True, name="ux_image_id"
            ),
            IndexModel([("try_on_session_id", ASCENDING)], name="ix_session"),
            IndexModel([("job_id", ASCENDING)], name="ix_job"),
            IndexModel([("retention.expires_at", ASCENDING)], name="ix_expiry"),
        ],
    ),
    (
        C.audit_logs,
        [
            IndexModel(
                [
                    ("actor_type", ASCENDING),
                    ("actor_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="ix_actor_created",
            ),
            IndexModel(
                [
                    ("target_type", ASCENDING),
                    ("target_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="ix_target_created",
            ),
            IndexModel(
                [("action", ASCENDING), ("created_at", DESCENDING)],
                name="ix_action_created",
            ),
        ],
    ),
    (
        C.analytics_events,
        [
            IndexModel(
                [("event_type", ASCENDING), ("created_at", DESCENDING)],
                name="ix_type_created",
            ),
            IndexModel(
                [("customer_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_customer_created",
            ),
            IndexModel([("try_on_session_id", ASCENDING)], name="ix_session"),
            IndexModel([("order_id", ASCENDING)], name="ix_order"),
        ],
    ),
    (
        C.settings,
        [IndexModel([("key", ASCENDING)], unique=True, name="ux_key")],
    ),
]


# ── Module-level handles populated by ``init_db()`` ─────────────────
_client: AsyncIOMotorClient[Any] | None = None
_db: AsyncIOMotorDatabase[Any] | None = None


def get_db() -> AsyncIOMotorDatabase[Any]:
    """Return the bound database. Raises if ``init_db()`` hasn't run yet."""
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _db


async def init_db() -> None:
    """Connect to MongoDB and ensure every index in ``INDEXES`` exists.

    Idempotent — re-running has no effect on existing indexes.
    """
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongo_url, uuidRepresentation="standard")
    _db = _client[settings.mongo_db]

    log.info("db.connect", url=_safe_url(settings.mongo_url), db=settings.mongo_db)

    for collection_name, indexes in INDEXES:
        coll = _db[collection_name]
        await coll.create_indexes(indexes)
        log.info("db.indexes_ensured", collection=collection_name, count=len(indexes))


async def close_db() -> None:
    """Close the Motor client and clear handles. Safe to call on shutdown."""
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def _safe_url(url: str) -> str:
    """Strip credentials from a connection URL for logging."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url
