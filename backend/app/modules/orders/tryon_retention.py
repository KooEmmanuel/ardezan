"""Retention pinning for try-on artifacts referenced by an order.

When a customer orders an AI try-on look, fulfillment needs to *see* the
generated look (the customer rendered in the recommended garments) so they can
verify the right items get packed. But anonymous/guest try-on artifacts are
otherwise auto-purged within ~24h by the retention sweeper.

So when an order is created we **pin** the artifacts behind its try-on lines —
clearing their ``expires_at`` so the sweeper leaves them alone — and start a
30-day purge clock only once the order **closes** (delivered / cancelled /
refunded / returned / exchanged). The privacy-respectful default: keep the
evidence through fulfillment + the return window, then let it go.

Registered-customer artifacts already live ``registered_until_deleted`` (the
Fitting Room keeps the customer's own history), so we never touch them here —
pinning/expiring them would wrongly start deleting a customer's saved looks.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger

log = get_logger(__name__)

ORDER_EVIDENCE_RETENTION_DAYS = 30
ORDER_EVIDENCE_POLICY = "order_evidence"

# Statuses that "close" an order and start the 30-day purge clock. A later
# close transition (e.g. delivered → return_requested → returned) refreshes
# the clock, so the evidence always survives the most recent close + 30 days.
CLOSING_STATUSES = frozenset(
    {"delivered", "cancelled", "refunded", "partially_refunded", "returned", "exchanged"}
)


def _now() -> datetime:
    return datetime.now(UTC)


def _ordered_cards_by_session(order_doc: dict[str, Any]) -> dict[str, set[str]]:
    """Map ``try_on_session_id`` → the set of ordered ``try_on_card_id``s.

    An empty set means "the order references the session but not a specific
    card" — we then pin every generated look in that session.
    """
    by_session: dict[str, set[str]] = {}
    for line in order_doc.get("lines", []) or []:
        sid = line.get("try_on_session_id")
        if not sid:
            continue
        by_session.setdefault(sid, set())
        cid = line.get("try_on_card_id")
        if cid:
            by_session[sid].add(cid)
    return by_session


async def pin_order_tryon_artifacts(
    db: AsyncIOMotorDatabase[Any], order_doc: dict[str, Any]
) -> int:
    """Pin the generated look + source photo behind an order's try-on lines.

    Idempotent. Returns the number of ``media_assets`` rows pinned. Only
    touches anonymous/guest sessions — registered sessions are already kept.
    """
    by_session = _ordered_cards_by_session(order_doc)
    if not by_session:
        return 0

    order_id = order_doc["order_id"]
    now = _now()
    pinned = 0

    for session_id, card_ids in by_session.items():
        session = await db[C.try_on_sessions].find_one(
            {"try_on_session_id": session_id}
        )
        if not session:
            continue
        # Registered-customer artifacts are already retained indefinitely.
        if session.get("customer_id"):
            continue

        media_ids: list[str] = []
        source_media_id = session.get("uploaded_media_asset_id")
        if source_media_id:
            media_ids.append(source_media_id)

        gen_image_ids = [
            card["generated_image_id"]
            for card in (session.get("result_cards") or [])
            if card.get("generated_image_id")
            and (not card_ids or card.get("card_id") in card_ids)
        ]
        if gen_image_ids:
            cursor = db[C.generated_images].find(
                {"generated_image_id": {"$in": gen_image_ids}},
                projection={"media_asset_id": 1, "_id": 0},
            )
            async for gi in cursor:
                if gi.get("media_asset_id"):
                    media_ids.append(gi["media_asset_id"])

        if media_ids:
            res = await db[C.media_assets].update_many(
                {
                    "media_asset_id": {"$in": media_ids},
                    "retention.deleted_at": None,
                },
                {
                    "$set": {
                        "retention.policy": ORDER_EVIDENCE_POLICY,
                        "retention.expires_at": None,
                        "retention.order_id": order_id,
                        "retention.order_pinned_at": now,
                        "updated_at": now,
                    }
                },
            )
            pinned += int(res.modified_count or 0)

        # Keep the session document itself from being expired, and tag it so
        # the close step can find it again to start the purge clock.
        await db[C.try_on_sessions].update_one(
            {"try_on_session_id": session_id},
            {
                "$set": {
                    "expires_at": None,
                    "order_evidence_pin": {"order_id": order_id, "pinned_at": now},
                    "updated_at": now,
                }
            },
        )

    if pinned:
        log.info(
            "order.tryon_artifacts_pinned",
            order_id=order_id,
            media_pinned=pinned,
            sessions=len(by_session),
        )
    return pinned


async def set_order_tryon_expiry(
    db: AsyncIOMotorDatabase[Any],
    order_id: str,
    *,
    closed_at: datetime | None = None,
) -> int:
    """Start (or refresh) the 30-day purge clock for an order's pinned
    try-on artifacts. Called when the order reaches a closing status.

    Idempotent and safe to call on orders with no try-on lines (no-op).
    Returns the number of ``media_assets`` rows updated.
    """
    closed_at = closed_at or _now()
    expires_at = closed_at + timedelta(days=ORDER_EVIDENCE_RETENTION_DAYS)
    now = _now()

    res = await db[C.media_assets].update_many(
        {
            "retention.order_id": order_id,
            "retention.policy": ORDER_EVIDENCE_POLICY,
            "retention.deleted_at": None,
        },
        {"$set": {"retention.expires_at": expires_at, "updated_at": now}},
    )
    await db[C.try_on_sessions].update_many(
        {"order_evidence_pin.order_id": order_id},
        {"$set": {"expires_at": expires_at, "updated_at": now}},
    )

    updated = int(res.modified_count or 0)
    if updated:
        log.info(
            "order.tryon_artifacts_expiry_set",
            order_id=order_id,
            media_updated=updated,
            expires_at=expires_at.isoformat(),
        )
    return updated


__all__ = [
    "CLOSING_STATUSES",
    "ORDER_EVIDENCE_POLICY",
    "ORDER_EVIDENCE_RETENTION_DAYS",
    "pin_order_tryon_artifacts",
    "set_order_tryon_expiry",
]
