"""Seed the design_inspirations collection from the curated brand set.

The Bespoke showcase mirrors what Ardezan actually sells — African
menswear: hand-woven Kente, Ankara wax-print, agbadas, kaftans,
dashikis, two-piece sets. Each inspiration deep-links into Design Me
with the form pre-filled, so they're starting points the customer
can customize.

Idempotent: skips entries already in the collection unless ``--force``.
``DEPRECATED_IDS`` are always removed (covers the original womenswear
and generic-Western seed that we no longer carry).

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


# Old seed entries that don't match the current catalog — pruned on
# every run so the showcase stays aligned with what we sell.
DEPRECATED_IDS: list[str] = [
    "ins_poplin_dress",     # womenswear
    "ins_kente_dress",      # womenswear
    "ins_ankara_wrap",      # womenswear
    "ins_wool_blazer",      # generic Western menswear, not in catalog
    "ins_khaki_trouser",    # generic Western menswear, not in catalog
    "ins_denim_overshirt",  # generic Western menswear, not in catalog
    "ins_cashmere_coat",    # generic Western menswear, not in catalog
]


SEED: list[dict[str, Any]] = [
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
        "sort_order": 10,
    },
    {
        "inspiration_id": "ins_kente_two_piece",
        "fabric_id": "fab_kente",
        "piece_type": "caftan",
        "complexity": "intricate",
        "title": "Kente two-piece set",
        "tagline": "Short-sleeve tunic and matching trousers in Kente strip-cloth.",
        "brief": (
            "Two-piece set: short-sleeve mandarin-collar tunic that "
            "falls just past the hip + matching tapered straight-leg "
            "trousers. Both pieces cut from the same Kente weave for a "
            "fully coordinated ceremonial look."
        ),
        "fit_note": "Tunic clean through the shoulders, trousers break softly on the shoe.",
        "sort_order": 20,
    },
    {
        "inspiration_id": "ins_natural_agbada",
        "fabric_id": "fab_italian_linen",
        "piece_type": "agbada",
        "complexity": "intricate",
        "title": "Natural linen agbada",
        "tagline": "Three-piece agbada ensemble in warm sand Italian linen.",
        "brief": (
            "Full three-piece agbada: wide-sleeve flowing outer robe "
            "with subtle tone-on-tone embroidery at the neckline, "
            "matching long-sleeve dansiki tunic underneath, and "
            "tapered sokoto trousers. All three pieces in the same "
            "warm sand-toned linen."
        ),
        "fit_note": "Generous through the body of the outer robe, structured at the shoulders.",
        "sort_order": 30,
    },
    {
        "inspiration_id": "ins_white_kaftan",
        "fabric_id": "fab_cotton_poplin",
        "piece_type": "caftan",
        "complexity": "standard",
        "title": "Crisp white cotton kaftan",
        "tagline": "Long-sleeve kaftan in fine cotton poplin with tone-on-tone embroidery.",
        "brief": (
            "Long-sleeve kaftan that falls to mid-thigh, mandarin "
            "collar, tone-on-tone white embroidery running down the "
            "centre placket, side slits at the hem. Cut from crisp "
            "lightweight cotton poplin."
        ),
        "fit_note": "Skims the body — relaxed but not boxy.",
        "sort_order": 40,
    },
    {
        "inspiration_id": "ins_ankara_two_piece",
        "fabric_id": "fab_ankara",
        "piece_type": "caftan",
        "complexity": "standard",
        "title": "Ankara two-piece set",
        "tagline": "Wax-print short-sleeve tunic and matching trousers.",
        "brief": (
            "Two-piece set in vibrant Ankara wax-print cotton: "
            "short-sleeve mandarin-collar tunic + matching tapered "
            "trousers. Both pieces cut from the same wax-print run so "
            "the motifs line up across the set."
        ),
        "fit_note": "Tunic falls just past the hip, trousers slim through the leg.",
        "sort_order": 50,
    },
    {
        "inspiration_id": "ins_ankara_bomber",
        "fabric_id": "fab_ankara",
        "piece_type": "jacket",
        "complexity": "intricate",
        "title": "Ankara wax-print bomber",
        "tagline": "Cropped bomber jacket in vivid Ankara wax-print cotton.",
        "brief": (
            "Cropped bomber jacket: ribbed crew collar, ribbed cuffs "
            "and hem, full two-way zip front, two slash pockets at "
            "the waist. Body cut from vibrant Ankara wax-print "
            "cotton; cuffs, collar, and hem in a matte black knit rib."
        ),
        "fit_note": "Sits at the natural waist, clean through the shoulders.",
        "sort_order": 60,
    },
    {
        "inspiration_id": "ins_ankara_dashiki",
        "fabric_id": "fab_ankara",
        "piece_type": "dashiki",
        "complexity": "standard",
        "title": "Classic Ankara dashiki",
        "tagline": "Pullover dashiki shirt in Ankara wax-print cotton.",
        "brief": (
            "Pullover dashiki shirt: V-neckline with embroidered "
            "ornamental yoke, short sleeves, square hem with side "
            "slits, falls just past the hip. Cut from vibrant Ankara "
            "wax-print cotton."
        ),
        "fit_note": "Relaxed through the body — meant to be worn loose.",
        "sort_order": 70,
    },
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
        "sort_order": 80,
    },
]


async def main(force: bool) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    coll = db[C.design_inspirations]

    await coll.create_index("inspiration_id", unique=True)
    await coll.create_index([("sort_order", 1), ("title", 1)])

    # Prune deprecated entries first — runs every time, idempotent.
    if DEPRECATED_IDS:
        deletion = await coll.delete_many(
            {"inspiration_id": {"$in": DEPRECATED_IDS}}
        )
        if deletion.deleted_count:
            print(f"  pruned     {deletion.deleted_count} deprecated inspirations")
            for dep in DEPRECATED_IDS:
                print(f"     - {dep}")

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
