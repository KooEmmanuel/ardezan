"""One-time gender backfill for products that don't have the field yet.

Heuristics (subcategory is checked first; parent category is the fallback):

WOMEN
  - Any product in category "Dresses" or "Skirts"
  - Subcategories that read distinctly women's:
      Blouses, Camisoles, Tank Tops

MEN
  - Subcategories that read distinctly men's in our catalog:
      Polos, Tailored, Tailored Trousers

UNISEX
  - Everything else (T-Shirts, Jeans, Coats, Knits, Footwear, Bags, …)

Run:
    .venv/bin/python -m scripts.backfill_gender         # dry run, prints proposed mapping
    .venv/bin/python -m scripts.backfill_gender --apply # writes to Mongo
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C


WOMEN_SUBCATEGORIES: set[str] = {
    "Blouses",
    "Camisoles",
    "Tank Tops",
}

MEN_SUBCATEGORIES: set[str] = {
    "Polos",
    "Tailored",
    "Tailored Trousers",
}

# Whole categories that are women-only in this catalog.
WOMEN_CATEGORIES: set[str] = {"Dresses", "Skirts"}


def classify(category: str | None, subcategory: str | None) -> str:
    if subcategory in WOMEN_SUBCATEGORIES:
        return "women"
    if subcategory in MEN_SUBCATEGORIES:
        return "men"
    if (category or "") in WOMEN_CATEGORIES:
        return "women"
    return "unisex"


async def main(apply: bool) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    products = db[C.products]

    proposed: dict[str, list[tuple[str, str]]] = {"women": [], "men": [], "unisex": []}
    updated = 0
    skipped = 0

    async for doc in products.find(
        {"deleted_at": None},
        {
            "product_id": 1,
            "title": 1,
            "category": 1,
            "subcategory": 1,
            "gender": 1,
            "_id": 0,
        },
    ):
        product_id = doc["product_id"]
        current = doc.get("gender")
        if current in {"women", "men", "unisex"}:
            skipped += 1
            continue
        target = classify(doc.get("category"), doc.get("subcategory"))
        proposed[target].append((product_id, doc.get("title", "?")))

        if apply:
            await products.update_one(
                {"product_id": product_id},
                {"$set": {"gender": target}},
            )
            updated += 1

    for bucket in ("women", "men", "unisex"):
        print(f"\n=== {bucket.upper()} ({len(proposed[bucket])}) ===")
        for pid, title in proposed[bucket][:50]:
            print(f"  {pid}  {title}")
        if len(proposed[bucket]) > 50:
            print(f"  … and {len(proposed[bucket]) - 50} more")

    print()
    print(f"Skipped (already had gender): {skipped}")
    if apply:
        print(f"Wrote gender on {updated} products.")
    else:
        print(f"DRY RUN — pass --apply to write {len(proposed['women']) + len(proposed['men']) + len(proposed['unisex'])} updates to Mongo.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write to Mongo (default is dry run)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
