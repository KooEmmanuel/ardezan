"""Remove orphan media asset references from products.

Every product carries a ``media_asset_ids`` list and a
``primary_media_asset_id``. A reference is "orphan" when it points at
a media_assets doc that no longer exists (soft-deleted or never
created — the latter happened with an earlier seed iteration that
allocated IDs before generating images).

This script:
  1. Loads all media_asset_ids referenced by published products.
  2. Looks up which of those have a real ``media_assets`` doc with
     ``deleted_at: None``.
  3. For each product, rewrites ``media_asset_ids`` to keep only valid
     references and resets ``primary_media_asset_id`` if it's now gone.

Run:
    .venv/bin/python -m scripts.prune_orphan_media         # dry run
    .venv/bin/python -m scripts.prune_orphan_media --apply # writes
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C


async def main(apply: bool) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]

    products = db[C.products]
    media_assets = db[C.media_assets]

    # Gather every media id any product references.
    referenced: set[str] = set()
    async for p in products.find(
        {"deleted_at": None},
        {"_id": 0, "product_id": 1, "media_asset_ids": 1, "primary_media_asset_id": 1},
    ):
        for mid in p.get("media_asset_ids") or []:
            if mid:
                referenced.add(mid)
        pm = p.get("primary_media_asset_id")
        if pm:
            referenced.add(pm)

    # Which of those actually exist (not soft-deleted)?
    valid: set[str] = set()
    async for ma in media_assets.find(
        {"media_asset_id": {"$in": list(referenced)}},
        {"_id": 0, "media_asset_id": 1, "retention.deleted_at": 1},
    ):
        if (ma.get("retention") or {}).get("deleted_at") is None:
            valid.add(ma["media_asset_id"])

    print(f"Referenced media ids: {len(referenced)}")
    print(f"Of those, valid: {len(valid)}")
    print(f"Orphans to prune: {len(referenced) - len(valid)}")
    print()

    touched = 0
    primary_cleared = 0
    async for p in products.find(
        {"deleted_at": None},
        {"_id": 0, "product_id": 1, "title": 1, "media_asset_ids": 1, "primary_media_asset_id": 1},
    ):
        ids = [m for m in (p.get("media_asset_ids") or []) if m]
        pm = p.get("primary_media_asset_id")
        new_ids = [m for m in ids if m in valid]
        new_pm = pm if pm in valid else None
        # If we cleared the primary but kept at least one media id, promote it.
        if new_pm is None and new_ids:
            new_pm = new_ids[0]

        if new_ids != ids or new_pm != pm:
            touched += 1
            if pm and pm != new_pm:
                primary_cleared += 1
            removed = [m for m in ids if m not in valid]
            print(
                f"  {p['product_id']:>30s}  {p.get('title','')[:32]:<32s}  "
                f"-{len(removed)}"
                + (f"  primary→{new_pm}" if new_pm != pm else "")
            )
            if apply:
                await products.update_one(
                    {"product_id": p["product_id"]},
                    {
                        "$set": {
                            "media_asset_ids": new_ids,
                            "primary_media_asset_id": new_pm,
                        }
                    },
                )

    print()
    print(f"Products touched: {touched}")
    print(f"Primary reset to fallback: {primary_cleared}")
    if not apply:
        print("\nDRY RUN — pass --apply to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
