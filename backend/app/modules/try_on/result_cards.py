"""Result-card construction.

The Recommender returns outfits referring to product_id + variant_id. Result
cards are the customer-visible shape (DATA_MODEL §9.1) — they include
display-ready fields (size labels, prices, rationale) so the frontend can
render the try-on grid without further lookups, and a ``status`` per card so
add-to-cart UI can prompt for swaps when something is partially unavailable.

``generated_image_id`` is left ``None`` here — the Designer (M4.4) fills it
once each outfit has been rendered onto the customer photo.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger
from app.modules.try_on.agent_schemas import RecommendedOutfit

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _card_id() -> str:
    return f"card_{secrets.token_hex(6)}"


def build_result_cards(
    outfits: list[RecommendedOutfit],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert validated outfits into persistable result cards.

    Assumes outfits have already been post-validated against the context —
    every product_id and variant_id is guaranteed to exist.
    """
    products_by_id = {p["product_id"]: p for p in context["candidates"]}
    variant_lookup: dict[str, dict[str, Any]] = {}
    for p in context["candidates"]:
        for v in p["variants"]:
            variant_lookup[v["variant_id"]] = v

    cards: list[dict[str, Any]] = []
    for outfit in outfits:
        items_payload: list[dict[str, Any]] = []
        total_amount = 0
        currency = "USD"
        any_low_stock = False

        for item in outfit.items:
            product = products_by_id.get(item.product_id)
            variant = variant_lookup.get(item.variant_id)
            if product is None or variant is None:
                continue
            price = int(product["price_amount"])
            currency = product.get("currency") or currency
            total_amount += price
            if int(variant.get("available_for_sale", 0)) <= 0:
                any_low_stock = True
            items_payload.append(
                {
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "product_title": product.get("title"),
                    "category": product.get("category"),
                    "color": variant.get("color"),
                    "color_hex": variant.get("color_hex"),
                    "recommended_size": variant["size"],
                    "selected_size": variant["size"],
                    "price_amount": price,
                    "compare_at_price_amount": product.get("sale_price_amount"),
                    "rationale": item.rationale,
                }
            )

        if not items_payload:
            continue

        cards.append(
            {
                "card_id": _card_id(),
                "outfit_name": outfit.outfit_name,
                "rationale": outfit.rationale,
                "generated_image_id": None,
                "total_amount": total_amount,
                "currency": currency,
                "disclaimer_shown": True,
                "ai_preview_label_shown": True,
                "items": items_payload,
                "status": "partially_unavailable" if any_low_stock else "available",
            }
        )

    return cards


async def persist_result_cards(
    db: AsyncIOMotorDatabase[Any],
    try_on_session_id: str,
    cards: list[dict[str, Any]],
) -> None:
    await db[C.try_on_sessions].update_one(
        {"try_on_session_id": try_on_session_id},
        {"$set": {"result_cards": cards, "updated_at": _now()}},
    )
    log.info(
        "result_cards.persisted",
        try_on_session_id=try_on_session_id,
        count=len(cards),
    )
