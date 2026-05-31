"""Single-call helper for recording any stock movement.

Every change to a variant's ``stock_on_hand`` should flow through
``record_movement()`` so the ``inventory_movements`` collection is the
single ledger answering "why did this variant go from 5 to 3?".

The helper is intentionally **passive** — it only writes the audit row,
it does NOT mutate stock. The caller is expected to already have updated
the variant in the same transaction/operation. Decoupling the two lets us
record movements from places that adjust stock through different code
paths (admin patch, payment webhook, cancel/refund, etc.) without
threading the mutation logic through every caller.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger

log = get_logger(__name__)

MovementReason = Literal[
    "admin_adjustment",    # admin edited stock from the UI
    "payment_decrement",   # paid checkout converted holds to committed sales
    "cancel_restock",      # customer/admin cancelled an order → stock returned
    "refund_restock",      # admin refunded → items returned to stock
    "import",              # bulk import / migration
    "system_correction",   # automated reconciliation
]

MovementSource = Literal["admin", "system", "order", "checkout"]


def _movement_id() -> str:
    return f"mov_{secrets.token_hex(8)}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record_movement(
    db: AsyncIOMotorDatabase[Any],
    *,
    variant_id: str,
    product_id: str | None,
    delta: int,
    quantity_after: int,
    reason: MovementReason,
    source_type: MovementSource,
    source_id: str | None = None,
    actor_id: str | None = None,
    note: str | None = None,
) -> str:
    """Insert one movement row. Returns the new ``movement_id``.

    Args:
        variant_id: The variant whose stock just changed.
        product_id: Owning product (cheap denormalisation for ledger queries).
        delta: Signed change. Positive = stock added, negative = stock removed.
        quantity_after: The new ``stock_on_hand`` after the change. Recording
            both delta and final lets queries reconstruct history without
            replaying.
        reason: Categorical reason — see ``MovementReason``.
        source_type: Where the change originated.
        source_id: Identifier of the source (order_id, checkout_session_id,
            admin_id, etc.). Used to follow audit trails.
        actor_id: Admin ID (when ``source_type=admin``) or None for system.
        note: Optional free-form note (e.g. "annual stock take").
    """
    movement_id = _movement_id()
    doc = {
        "movement_id": movement_id,
        "variant_id": variant_id,
        "product_id": product_id,
        "delta": int(delta),
        "quantity_after": int(quantity_after),
        "reason": reason,
        "source_type": source_type,
        "source_id": source_id,
        "actor_id": actor_id,
        "note": note,
        "created_at": _now(),
    }
    await db[C.inventory_movements].insert_one(doc)
    log.info(
        "inventory.movement_recorded",
        variant_id=variant_id,
        delta=delta,
        quantity_after=quantity_after,
        reason=reason,
        source_type=source_type,
    )
    return movement_id


__all__ = ["record_movement", "MovementReason", "MovementSource"]
