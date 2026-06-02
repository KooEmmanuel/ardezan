"""Regenerate the homepage hero looks + category tiles to match the
actual menswear catalog (two-piece sets, agbada, dashikis, kaftans,
hand-woven Kente).

Writes everything into ``frontend/public/site/`` so the homepage hero
and category grid pick it up automatically. Same idempotent pattern as
``render_design_showcases.py`` — already-existing files are skipped
unless ``--force``.

Run::

    .venv/bin/python -m scripts.regenerate_site_imagery
    .venv/bin/python -m scripts.regenerate_site_imagery --force
    .venv/bin/python -m scripts.regenerate_site_imagery --only hero_look_01
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from google.genai import types

from app.config import get_settings
from app.logging_setup import get_logger
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)


# ── Slots ──────────────────────────────────────────────────────────
# Each entry: (slot_name, prompt). The prompts are written for a
# coherent visual brand — black African men modelling well-tailored
# menswear in clean editorial settings. Mix of Kente, Ankara wax
# print, and plain cotton two-pieces to mirror the catalog.
SLOTS: list[dict[str, Any]] = [
    {
        "name": "hero_look_01",
        "prompt": (
            "Editorial fashion photograph of a tall, confident young black African "
            "man modelling a tailored two-piece set in deep burgundy cotton — "
            "high-collar tunic shirt + matching tapered trousers, structured "
            "drape, magazine quality. Clean off-white studio background, soft "
            "warm window light from camera-left. Full length, head to shoe, "
            "model centered, hands clasped at the waist. 4:5 vertical, "
            "photorealistic, premium menswear editorial."
        ),
    },
    {
        "name": "hero_look_02",
        "prompt": (
            "Editorial fashion photograph of a black African man modelling a "
            "hand-woven Kente two-piece set — bold geometric blocks of saffron "
            "yellow, vermillion, emerald, and deep indigo in the traditional "
            "Bonwire weave, tailored short-sleeve tunic + matching trousers. "
            "Clean warm-neutral studio background, soft natural light. "
            "Full length, three-quarter angle, calm confident expression. 4:5 "
            "vertical, magazine-quality photorealistic."
        ),
    },
    {
        "name": "hero_look_03",
        "prompt": (
            "Editorial fashion photograph of a black African man modelling a "
            "crisp white cotton kaftan with subtle tone-on-tone embroidery at "
            "the placket. Tall, slender, confident. Minimal modern interior — "
            "warm wood floor, off-white wall, a single sculptural plant. Soft "
            "diffused daylight. Full length, head to ankle. 4:5 vertical, "
            "premium magazine editorial quality."
        ),
    },
    {
        "name": "hero_look_04",
        "prompt": (
            "Editorial fashion photograph of a black African man modelling an "
            "Ankara wax-print bomber jacket — vibrant high-contrast pattern in "
            "indigo, vermillion, and amber on a cream ground — paired with "
            "clean black tapered trousers. Urban editorial setting: bare "
            "concrete wall, polished concrete floor, single moody window light. "
            "Full length, dynamic stance with hands in pockets. 4:5 vertical, "
            "photorealistic."
        ),
    },
    {
        "name": "hero_look_05",
        "prompt": (
            "Editorial fashion photograph of a black African man modelling a "
            "deep forest green textured cotton two-piece set — long-sleeve "
            "tunic shirt with mandarin collar + slim trousers. Warm-neutral "
            "studio cyclorama, soft directional light from above. Confident "
            "modern menswear. Full length, slight turn to the side. 4:5 "
            "vertical, premium magazine editorial."
        ),
    },
    {
        "name": "hero_look_06",
        "prompt": (
            "Editorial fashion photograph of a black African man modelling a "
            "royal blue cotton agbada — wide-sleeve flowing outer robe with "
            "gold embroidery at the neckline, over a matching dansiki and "
            "tapered sokoto trousers. Clean warm-cream studio backdrop, soft "
            "regal light. Full length, ceremonial confident stance. 4:5 "
            "vertical, photorealistic, magazine-quality. Show the full "
            "three-piece ensemble."
        ),
    },
    {
        "name": "hero_mobile",
        "prompt": (
            "Editorial fashion photograph for a mobile hero banner. Wide "
            "horizontal composition (3:2 landscape). A young black African "
            "man in a tailored deep burgundy cotton two-piece set walking "
            "confidently across a warm cream studio backdrop, soft cinematic "
            "side light, motion blur subtle. Premium menswear editorial, "
            "magazine quality, photorealistic."
        ),
    },
    {
        "name": "category_men",
        "prompt": (
            "Editorial product tile for the Men category. Close-up "
            "three-quarter shot of a black African man in a tailored cream "
            "cotton two-piece set, framed from shoulder to knee. Clean off-"
            "white studio background, soft warm light. Strong fabric "
            "texture visible. 3:2 horizontal composition, premium menswear "
            "magazine editorial, photorealistic."
        ),
    },
    {
        "name": "category_bespoke",
        "prompt": (
            "Editorial product tile for the Bespoke / made-to-order "
            "category. Close-up of a tailor's hands hand-stitching a Kente "
            "garment at a worktable — the bold saffron, vermillion, "
            "emerald, indigo geometric weave clearly visible. Warm "
            "directional light, shallow depth of field. 3:2 horizontal "
            "composition, premium craft documentary photography, "
            "photorealistic."
        ),
    },
    {
        "name": "category_new",
        "prompt": (
            "Editorial product tile for the New Arrivals category. "
            "Three-quarter shot of a black African man in a bright "
            "Ankara wax-print bomber jacket and dark trousers, walking "
            "out of frame to camera-right, motion blur on the legs. "
            "Clean warm-neutral background, soft daylight. 3:2 horizontal "
            "composition, magazine-quality photorealistic."
        ),
    },
    {
        "name": "editorial_no_01",
        "prompt": (
            "Editorial spread image — a black African man seated on a "
            "minimal wooden bench against a warm cream wall, wearing a "
            "deep burgundy cotton two-piece set. Soft window light from "
            "the side, contemplative pose looking off to the right, hands "
            "loosely clasped. Premium menswear magazine editorial, "
            "magazine-quality, photorealistic. 4:5 vertical."
        ),
    },
]


def _extract_image(response: Any) -> tuple[bytes, str] | None:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None) or "image/png"
            if data:
                return data, mime
    return None


async def render_one(slot: dict[str, Any]) -> bytes | None:
    settings = get_settings()
    client = get_gemini_client()
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"], temperature=0.7
    )
    log.info("site.render.start", name=slot["name"])
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model_designer,
            contents=[slot["prompt"]],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("site.render.failed", name=slot["name"], error=str(exc)[:200])
        return None
    extracted = _extract_image(response)
    if not extracted:
        log.warning("site.render.no_image", name=slot["name"])
        return None
    image_bytes, _mime = extracted
    log.info("site.render.ok", name=slot["name"], bytes=len(image_bytes))
    return image_bytes


async def main(force: bool, only: str | None) -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    out_dir = repo_root / "frontend" / "public" / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_dir}")

    targets = [s for s in SLOTS if not only or s["name"] == only]
    if not targets:
        print(f"No matching slot for --only={only}.")
        return 1

    written = 0
    skipped = 0
    failed = 0
    for entry in targets:
        path = out_dir / f"{entry['name']}.png"
        if path.exists() and not force:
            print(f"  skipped   {entry['name']}  (exists; --force to overwrite)")
            skipped += 1
            continue
        image_bytes = await render_one(entry)
        if image_bytes is None:
            print(f"  FAILED    {entry['name']}")
            failed += 1
            continue
        path.write_bytes(image_bytes)
        print(f"  wrote     {entry['name']}  ({len(image_bytes):,} bytes)")
        written += 1

    print()
    print(f"Wrote: {written}   Skipped: {skipped}   Failed: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(force=args.force, only=args.only)))
