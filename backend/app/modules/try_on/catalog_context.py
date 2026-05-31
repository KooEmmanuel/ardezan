"""CatalogContext builder.

Per ARCHITECTURE.md §8.4 + ADR-003, the Recommender NEVER receives raw DB
access. We build a bounded, sanitised view of the catalog filtered to:

- ``status = published`` and ``deleted_at = None``
- ``ai.eligible = true``
- at least one variant with ``available_for_sale > 0``

A seeded product (when a customer clicks "Try this on you" from a PDP) is
always included if eligible. The remaining slots are filled up to
``max_candidates``.

The output is a plain dict that gets serialised into the prompt — keeping
it small enough that the model can actually reason over it.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.logging_setup import get_logger
from app.modules.try_on.schemas import TryOnInputs

log = get_logger(__name__)

CONTEXT_VERSION = "2026-05-28"


def _available_for_sale(variant_doc: dict[str, Any]) -> int:
    inv = variant_doc.get("inventory", {}) or {}
    stock = int(inv.get("stock_on_hand", 0))
    held = int(inv.get("held_units", 0))
    return max(0, stock - held)


async def build_catalog_context(
    db: AsyncIOMotorDatabase[Any],
    *,
    body_profile: dict[str, Any],
    inputs: TryOnInputs,
    seeded_product_id: str | None = None,
    max_candidates: int = 60,
    max_outfits: int = 10,
    max_items_per_outfit: int = 4,
) -> dict[str, Any]:
    """Return the bounded context the Recommender sees."""
    base_query: dict[str, Any] = {
        "status": "published",
        "deleted_at": None,
        "ai.eligible": True,
    }

    # Always include the seeded product if present and eligible.
    seeded_doc: dict[str, Any] | None = None
    if seeded_product_id:
        seeded_doc = await db[C.products].find_one(
            {**base_query, "product_id": seeded_product_id}
        )

    # Top candidates by recency. (Real ranking comes when we have telemetry.)
    cursor = (
        db[C.products]
        .find(base_query)
        .sort("updated_at", -1)
        .limit(max_candidates)
    )
    candidate_docs: list[dict[str, Any]] = await cursor.to_list(max_candidates)

    if seeded_doc is not None:
        existing_ids = {p["product_id"] for p in candidate_docs}
        if seeded_doc["product_id"] not in existing_ids:
            # Insert seeded first; drop the oldest if we're at the cap.
            candidate_docs = [seeded_doc] + candidate_docs[: max_candidates - 1]

    if not candidate_docs:
        return _empty_context(body_profile, inputs, seeded_product_id, max_outfits, max_items_per_outfit)

    # Pull variants for all candidates in one query.
    product_ids = [p["product_id"] for p in candidate_docs]
    variants_by_product: dict[str, list[dict[str, Any]]] = {}
    async for v in db[C.variants].find(
        {
            "product_id": {"$in": product_ids},
            "status": "active",
            "deleted_at": None,
        }
    ):
        variants_by_product.setdefault(v["product_id"], []).append(v)

    candidates: list[dict[str, Any]] = []
    for p in candidate_docs:
        variant_list: list[dict[str, Any]] = []
        for v in variants_by_product.get(p["product_id"], []):
            available = _available_for_sale(v)
            if available <= 0:
                continue
            variant_list.append(
                {
                    "variant_id": v["variant_id"],
                    "sku": v.get("sku"),
                    "size": v["size"],
                    "color": v["color"],
                    "color_hex": v.get("color_hex"),
                    "available_for_sale": available,
                }
            )

        if not variant_list:
            continue  # no in-stock variants — skip the product entirely

        pricing = p.get("pricing") or {}
        ai_meta = p.get("ai") or {}
        candidates.append(
            {
                "product_id": p["product_id"],
                "title": p["title"],
                "category": p["category"],
                "subcategory": p.get("subcategory"),
                "price_amount": int(pricing.get("base_price_amount", 0)),
                "sale_price_amount": pricing.get("compare_at_price_amount"),
                "currency": pricing.get("currency") or "USD",
                "fabric_type": ai_meta.get("fabric_type"),
                "formality": ai_meta.get("formality"),
                "fit_shape": ai_meta.get("fit_shape"),
                "season": ai_meta.get("season"),
                "color_palette": ai_meta.get("color_palette", []),
                "compatibility_tags": ai_meta.get("compatibility_tags", []),
                "variants": variant_list,
            }
        )

    log.info(
        "context.built",
        candidates=len(candidates),
        max_candidates=max_candidates,
        seeded=seeded_product_id,
    )
    return {
        "version": CONTEXT_VERSION,
        "body_profile_summary": {
            "body_shape": body_profile.get("body_shape"),
            "estimated_measurements": {
                "height_cm": body_profile.get("estimated_height_cm"),
                "chest_cm": body_profile.get("estimated_chest_cm"),
                "waist_cm": body_profile.get("estimated_waist_cm"),
                "hip_cm": body_profile.get("estimated_hip_cm"),
                "inseam_cm": body_profile.get("estimated_inseam_cm"),
            },
            "skin_undertone": body_profile.get("skin_undertone"),
            "current_style_notes": body_profile.get("current_style_notes"),
            "fit_preference": inputs.fit_preference,
            "occasion": inputs.occasion,
            "customer_prompt": inputs.prompt,
        },
        "candidates": candidates,
        "constraints": {
            "max_outfits": max_outfits,
            "max_items_per_outfit": max_items_per_outfit,
            "excluded_product_ids": [],
            "seeded_product_id": seeded_product_id,
        },
    }


def _empty_context(
    body_profile: dict[str, Any],
    inputs: TryOnInputs,
    seeded_product_id: str | None,
    max_outfits: int,
    max_items_per_outfit: int,
) -> dict[str, Any]:
    return {
        "version": CONTEXT_VERSION,
        "body_profile_summary": {
            "body_shape": body_profile.get("body_shape"),
            "fit_preference": inputs.fit_preference,
            "occasion": inputs.occasion,
        },
        "candidates": [],
        "constraints": {
            "max_outfits": max_outfits,
            "max_items_per_outfit": max_items_per_outfit,
            "excluded_product_ids": [],
            "seeded_product_id": seeded_product_id,
        },
    }
