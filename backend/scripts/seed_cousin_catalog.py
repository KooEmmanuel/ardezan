"""Seed the catalog from your cousin's processed photos.

Reads ``marketing and videos/processed/*_meta.json`` plus the matching
``_catalog.png`` and ``_lifestyle.png``, then:

1. Copies the processed images to ``frontend/public/catalog/<slug>/``
   (Vercel CDN-served, no B2 egress cap).
2. Creates a product doc with realistic pricing for the piece type
   (see ``_RETAIL_RANGE_BY_PIECE``).
3. Creates variants for typical sizes (M, L, XL for men's; S, M, L
   for women's), each with a small handmade-batch stock quantity.
4. Skips entries where the AI classifier had low confidence (<0.5)
   so we don't accidentally list garbage.

Run::

    .venv/bin/python -m scripts.seed_cousin_catalog          # dry run
    .venv/bin/python -m scripts.seed_cousin_catalog --apply  # really do it
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C


# ── Retail price ranges (USD cents). Centered, narrow ranges so demos
# look consistent. Cousin gets ~50% of retail as wholesale. ──────────
_RETAIL_RANGE_BY_PIECE: dict[str, tuple[int, int]] = {
    "two_piece_set":  (22_000, 32_000),   # $220-$320
    "kente_set":      (28_000, 42_000),
    "agbada":         (32_000, 48_000),
    "caftan":         (18_000, 26_000),
    "kaba":           (20_000, 28_000),
    "ankara_dress":   (15_000, 22_000),
    "dress":          (14_000, 22_000),
    "dashiki":        (9_000,  14_000),
    "shirt":          (7_000,  11_000),
    "blouse":         (7_000,  11_000),
    "trouser":        (8_000,  12_000),
    "skirt":          (7_000,  10_500),
    "jacket":         (16_000, 24_000),
    "blazer":         (20_000, 30_000),
    "coat":           (24_000, 34_000),
    "overshirt":      (11_000, 16_000),
    "tee":            (4_500,  7_000),
    "other":          (10_000, 16_000),
}


# Sizes + stock. Handmade pieces so stock is naturally low.
_DEFAULT_SIZES = ["S", "M", "L", "XL"]
_DEFAULT_STOCK_PER_VARIANT = 2


# Which piece types skew menswear vs womenswear (for category routing).
_MENS_PIECES = {"agbada", "dashiki", "two_piece_set"}
_WOMENS_PIECES = {"kaba", "ankara_dress", "dress", "blouse", "skirt"}
_UNISEX_PIECES = {"caftan", "kente_set", "tee", "shirt", "trouser"}


def _now() -> datetime:
    return datetime.now(UTC)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or f"piece-{secrets.token_hex(3)}"


def _product_id() -> str:
    return f"prod_{secrets.token_hex(8)}"


def _variant_id() -> str:
    return f"var_{secrets.token_hex(8)}"


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _sku(slug: str, size: str) -> str:
    # Take the first 10 letters of the slug + a short hash suffix so SKUs
    # stay unique even when two products share a prefix (e.g. two
    # "Crisp White" pieces).
    import hashlib
    prefix = slug.upper().replace("-", "")[:10]
    suffix = hashlib.sha1(slug.encode()).hexdigest()[:4].upper()
    return f"{prefix}-{suffix}-{size}"


def _retail_for(piece_type: str, hash_seed: str) -> int:
    """Pick a price inside the configured range — deterministic per piece
    so re-runs don't reshuffle prices."""
    lo, hi = _RETAIL_RANGE_BY_PIECE.get(piece_type, _RETAIL_RANGE_BY_PIECE["other"])
    # Hash the slug to a stable offset within the range.
    h = sum(ord(c) for c in hash_seed)
    return lo + (h % max(1, hi - lo))


def _gender_for(piece_type: str) -> str:
    if piece_type in _MENS_PIECES:
        return "men"
    if piece_type in _WOMENS_PIECES:
        return "women"
    return "unisex"


def _category_for(piece_type: str) -> tuple[str, str | None]:
    """Returns (category, subcategory)."""
    mapping = {
        "two_piece_set": ("Tops", "Sets"),
        "kente_set":     ("Tops", "Sets"),
        "agbada":        ("Tops", "Agbada"),
        "caftan":        ("Tops", "Caftan"),
        "dashiki":       ("Tops", "Dashiki"),
        "kaba":          ("Dresses", "Kaba"),
        "ankara_dress":  ("Dresses", "Ankara"),
        "dress":         ("Dresses", None),
        "shirt":         ("Tops", "Shirts"),
        "blouse":        ("Tops", "Blouses"),
        "trouser":       ("Trousers", None),
        "skirt":         ("Skirts", None),
        "jacket":        ("Outerwear", "Jackets"),
        "blazer":        ("Outerwear", "Blazers"),
        "coat":          ("Outerwear", "Coats"),
        "overshirt":     ("Outerwear", "Overshirts"),
        "tee":           ("Tops", "Tees"),
        "other":         ("Tops", None),
    }
    return mapping.get(piece_type, ("Tops", None))


def _sizes_for(piece_type: str) -> list[str]:
    if piece_type in _WOMENS_PIECES:
        return ["S", "M", "L"]
    if piece_type in _MENS_PIECES:
        return ["M", "L", "XL"]
    return ["S", "M", "L"]


async def main(apply: bool) -> int:
    settings = get_settings()
    repo_root = Path(__file__).resolve().parent.parent.parent
    processed_dir = repo_root / "marketing and videos" / "processed"
    public_dir = repo_root / "frontend" / "public" / "catalog"

    metas = sorted(processed_dir.glob("*_meta.json"))
    if not metas:
        print(f"No metadata in {processed_dir}. Run regenerate_catalog_photos first.")
        return 1

    print(f"Source:  {processed_dir}")
    print(f"Images → {public_dir}")
    print(f"Database: {settings.mongo_db}")
    print()

    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]

    queued: list[dict[str, Any]] = []
    skipped = 0
    used_slugs: set[str] = set()

    for meta_path in metas:
        meta = json.loads(meta_path.read_text())
        if meta.get("confidence", 0.0) < 0.5:
            skipped += 1
            print(f"  skip (low conf)  {meta_path.stem}  conf={meta.get('confidence')}")
            continue

        stem = meta_path.stem[: -len("_meta")]  # strip ``_meta`` suffix
        catalog_src = processed_dir / f"{stem}_catalog.png"
        lifestyle_src = processed_dir / f"{stem}_lifestyle.png"
        if not catalog_src.exists():
            skipped += 1
            print(f"  skip (no catalog img)  {stem}")
            continue

        title: str = meta.get("proposed_name") or stem
        slug = _slug(title)
        # Disambiguate duplicate names by appending a short tag.
        if slug in used_slugs:
            slug = f"{slug}-{secrets.token_hex(2)}"
        used_slugs.add(slug)

        piece_type = meta.get("piece_type", "other")
        category, subcategory = _category_for(piece_type)
        gender = _gender_for(piece_type)
        sizes = _sizes_for(piece_type)
        retail_cents = _retail_for(piece_type, slug)
        compare_at = int(retail_cents * 1.2)  # gentle "was $X" anchor

        product_dir = public_dir / slug
        catalog_dst = product_dir / "catalog.png"
        lifestyle_dst = product_dir / "lifestyle.png"

        queued.append({
            "title": title,
            "slug": slug,
            "description": meta.get("short_description", ""),
            "category": category,
            "subcategory": subcategory,
            "gender": gender,
            "tags": [
                category.lower(),
                gender,
                meta.get("fabric_guess", "").lower(),
                meta.get("color_story", "").lower(),
                piece_type,
            ],
            "color_story": meta.get("color_story") or "Earth tone",
            "fabric_guess": meta.get("fabric_guess", "unknown"),
            "piece_type": piece_type,
            "sizes": sizes,
            "retail_cents": retail_cents,
            "compare_at_cents": compare_at,
            "src_catalog": catalog_src,
            "src_lifestyle": lifestyle_src if lifestyle_src.exists() else None,
            "dst_catalog": catalog_dst,
            "dst_lifestyle": lifestyle_dst if lifestyle_src.exists() else None,
            "static_url_catalog": f"/catalog/{slug}/catalog.png",
            "static_url_lifestyle": (
                f"/catalog/{slug}/lifestyle.png"
                if lifestyle_src.exists()
                else None
            ),
        })

    print()
    print(f"Ready to seed: {len(queued)} products. Skipped: {skipped}")
    if not apply:
        for q in queued:
            print(
                f"  $ {q['retail_cents']/100:>6.2f}   "
                f"{q['piece_type']:<14}  "
                f"{q['title']}"
            )
        print()
        print("DRY RUN — pass --apply to write to Mongo + copy images.")
        return 0

    # Apply: copy images, insert docs.
    now = _now()
    inserted = 0
    for q in queued:
        q["dst_catalog"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(q["src_catalog"], q["dst_catalog"])
        if q["dst_lifestyle"]:
            shutil.copy2(q["src_lifestyle"], q["dst_lifestyle"])

        product_id = _product_id()
        # Build the doc — schema-compatible with what the catalog router
        # already serves. ``static_image_url`` / ``static_media_urls`` are
        # the new fields the repo now prefers over signed B2 URLs.
        product_doc = {
            "product_id": product_id,
            "slug": q["slug"],
            "title": q["title"],
            "description": q["description"],
            "category": q["category"],
            "subcategory": q["subcategory"],
            "gender": q["gender"],
            "tags": [t for t in q["tags"] if t],
            "status": "published",
            "publication": {"published_at": now, "scheduled_for": None},
            "pricing": {
                "price_amount": q["retail_cents"],
                "base_price_amount": q["retail_cents"],
                "compare_at_price_amount": q["compare_at_cents"],
                "currency": "USD",
            },
            "media_asset_ids": [],
            "primary_media_asset_id": None,
            "static_image_url": q["static_url_catalog"],
            "static_media_urls": [
                u for u in (q["static_url_catalog"], q["static_url_lifestyle"]) if u
            ],
            "ai_friendly_media_asset_ids": [],
            "product_details": {
                "fabric": q["fabric_guess"].replace("_", " ").title(),
                "color": q["color_story"],
                "care": "Hand wash cold. Hang to dry.",
                "origin": "Handmade in Ghana",
            },
            "size_chart_id": None,
            "ai": {"eligible": True},
            "seo": {
                "title": q["title"],
                "description": q["description"][:160],
            },
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await db[C.products].insert_one(product_doc)

        # Variants: one per size, small stock.
        variants_to_insert = []
        for size in q["sizes"]:
            variants_to_insert.append({
                "variant_id": _variant_id(),
                "product_id": product_id,
                "sku": _sku(q["slug"], size),
                "title": None,
                "size": size,
                "color": q["color_story"],
                "color_hex": None,
                "status": "active",
                "pricing": {
                    "price_amount": q["retail_cents"],
                    "compare_at_price_amount": q["compare_at_cents"],
                    "currency": "USD",
                },
                "inventory": {
                    "stock_on_hand": _DEFAULT_STOCK_PER_VARIANT,
                    "held_units": 0,
                    "committed_units": 0,
                    "low_stock_threshold": 1,
                    "track_inventory": True,
                },
                "measurements": {},
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            })
        if variants_to_insert:
            await db[C.variants].insert_many(variants_to_insert)

        inserted += 1
        print(f"  inserted  {q['slug']}  ({len(variants_to_insert)} variants, ${q['retail_cents']/100:.0f})")

    print()
    print(f"Done. {inserted} products + {sum(len(_sizes_for(q['piece_type'])) for q in queued)} variants.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
