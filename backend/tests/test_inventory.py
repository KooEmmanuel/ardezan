"""Inventory hold tests (REQ-038, REQ-040).

Covers the soft-hold lifecycle and the invariants that protect oversell:
- atomic hold creation with the conditional stock check,
- the last-unit race (two holds for one unit → exactly one wins),
- idempotent release/commit (safe under webhook replay),
- all-or-nothing multi-line reservation,
- the expiry sweep returning held units to availability.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.errors import ApiError, ErrorCode
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import ReservationLine
from app.modules.inventory.service import InventoryService
from tests.conftest import make_variant


async def _seed_variant(db: Any, **overrides: Any) -> None:
    await db["variants"].insert_one(make_variant(**overrides))


async def _held_units(db: Any, variant_id: str = "var_test_m_black") -> int:
    doc = await db["variants"].find_one({"variant_id": variant_id})
    return int(doc["inventory"]["held_units"])


async def _stock_on_hand(db: Any, variant_id: str = "var_test_m_black") -> int:
    doc = await db["variants"].find_one({"variant_id": variant_id})
    return int(doc["inventory"]["stock_on_hand"])


# ── Hold creation ───────────────────────────────────────────────────
async def test_create_hold_reserves_units(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=5)
    repo = InventoryRepository(mock_db)
    hold = await repo.create_hold(
        variant_id="var_test_m_black",
        quantity=2,
        checkout_session_id="cs_1",
        ttl_minutes=15,
    )
    assert hold.status == "active"
    assert hold.quantity == 2
    assert await _held_units(mock_db) == 2


async def test_create_hold_rejects_when_insufficient(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=1)
    repo = InventoryRepository(mock_db)
    with pytest.raises(ApiError) as exc:
        await repo.create_hold(
            variant_id="var_test_m_black",
            quantity=2,
            checkout_session_id="cs_1",
            ttl_minutes=15,
        )
    assert exc.value.code == ErrorCode.OUT_OF_STOCK
    assert await _held_units(mock_db) == 0  # nothing reserved on failure


async def test_create_hold_unknown_variant_raises_not_found(mock_db: Any) -> None:
    repo = InventoryRepository(mock_db)
    with pytest.raises(ApiError) as exc:
        await repo.create_hold(
            variant_id="var_missing",
            quantity=1,
            checkout_session_id="cs_1",
            ttl_minutes=15,
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


async def test_last_unit_race_only_one_wins(mock_db: Any) -> None:
    # The core oversell guard: a single unit, two simultaneous holds.
    await _seed_variant(mock_db, stock_on_hand=1)
    repo = InventoryRepository(mock_db)

    async def attempt() -> str:
        try:
            await repo.create_hold(
                variant_id="var_test_m_black",
                quantity=1,
                checkout_session_id="cs_race",
                ttl_minutes=15,
            )
            return "won"
        except ApiError:
            return "lost"

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == ["lost", "won"]
    assert await _held_units(mock_db) == 1  # never exceeds stock


# ── Release / commit idempotency ────────────────────────────────────
async def test_release_hold_is_idempotent(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=3)
    repo = InventoryRepository(mock_db)
    hold = await repo.create_hold(
        variant_id="var_test_m_black",
        quantity=2,
        checkout_session_id="cs_1",
        ttl_minutes=15,
    )
    assert await repo.release_hold(hold.hold_id) is True
    assert await _held_units(mock_db) == 0
    # Second release is a no-op — does not double-decrement.
    assert await repo.release_hold(hold.hold_id) is False
    assert await _held_units(mock_db) == 0


async def test_commit_hold_decrements_stock_once(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=3)
    repo = InventoryRepository(mock_db)
    hold = await repo.create_hold(
        variant_id="var_test_m_black",
        quantity=2,
        checkout_session_id="cs_1",
        ttl_minutes=15,
    )
    assert await repo.commit_hold(hold.hold_id) is True
    assert await _stock_on_hand(mock_db) == 1  # 3 - 2
    assert await _held_units(mock_db) == 0
    # Replay: committing the same hold again must not decrement stock further.
    assert await repo.commit_hold(hold.hold_id) is False
    assert await _stock_on_hand(mock_db) == 1


# ── Service-level reservation ───────────────────────────────────────
async def test_reserve_for_checkout_all_or_nothing(mock_db: Any) -> None:
    # First line fits (stock 5); second line oversells (stock 1, wants 3).
    await _seed_variant(mock_db, variant_id="var_a", sku="A", stock_on_hand=5)
    await _seed_variant(mock_db, variant_id="var_b", sku="B", stock_on_hand=1)
    service = InventoryService(mock_db)

    with pytest.raises(ApiError) as exc:
        await service.reserve_for_checkout(
            [
                ReservationLine(variant_id="var_a", quantity=2),
                ReservationLine(variant_id="var_b", quantity=3),
            ],
            checkout_session_id="cs_multi",
            ttl_minutes=15,
        )
    assert exc.value.code == ErrorCode.OUT_OF_STOCK
    # The first line's hold must have been rolled back.
    assert await _held_units(mock_db, "var_a") == 0
    assert await _held_units(mock_db, "var_b") == 0


async def test_commit_checkout_is_idempotent_on_replay(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=5)
    service = InventoryService(mock_db)
    await service.reserve_for_checkout(
        [ReservationLine(variant_id="var_test_m_black", quantity=2)],
        checkout_session_id="cs_1",
        ttl_minutes=15,
    )
    first = await service.commit_checkout("cs_1")
    second = await service.commit_checkout("cs_1")  # webhook replay
    assert first == 1
    assert second == 0  # nothing left active to commit
    assert await _stock_on_hand(mock_db) == 3


# ── Expiry sweep ────────────────────────────────────────────────────
async def test_sweep_expired_releases_held_units(mock_db: Any) -> None:
    await _seed_variant(mock_db, stock_on_hand=5)
    repo = InventoryRepository(mock_db)
    hold = await repo.create_hold(
        variant_id="var_test_m_black",
        quantity=2,
        checkout_session_id="cs_1",
        ttl_minutes=15,
    )
    # Force the hold into the past so the sweep picks it up.
    await mock_db["inventory_holds"].update_one(
        {"hold_id": hold.hold_id},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(minutes=1)}},
    )
    released = await InventoryService(mock_db).sweep_expired()
    assert released == 1
    assert await _held_units(mock_db) == 0
    doc = await mock_db["inventory_holds"].find_one({"hold_id": hold.hold_id})
    assert doc["status"] == "expired"
