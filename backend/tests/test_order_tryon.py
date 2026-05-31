"""Order → try-on provenance + retention pinning tests.

Covers the fulfillment feature: an admin can view the generated look + source
photo behind an order's try-on lines, and those artifacts are pinned at order
creation (so the otherwise-24h anonymous artifacts survive) and given a 30-day
purge clock only once the order closes.

Key invariants:
- Only the *ordered* card's look is pinned (sibling looks in the same session
  still expire).
- Registered-customer sessions are never touched (their Fitting Room history is
  already retained — pinning/expiring would wrongly start deleting it).
- ``set_order_tryon_expiry`` is idempotent and only affects pinned artifacts.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db import C
from app.modules.orders.tryon_retention import (
    ORDER_EVIDENCE_POLICY,
    ORDER_EVIDENCE_RETENTION_DAYS,
    pin_order_tryon_artifacts,
    set_order_tryon_expiry,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _close(a: datetime, b: datetime, *, seconds: int = 5) -> bool:
    """Compare two datetimes ignoring tz — mongomock returns naive datetimes."""
    an = a.replace(tzinfo=None) if a.tzinfo else a
    bn = b.replace(tzinfo=None) if b.tzinfo else b
    return abs((an - bn).total_seconds()) < seconds


async def _seed_tryon_world(db: Any) -> None:
    """One anonymous session (2 looks) + one registered session (1 look)."""
    soon = _now() + timedelta(minutes=10)

    # media_assets behind everything. Anonymous artifacts carry the short
    # expiry; the registered customer's are kept indefinitely.
    registered = {"ma_src_reg", "ma_look_r"}
    for mid in ("ma_src_anon", "ma_look_a", "ma_look_b", "ma_src_reg", "ma_look_r"):
        is_reg = mid in registered
        await db[C.media_assets].insert_one(
            {
                "media_asset_id": mid,
                "storage": {"object_key": f"tryon/{mid}.jpg"},
                "retention": {
                    "policy": "registered_until_deleted" if is_reg else "anonymous_15_min",
                    "expires_at": None if is_reg else soon,
                    "deleted_at": None,
                },
            }
        )

    await db[C.generated_images].insert_many(
        [
            {"generated_image_id": "gi_a", "media_asset_id": "ma_look_a"},
            {"generated_image_id": "gi_b", "media_asset_id": "ma_look_b"},
            {"generated_image_id": "gi_r", "media_asset_id": "ma_look_r"},
        ]
    )

    await db[C.try_on_sessions].insert_one(
        {
            "try_on_session_id": "tos_anon",
            "customer_id": None,
            "source": "upload",
            "status": "active",
            "uploaded_media_asset_id": "ma_src_anon",
            "expires_at": soon,
            "result_cards": [
                {"card_id": "card_a", "generated_image_id": "gi_a", "outfit_name": "Look A"},
                {"card_id": "card_b", "generated_image_id": "gi_b", "outfit_name": "Look B"},
            ],
        }
    )
    await db[C.try_on_sessions].insert_one(
        {
            "try_on_session_id": "tos_reg",
            "customer_id": "cus_1",
            "source": "saved_photo",
            "status": "active",
            "uploaded_media_asset_id": "ma_src_reg",
            "expires_at": None,
            "result_cards": [
                {"card_id": "card_r", "generated_image_id": "gi_r", "outfit_name": "Look R"},
            ],
        }
    )


def _order_doc() -> dict[str, Any]:
    return {
        "order_id": "ord_1",
        "order_number": "AD-1001",
        "lines": [
            # Anonymous try-on look A is the one that got ordered.
            {
                "line_id": "ol_1",
                "sku": "SKU-A",
                "title_snapshot": "Item A",
                "size": "M",
                "color": "Black",
                "quantity": 1,
                "try_on_session_id": "tos_anon",
                "try_on_card_id": "card_a",
            },
            # A registered-customer try-on look.
            {
                "line_id": "ol_2",
                "sku": "SKU-R",
                "title_snapshot": "Item R",
                "size": "L",
                "color": "Navy",
                "quantity": 1,
                "try_on_session_id": "tos_reg",
                "try_on_card_id": "card_r",
            },
            # A plain catalog line — no try-on.
            {
                "line_id": "ol_3",
                "sku": "SKU-C",
                "title_snapshot": "Item C",
                "size": "S",
                "color": "Cream",
                "quantity": 2,
            },
        ],
    }


async def test_pin_only_ordered_anonymous_look(mock_db: Any) -> None:
    await _seed_tryon_world(mock_db)

    pinned = await pin_order_tryon_artifacts(mock_db, _order_doc())

    # Source photo + ordered look A are pinned; sibling look B is not.
    assert pinned == 2

    src = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_src_anon"})
    look_a = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_a"})
    look_b = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_b"})

    for asset in (src, look_a):
        assert asset["retention"]["policy"] == ORDER_EVIDENCE_POLICY
        assert asset["retention"]["expires_at"] is None  # un-expired → survives sweep
        assert asset["retention"]["order_id"] == "ord_1"

    # The look the customer did NOT order keeps its short anonymous expiry.
    assert look_b["retention"]["policy"] == "anonymous_15_min"
    assert look_b["retention"]["expires_at"] is not None

    # The session is kept alive + tagged for the close step.
    sess = await mock_db[C.try_on_sessions].find_one({"try_on_session_id": "tos_anon"})
    assert sess["expires_at"] is None
    assert sess["order_evidence_pin"]["order_id"] == "ord_1"


async def test_pin_skips_registered_session(mock_db: Any) -> None:
    await _seed_tryon_world(mock_db)
    await pin_order_tryon_artifacts(mock_db, _order_doc())

    # Registered artifacts are already retained — must be untouched.
    reg_look = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_r"})
    reg_src = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_src_reg"})
    assert reg_look["retention"]["policy"] == "registered_until_deleted"
    assert "order_id" not in reg_look["retention"]
    assert reg_src["retention"]["policy"] == "registered_until_deleted"

    reg_sess = await mock_db[C.try_on_sessions].find_one({"try_on_session_id": "tos_reg"})
    assert "order_evidence_pin" not in reg_sess


async def test_expiry_clock_only_affects_pinned(mock_db: Any) -> None:
    await _seed_tryon_world(mock_db)
    await pin_order_tryon_artifacts(mock_db, _order_doc())

    closed_at = _now()
    updated = await set_order_tryon_expiry(mock_db, "ord_1", closed_at=closed_at)
    assert updated == 2  # source + ordered look

    expected = closed_at + timedelta(days=ORDER_EVIDENCE_RETENTION_DAYS)
    src = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_src_anon"})
    look_a = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_a"})
    assert _close(src["retention"]["expires_at"], expected)
    assert _close(look_a["retention"]["expires_at"], expected)

    # Non-pinned + registered assets are never given the order clock.
    look_b = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_b"})
    reg_look = await mock_db[C.media_assets].find_one({"media_asset_id": "ma_look_r"})
    assert look_b["retention"].get("order_id") is None
    assert reg_look["retention"].get("order_id") is None

    sess = await mock_db[C.try_on_sessions].find_one({"try_on_session_id": "tos_anon"})
    assert _close(sess["expires_at"], expected)


async def test_pin_is_noop_without_tryon_lines(mock_db: Any) -> None:
    await _seed_tryon_world(mock_db)
    catalog_only = {
        "order_id": "ord_2",
        "order_number": "AD-1002",
        "lines": [{"line_id": "ol_x", "sku": "SKU-C", "quantity": 1}],
    }
    assert await pin_order_tryon_artifacts(mock_db, catalog_only) == 0
    assert await set_order_tryon_expiry(mock_db, "ord_2") == 0


# ── Admin view ──────────────────────────────────────────────────────
class _FakeStorage:
    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        return f"https://signed.example/{key}?ttl={expires_in}"


async def test_admin_view_returns_look_for_tryon_line(
    mock_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_tryon_world(mock_db)
    # Give the ordered card real items so we can assert they come back.
    await mock_db[C.try_on_sessions].update_one(
        {"try_on_session_id": "tos_anon", "result_cards.card_id": "card_a"},
        {
            "$set": {
                "result_cards.$.rationale": "Clean monochrome layering.",
                "result_cards.$.items": [
                    {
                        "product_id": "prod_a",
                        "variant_id": "var_a",
                        "product_title": "Wool Coat",
                        "category": "Outerwear",
                        "color": "Black",
                        "recommended_size": "M",
                        "selected_size": "M",
                        "price_amount": 24900,
                    }
                ],
            }
        },
    )
    await mock_db[C.orders].insert_one(_order_doc())

    monkeypatch.setattr("app.storage.get_storage", lambda: _FakeStorage())

    from app.modules.admin.orders_service import AdminOrdersService

    service = AdminOrdersService(mock_db)
    result = await service.get_order_try_ons("ord_1")

    assert result["order_id"] == "ord_1"
    # Two of the three lines came from a try-on (the catalog line is excluded).
    assert len(result["looks"]) == 2

    look_a = next(lk for lk in result["looks"] if lk["line_id"] == "ol_1")
    assert look_a["outfit_name"] == "Look A"
    assert look_a["images_available"] is True
    assert look_a["generated_look_image_url"].startswith("https://signed.example/")
    assert look_a["source_photo_url"] is not None
    assert look_a["items"][0]["product_title"] == "Wool Coat"
    assert look_a["session_source"] == "upload"


async def test_admin_view_flags_purged_images(
    mock_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_tryon_world(mock_db)
    # Simulate retention having purged the anonymous look + source photo.
    await mock_db[C.media_assets].update_many(
        {"media_asset_id": {"$in": ["ma_src_anon", "ma_look_a"]}},
        {"$set": {"retention.deleted_at": _now()}},
    )
    await mock_db[C.orders].insert_one(_order_doc())
    monkeypatch.setattr("app.storage.get_storage", lambda: _FakeStorage())

    from app.modules.admin.orders_service import AdminOrdersService

    result = await AdminOrdersService(mock_db).get_order_try_ons("ord_1")
    look_a = next(lk for lk in result["looks"] if lk["line_id"] == "ol_1")
    assert look_a["generated_look_image_url"] is None
    assert look_a["source_photo_url"] is None
    assert look_a["images_available"] is False
