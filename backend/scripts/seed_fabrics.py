"""Seed the fabric library that anchors the Design Me flow.

We keep this list tight and curated — six fabrics span the natural
range a customer might want for a custom piece (light shirt → heavy
overcoat → denim → cashmere). Each fabric has a swatch gradient so the
picker renders without needing image uploads.

Run:
    .venv/bin/python -m scripts.seed_fabrics            # idempotent upsert
    .venv/bin/python -m scripts.seed_fabrics --force    # rewrite even if present
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C


# (cost_per_yard_amount is in USD cents.)
FABRICS: list[dict] = [
    {
        "fabric_id": "fab_italian_linen",
        "name": "Italian Linen",
        "description": (
            "Lightweight, breathable linen woven in Italy. Falls softly, "
            "wears in beautifully — ideal for warm-weather shirts and dresses."
        ),
        "color_family": "warm-neutrals",
        "cost_per_yard_amount": 4_500,
        "suitable_for": ["shirt", "blouse", "dress", "blazer", "overshirt"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #e8dcc4 0%, #d4c5a0 50%, #b8a679 100%)",
        },
        "weight": "light",
        "finish": "matte",
    },
    {
        "fabric_id": "fab_wool_flannel",
        "name": "Wool Flannel",
        "description": (
            "A medium-heavy English wool flannel with a brushed surface. "
            "Holds its shape, drapes cleanly — built for trousers, blazers, "
            "and outerwear."
        ),
        "color_family": "cool-neutrals",
        "cost_per_yard_amount": 6_500,
        "suitable_for": ["trouser", "blazer", "coat", "skirt"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #5a5a5a 0%, #3e3e44 50%, #2a2a30 100%)",
        },
        "weight": "heavy",
        "finish": "brushed",
    },
    {
        "fabric_id": "fab_khaki_twill",
        "name": "Khaki Twill",
        "description": (
            "Mid-weight cotton twill with a structured hand and a clean "
            "diagonal weave. The workhorse fabric — pairs with almost any "
            "trouser, shirt, or jacket."
        ),
        "color_family": "warm-neutrals",
        "cost_per_yard_amount": 2_800,
        "suitable_for": ["trouser", "shirt", "jacket", "overshirt", "skirt"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #c8b290 0%, #a8916b 50%, #7a6647 100%)",
        },
        "weight": "medium",
        "finish": "structured",
    },
    {
        "fabric_id": "fab_cotton_poplin",
        "name": "Cotton Poplin",
        "description": (
            "Crisp, smooth cotton poplin with a fine plain weave. Holds a "
            "press, breathes well, photographs cleanly — the classic "
            "shirting choice."
        ),
        "color_family": "cool-neutrals",
        "cost_per_yard_amount": 2_200,
        "suitable_for": ["shirt", "blouse", "dress"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #ffffff 0%, #f3f3f5 50%, #dadce0 100%)",
        },
        "weight": "light",
        "finish": "matte",
    },
    {
        "fabric_id": "fab_japanese_denim",
        "name": "Japanese Denim",
        "description": (
            "Selvedge denim from Okayama — slubby texture, deep indigo, "
            "ages with character. Heavy enough for outerwear, refined "
            "enough for trousers."
        ),
        "color_family": "denim",
        "cost_per_yard_amount": 3_800,
        "suitable_for": ["trouser", "jacket", "overshirt", "skirt"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #4a5a78 0%, #2e3c5a 50%, #1a2440 100%)",
        },
        "weight": "medium",
        "finish": "structured",
    },
    {
        "fabric_id": "fab_cashmere",
        "name": "Italian Cashmere",
        "description": (
            "Pure cashmere, woven in Biella. Lustrous surface, exceptional "
            "drape, warm without weight — the fabric for a coat or blazer "
            "you keep for a decade."
        ),
        "color_family": "rich-tones",
        "cost_per_yard_amount": 12_000,
        "suitable_for": ["coat", "blazer", "overshirt"],
        "swatch": {
            "gradient": "linear-gradient(135deg, #6b4a3a 0%, #4a2e22 50%, #2e1a14 100%)",
        },
        "weight": "medium",
        "finish": "lustrous",
    },
    # Hand-woven and printed African cloths. These anchor the brand —
    # most Bespoke customers come for a Kente or Ankara piece first.
    {
        "fabric_id": "fab_kente",
        "name": "Hand-woven Kente",
        "description": (
            "Hand-woven Ghanaian Kente strip-cloth in the traditional "
            "Bonwire weave — bold geometric blocks in saffron yellow, "
            "vermillion, emerald, and ink. Each yard is a single artisan's "
            "morning at the loom. Reads as ceremony."
        ),
        "color_family": "rich-tones",
        "cost_per_yard_amount": 9_500,
        "suitable_for": [
            "dress", "skirt", "blazer", "jacket", "shirt", "overshirt",
        ],
        "swatch": {
            "gradient": (
                "linear-gradient(135deg, #e8b923 0%, #c83a2a 30%, "
                "#1f7a3a 60%, #1c1c2e 100%)"
            ),
        },
        "weight": "medium",
        "finish": "structured",
    },
    {
        "fabric_id": "fab_ankara",
        "name": "Ankara Wax Print",
        "description": (
            "Vibrant West African wax-print cotton with a rich, "
            "high-contrast pattern — saturated indigo, vermillion, and "
            "amber on cream. Crisp, breathable, holds its colour through "
            "decades of wear."
        ),
        "color_family": "rich-tones",
        "cost_per_yard_amount": 4_200,
        "suitable_for": [
            "dress", "skirt", "shirt", "blouse", "blazer", "overshirt", "trouser",
        ],
        "swatch": {
            "gradient": (
                "linear-gradient(135deg, #f4d68a 0%, #d96a1f 35%, "
                "#9d2727 65%, #1a3a8c 100%)"
            ),
        },
        "weight": "light",
        "finish": "matte",
    },
]


async def main(force: bool) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    coll = db[C.fabrics]

    # An index on fabric_id makes the lookup in the router cheap.
    await coll.create_index("fabric_id", unique=True)

    now = datetime.now(UTC)
    inserted = updated = skipped = 0

    for raw in FABRICS:
        existing = await coll.find_one({"fabric_id": raw["fabric_id"]})
        doc = {
            **raw,
            "currency": "USD",
            "active": True,
            "updated_at": now,
        }
        if existing is None:
            doc["created_at"] = now
            await coll.insert_one(doc)
            inserted += 1
            print(f"  inserted   {raw['fabric_id']}  {raw['name']}")
        elif force:
            doc["created_at"] = existing.get("created_at", now)
            await coll.replace_one({"fabric_id": raw["fabric_id"]}, doc)
            updated += 1
            print(f"  rewrote    {raw['fabric_id']}  {raw['name']}")
        else:
            skipped += 1
            print(f"  unchanged  {raw['fabric_id']}  {raw['name']}")

    print()
    print(f"Inserted: {inserted}   Rewrote: {updated}   Unchanged: {skipped}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing fabrics with the canonical seed data.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(force=args.force)))
