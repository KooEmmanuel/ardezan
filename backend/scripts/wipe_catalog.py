"""One-shot: wipe the catalog so we can reseed from the cousin's pieces.

Deletes:
- ``products`` (all)
- ``variants`` (all)
- ``inventory_holds`` (orphaned without products)
- ``inventory_movements`` (full ledger reset)
- ``media_assets`` where ``owner_type=product``  (clears their B2 keys
  conceptually — actual B2 objects stay until the retention worker
  sweeps them; that's fine)

Preserves:
- ``fabrics``, ``design_inspirations`` (just seeded)
- ``customers``, ``admin_users``, ``orders``, ``checkout_sessions``
- ``settings``, ``audit_logs``, ``analytics_events``
- ``try_on_sessions``, ``design_sessions``, ``ai_jobs``,
  ``generated_images`` (customer artifacts)

Run::

    .venv/bin/python -m scripts.wipe_catalog          # dry run
    .venv/bin/python -m scripts.wipe_catalog --apply  # really delete
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

    targets: list[tuple[str, dict]] = [
        (C.products, {}),
        (C.variants, {}),
        (C.inventory_holds, {}),
        (C.inventory_movements, {}),
        (C.media_assets, {"owner_type": "product"}),
    ]

    print(f"Database: {settings.mongo_db}")
    print()
    total = 0
    for coll_name, query in targets:
        count = await db[coll_name].count_documents(query)
        total += count
        label = f"{coll_name} ({query or 'all'})"
        if apply and count > 0:
            r = await db[coll_name].delete_many(query)
            print(f"  deleted  {r.deleted_count:>5}  {label}")
        else:
            verb = "would delete" if not apply else "no rows"
            print(f"  {verb:<12} {count:>5}  {label}")

    print()
    if not apply:
        print(f"DRY RUN — would touch {total} rows. Pass --apply to do it.")
    else:
        print(f"Done. Touched {total} rows.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
