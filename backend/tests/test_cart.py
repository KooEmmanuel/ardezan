"""Cart revalidation tests (REQ-055).

Revalidation must never trust client-supplied prices/stock: it re-reads the
catalog at call time and classifies every line. These tests pin the status
priority (out_of_stock > low_stock > price_changed > ok), the removed path
for vanished/unpublished items, and the checkout-blocking signal.
"""
from __future__ import annotations

from typing import Any

from app.modules.cart.schemas import CartLineInput
from app.modules.cart.service import CartService
from tests.conftest import make_product, make_variant


def _line(**kw: Any) -> CartLineInput:
    base: dict[str, Any] = {
        "line_id": "line_1",
        "product_id": "prod_test",
        "variant_id": "var_test_m_black",
        "quantity": 1,
    }
    base.update(kw)
    return CartLineInput(**base)


async def _seed(db: Any, **variant_overrides: Any) -> None:
    await db["products"].insert_one(make_product())
    await db["variants"].insert_one(make_variant(**variant_overrides))


async def test_line_ok_in_stock(mock_db: Any) -> None:
    await _seed(mock_db, stock_on_hand=5, price_amount=12900)
    resp = await CartService(mock_db).revalidate(
        [_line(quantity=2, expected_unit_price_amount=12900)]
    )
    line = resp.lines[0]
    assert line.status == "ok"
    assert line.available_quantity == 5
    assert line.line_subtotal_amount == 12900 * 2
    assert resp.any_changes is False
    assert resp.blocks_checkout is False
    assert resp.totals.item_count == 2


async def test_line_price_changed(mock_db: Any) -> None:
    await _seed(mock_db, stock_on_hand=5, price_amount=12900)
    resp = await CartService(mock_db).revalidate(
        [_line(quantity=1, expected_unit_price_amount=9900)]
    )
    assert resp.lines[0].status == "price_changed"
    assert resp.any_changes is True
    assert resp.blocks_checkout is False  # price change alone doesn't block


async def test_line_low_stock_reduces_quantity(mock_db: Any) -> None:
    # 1 available, customer wants 3.
    await _seed(mock_db, stock_on_hand=1, held_units=0)
    resp = await CartService(mock_db).revalidate([_line(quantity=3)])
    line = resp.lines[0]
    assert line.status == "low_stock"
    assert line.available_quantity == 1
    assert line.line_subtotal_amount == 12900 * 1  # charged for available only
    assert resp.blocks_checkout is False
    assert resp.totals.item_count == 1


async def test_line_out_of_stock_blocks_checkout(mock_db: Any) -> None:
    # held_units == stock_on_hand → nothing available for sale.
    await _seed(mock_db, stock_on_hand=2, held_units=2)
    resp = await CartService(mock_db).revalidate([_line(quantity=1)])
    line = resp.lines[0]
    assert line.status == "out_of_stock"
    assert line.available_quantity == 0
    assert line.line_subtotal_amount == 0
    assert resp.blocks_checkout is True
    assert resp.totals.item_count == 0


async def test_line_removed_when_variant_missing(mock_db: Any) -> None:
    # Product exists but the variant was never seeded.
    await mock_db["products"].insert_one(make_product())
    resp = await CartService(mock_db).revalidate([_line(quantity=1)])
    line = resp.lines[0]
    assert line.status == "removed"
    assert resp.blocks_checkout is True


async def test_line_removed_when_product_unpublished(mock_db: Any) -> None:
    await mock_db["products"].insert_one(make_product(status="draft"))
    await mock_db["variants"].insert_one(make_variant())
    resp = await CartService(mock_db).revalidate([_line(quantity=1)])
    assert resp.lines[0].status == "removed"
    assert resp.blocks_checkout is True


async def test_mixed_lines_totals_and_flags(mock_db: Any) -> None:
    await _seed(mock_db, stock_on_hand=5, price_amount=10000)
    resp = await CartService(mock_db).revalidate(
        [
            _line(line_id="line_ok", quantity=2, expected_unit_price_amount=10000),
            _line(line_id="line_price", quantity=1, expected_unit_price_amount=1),
        ]
    )
    statuses = {line.line_id: line.status for line in resp.lines}
    assert statuses["line_ok"] == "ok"
    assert statuses["line_price"] == "price_changed"
    assert resp.any_changes is True
    assert resp.blocks_checkout is False
    # 2 ok units + 1 price-changed unit are all still purchasable.
    assert resp.totals.item_count == 3
    assert resp.totals.subtotal_amount == 10000 * 3
