"""Inventory service — orchestration around the repository.

The repository handles single-hold atomic operations. The service handles
multi-line transactions: reserve every line in a cart, or roll back any
already-created holds.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.errors import ApiError
from app.logging_setup import get_logger
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import InventoryHold, ReservationLine

log = get_logger(__name__)


class InventoryService:
    """High-level inventory operations used by Checkout and the worker."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = InventoryRepository(db)

    async def reserve_for_checkout(
        self,
        lines: Iterable[ReservationLine],
        *,
        checkout_session_id: str,
        ttl_minutes: int,
        cart_id: str | None = None,
        guest_cart_id: str | None = None,
        customer_id: str | None = None,
    ) -> list[InventoryHold]:
        """All-or-nothing: reserve every line, or release everything and raise.

        If any line can't be reserved, all previously created holds in this
        call are released before the ``OUT_OF_STOCK`` is re-raised. The caller
        sees either a full set of holds or a clean failure.
        """
        created: list[InventoryHold] = []
        try:
            for line in lines:
                hold = await self.repo.create_hold(
                    variant_id=line.variant_id,
                    quantity=line.quantity,
                    checkout_session_id=checkout_session_id,
                    ttl_minutes=ttl_minutes,
                    cart_id=cart_id,
                    guest_cart_id=guest_cart_id,
                    customer_id=customer_id,
                )
                created.append(hold)
            return created
        except ApiError:
            # Roll back anything we already created in this call.
            for h in created:
                await self.repo.release_hold(h.hold_id, reason="released")
            raise

    async def commit_checkout(self, checkout_session_id: str) -> int:
        """Commit every active hold for a checkout. Returns the number committed.

        Called by the Stripe webhook handler after ``payment_intent.succeeded``.
        Idempotent: re-running converts only active holds, so a webhook replay
        is safe.
        """
        active = await self.repo.find_active_for_checkout(checkout_session_id)
        committed_count = 0
        for hold in active:
            if await self.repo.commit_hold(hold.hold_id):
                committed_count += 1
        log.info(
            "inventory.checkout_committed",
            checkout_session_id=checkout_session_id,
            active_found=len(active),
            committed=committed_count,
        )
        return committed_count

    async def release_checkout(self, checkout_session_id: str) -> int:
        """Release every active hold for a checkout (e.g. payment failed)."""
        active = await self.repo.find_active_for_checkout(checkout_session_id)
        released_count = 0
        for hold in active:
            if await self.repo.release_hold(hold.hold_id, reason="released"):
                released_count += 1
        log.info(
            "inventory.checkout_released",
            checkout_session_id=checkout_session_id,
            released=released_count,
        )
        return released_count

    async def restock(
        self,
        variant_id: str,
        quantity: int,
        *,
        reason: str = "cancel_restock",
        source_type: str = "order",
        source_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        """Increment ``stock_on_hand`` by ``quantity`` and log a movement.

        Compensating operation used when an order is cancelled or returned:
        the units we previously decremented at payment time go back to
        available stock. Doesn't touch holds (those belong to in-flight
        checkouts, not committed sales).
        """
        if quantity <= 0:
            return
        from app.db import C as _C
        from pymongo import ReturnDocument

        from app.modules.inventory.movements import (
            MovementReason,
            MovementSource,
            record_movement,
        )

        updated = await self.db[_C.variants].find_one_and_update(
            {"variant_id": variant_id},
            {"$inc": {"inventory.stock_on_hand": int(quantity)}},
            return_document=ReturnDocument.AFTER,
            projection={"product_id": 1, "inventory.stock_on_hand": 1},
        )
        if updated is None:
            log.warning(
                "inventory.restock_variant_missing", variant_id=variant_id
            )
            return

        await record_movement(
            self.db,
            variant_id=variant_id,
            product_id=updated.get("product_id"),
            delta=int(quantity),
            quantity_after=int(
                (updated.get("inventory") or {}).get("stock_on_hand", 0)
            ),
            reason=reason,  # type: ignore[arg-type]
            source_type=source_type,  # type: ignore[arg-type]
            source_id=source_id,
            actor_id=actor_id,
        )

        log.info(
            "inventory.restocked", variant_id=variant_id, quantity=int(quantity)
        )

    async def sweep_expired(self, *, batch_size: int = 500) -> int:
        """Mark expired active holds as ``expired`` and decrement held_units.

        Designed to be called repeatedly by the worker cron — bounded batch
        size keeps each run short under unusual backlog.
        """
        expired_ids = await self.repo.find_expired_hold_ids(limit=batch_size)
        released = 0
        for hold_id in expired_ids:
            if await self.repo.release_hold(hold_id, reason="expired"):
                released += 1
        if expired_ids:
            log.info(
                "inventory.sweep_expired",
                found=len(expired_ids),
                released=released,
            )
        return released
