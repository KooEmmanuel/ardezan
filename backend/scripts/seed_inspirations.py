"""Seed the design_inspirations collection from the original curated set.

The 9 existing inspirations were hardcoded in the frontend; their hero
images already live at ``frontend/public/bespoke/<id>.png`` (CDN-served).
This script writes them to Mongo with ``static_image_path`` pointing at
those bundled assets so the admin can edit / replace / hide them
without a code push, but the live site still serves the pre-rendered
photos out of the box.

Idempotent: skips entries already in the collection unless ``--force``.

Run::

    .venv/bin/python -m scripts.seed_inspirations          # insert missing
    .venv/bin/python -m scripts.seed_inspirations --force  # rewrite all
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C


SEED: list[dict[str, Any]] = [
    {
        "inspiration_id": "ins_linen_shirt",
        "fabric_id": "fab_italian_linen",
        "piece_type": "shirt",
        "complexity": "standard",
        "title": "Camp-collar linen shirt",
        "tagline": "Open-collar shirt in lightweight Italian linen.",
        "brief": (
            "Camp-collar shirt, short sleeves, single chest pocket, "
            "mother-of-pearl buttons. Boxy through the body."
        ),
        "fit_note": "Relaxed, falls just past the hip.",
        "sort_order": 10,
    },
    {
        "inspiration_id": "ins_wool_blazer",
        "fabric_id": "fab_wool_flannel",
        "piece_type": "blazer",
        "complexity": "intricate",
        "title": "Unstructured wool blazer",
        "tagline": "Single-breasted blazer in soft English wool flannel.",
        "brief": (
            "Single-breasted, notched lapels, two-button closure, "
            "soft shoulder, side vents, working cuffs."
        ),
        "fit_note": "Tailored at the waist, slight taper.",
        "sort_order": 20,
    },
    {
        "inspiration_id": "ins_khaki_trouser",
        "fabric_id": "fab_khaki_twill",
        "piece_type": "trouser",
        "complexity": "standard",
        "title": "Pleated khaki trouser",
        "tagline": "Pleated trouser cut from structured cotton twill.",
        "brief": (
            "Double-pleated trouser, mid-rise, side adjusters, slight "
            "taper, finished with a 1.5-inch turn-up."
        ),
        "fit_note": "Drapes cleanly without breaking on the shoe.",
        "sort_order": 30,
    },
    {
        "inspiration_id": "ins_poplin_dress",
        "fabric_id": "fab_cotton_poplin",
        "piece_type": "dress",
        "complexity": "standard",
        "title": "Cotton poplin shirt-dress",
        "tagline": "Button-through shirt-dress in crisp cotton poplin.",
        "brief": (
            "Collared shirt-dress, fitted waist with a thin self-belt, "
            "knee-length, button-through front."
        ),
        "fit_note": "Defined at the waist, A-line through the skirt.",
        "sort_order": 40,
    },
    {
        "inspiration_id": "ins_denim_overshirt",
        "fabric_id": "fab_japanese_denim",
        "piece_type": "overshirt",
        "complexity": "standard",
        "title": "Japanese denim overshirt",
        "tagline": "Western-yoke overshirt in selvedge Japanese denim.",
        "brief": (
            "Western-yoke overshirt, two chest pockets with flaps, "
            "point collar, pearl-snap closure."
        ),
        "fit_note": "Roomy through the body, fits over a sweater.",
        "sort_order": 50,
    },
    {
        "inspiration_id": "ins_cashmere_coat",
        "fabric_id": "fab_cashmere",
        "piece_type": "coat",
        "complexity": "intricate",
        "title": "Cashmere overcoat",
        "tagline": "Double-breasted overcoat in Italian cashmere.",
        "brief": (
            "Double-breasted overcoat, peak lapels, six-button closure, "
            "full lining, two flap pockets, back vent."
        ),
        "fit_note": "Falls to mid-thigh, structured shoulders.",
        "sort_order": 60,
    },
    {
        "inspiration_id": "ins_kente_blazer",
        "fabric_id": "fab_kente",
        "piece_type": "blazer",
        "complexity": "intricate",
        "title": "Hand-woven Kente blazer",
        "tagline": "Tailored blazer in hand-woven Ghanaian Kente.",
        "brief": (
            "Single-breasted Kente blazer with notched lapels, "
            "one-button closure, plain black lapels and cuffs as a "
            "counterpoint to the woven body, double back vent."
        ),
        "fit_note": "Tailored at the waist, full canvas, padded shoulder.",
        "sort_order": 70,
    },
    {
        "inspiration_id": "ins_kente_dress",
        "fabric_id": "fab_kente",
        "piece_type": "dress",
        "complexity": "intricate",
        "title": "Kente column dress",
        "tagline": "Floor-length Kente dress with a strapless bodice.",
        "brief": (
            "Floor-length column dress, strapless sweetheart bodice, "
            "fitted through the waist and hips, side slit to mid-thigh, "
            "fully lined."
        ),
        "fit_note": (
            "Hugs the silhouette through bodice and hip, falls clean "
            "to the floor."
        ),
        "sort_order": 80,
    },
    {
        "inspiration_id": "ins_ankara_wrap",
        "fabric_id": "fab_ankara",
        "piece_type": "dress",
        "complexity": "standard",
        "title": "Ankara wrap dress",
        "tagline": "Knee-length wrap dress in Ankara wax print.",
        "brief": (
            "Knee-length wrap dress, deep V neckline, three-quarter "
            "sleeves, self-tie at the waist, A-line skirt."
        ),
        "fit_note": "Fitted through the bodice, gentle flare from the waist.",
        "sort_order": 90,
    },
]


async def main(force: bool) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    coll = db[C.design_inspirations]

    await coll.create_index("inspiration_id", unique=True)
    await coll.create_index([("sort_order", 1), ("title", 1)])

    now = datetime.now(UTC)
    inserted = updated = skipped = 0

    for raw in SEED:
        existing = await coll.find_one({"inspiration_id": raw["inspiration_id"]})
        doc = {
            **raw,
            "static_image_path": f"/bespoke/{raw['inspiration_id']}.png",
            "image_media_asset_id": None,
            "gradient": None,
            "active": True,
            "updated_at": now,
        }
        if existing is None:
            doc["created_at"] = now
            await coll.insert_one(doc)
            inserted += 1
            print(f"  inserted   {raw['inspiration_id']}  {raw['title']}")
        elif force:
            doc["created_at"] = existing.get("created_at", now)
            # Preserve any admin-uploaded hero photo unless --force AND
            # they want a hard reset. Keep ``image_media_asset_id`` if it
            # was already set so we don't blow away uploaded photos.
            doc["image_media_asset_id"] = existing.get("image_media_asset_id")
            await coll.replace_one(
                {"inspiration_id": raw["inspiration_id"]}, doc
            )
            updated += 1
            print(f"  rewrote    {raw['inspiration_id']}  {raw['title']}")
        else:
            skipped += 1
            print(f"  unchanged  {raw['inspiration_id']}  {raw['title']}")

    print()
    print(f"Inserted: {inserted}   Rewrote: {updated}   Unchanged: {skipped}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing inspirations with the canonical seed data.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(force=args.force)))
