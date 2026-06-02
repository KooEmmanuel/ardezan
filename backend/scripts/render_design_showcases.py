"""Render the Bespoke / Design Me showcase tiles via Gemini 2.5 Flash Image.

The customer-facing Bespoke gallery and the Design Me inspiration row
both want a real, photographic hero for each pairing — gradients don't
sell the idea. This script generates one image per inspiration entry
(text-only prompt, no reference photo needed) and writes them to
``frontend/public/bespoke/<id>.png`` so the frontend can serve them as
static assets.

The lineup is kept in sync with ``seed_inspirations.py``. Both files
need to change together — the script will warn if it finds bespoke PNGs
on disk whose IDs aren't in the SHOWCASES list (so you can prune them).

Re-runs are idempotent: existing files are skipped unless ``--force``.

Run::

    .venv/bin/python -m scripts.render_design_showcases          # generate missing
    .venv/bin/python -m scripts.render_design_showcases --force  # regenerate all
    .venv/bin/python -m scripts.render_design_showcases --only ins_kente_blazer
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


# Mirror of ``seed_inspirations.py`` SEED. Eight African-leaning
# menswear pieces — the prompts all show a black African male model
# so the showcase reads cohesively next to the homepage hero.
SHOWCASES: list[dict[str, Any]] = [
    {
        "id": "ins_kente_blazer",
        "title": "Hand-woven Kente blazer",
        "fabric": (
            "Traditional hand-woven Ghanaian Kente strip-cloth in the Bonwire "
            "weaving style — bold geometric blocks and stripes in saffron yellow, "
            "vermillion red, emerald green, and deep indigo/black. Each strip "
            "is roughly 4 inches wide, sewn edge-to-edge to form a panel. "
            "Medium weight cotton-rayon, slight sheen, structured hand."
        ),
        "piece_brief": (
            "Single-breasted blazer with notched lapels, one-button closure, "
            "and double back vent. The body is cut from the Kente weave; "
            "the lapels and cuffs are plain matte black wool as a counterpoint. "
            "Padded shoulder, full canvas construction."
        ),
    },
    {
        "id": "ins_kente_two_piece",
        "title": "Kente two-piece set",
        "fabric": (
            "Traditional hand-woven Ghanaian Kente strip-cloth in the Bonwire "
            "weaving style — bold horizontal bands of saffron yellow, vermillion "
            "red, emerald green, and deep indigo/black. Medium weight cotton-rayon."
        ),
        "piece_brief": (
            "Coordinated two-piece set: short-sleeve mandarin-collar tunic top "
            "that falls just past the hip + matching tapered straight-leg "
            "trousers. Both pieces cut from the same Kente weave so the bands "
            "run continuously from tunic to trouser."
        ),
    },
    {
        "id": "ins_natural_agbada",
        "title": "Natural linen agbada",
        "fabric": (
            "Premium Italian linen — warm natural sand and stone tones, "
            "medium weight, soft drape, matte surface with subtle slubbed texture."
        ),
        "piece_brief": (
            "Full three-piece agbada ensemble: wide-sleeve flowing outer robe "
            "with subtle tone-on-tone gold thread embroidery at the neckline, "
            "matching long-sleeve dansiki tunic underneath, and tapered "
            "sokoto trousers. All three pieces cut from the same warm "
            "sand-toned linen. Ceremonial menswear."
        ),
    },
    {
        "id": "ins_white_kaftan",
        "title": "Crisp white cotton kaftan",
        "fabric": (
            "Fine cotton poplin — clean white, lightweight, soft matte surface, "
            "crisp drape."
        ),
        "piece_brief": (
            "Long-sleeve kaftan that falls to mid-thigh, mandarin collar, "
            "tone-on-tone white embroidery running down the centre placket, "
            "side slits at the hem. Cut from crisp lightweight cotton poplin."
        ),
    },
    {
        "id": "ins_ankara_two_piece",
        "title": "Ankara two-piece set",
        "fabric": (
            "West African Ankara wax-print cotton — a vibrant high-contrast "
            "pattern of stylised florals and geometric motifs in saturated "
            "cream, amber, vermillion, and deep indigo. Crisp, light cotton "
            "with the characteristic waxed sheen."
        ),
        "piece_brief": (
            "Coordinated two-piece set: short-sleeve mandarin-collar tunic + "
            "matching tapered trousers. Both pieces cut from the same "
            "wax-print run so the motifs line up across the set."
        ),
    },
    {
        "id": "ins_ankara_bomber",
        "title": "Ankara wax-print bomber",
        "fabric": (
            "West African Ankara wax-print cotton — a vibrant high-contrast "
            "pattern in indigo, vermillion, and amber on a cream ground. "
            "Crisp lightweight cotton with the characteristic waxed sheen."
        ),
        "piece_brief": (
            "Cropped bomber jacket: ribbed crew collar, ribbed cuffs and hem, "
            "full two-way zip front, two slash pockets at the waist. Body cut "
            "from the Ankara wax-print; the collar, cuffs, and hem are in a "
            "matte black knit rib."
        ),
    },
    {
        "id": "ins_ankara_dashiki",
        "title": "Classic Ankara dashiki",
        "fabric": (
            "West African Ankara wax-print cotton — a vibrant high-contrast "
            "pattern of stylised florals and geometric motifs in saturated "
            "cream, amber, vermillion, and indigo. Crisp lightweight cotton."
        ),
        "piece_brief": (
            "Pullover dashiki shirt: V-neckline with embroidered ornamental "
            "yoke, short sleeves, square hem with side slits, falls just past "
            "the hip. Cut from the vibrant Ankara wax-print cotton."
        ),
    },
    {
        "id": "ins_linen_shirt",
        "title": "Camp-collar linen shirt",
        "fabric": (
            "Italian linen — warm sand and stone tones, lightweight, soft "
            "drape, matte surface with subtle slubbed texture."
        ),
        "piece_brief": (
            "Camp-collar shirt with short sleeves, single chest pocket, "
            "mother-of-pearl buttons, boxy through the body."
        ),
    },
]


def _build_prompt(entry: dict[str, Any]) -> str:
    """Editorial prompt — black African male model wearing the piece.

    We switched from flat-lay to on-body because the showcase reads
    next to the homepage hero (which is on-body) and a coherent
    visual brand requires both to match. Studio settings keep the
    focus on the garment, not the location.
    """
    return (
        "Editorial fashion photograph for a premium menswear magazine. "
        f"A tall, confident, handsome young black African man modelling: "
        f"{entry['piece_brief']} "
        f"The fabric is {entry['fabric']}. "
        "Clean warm-neutral studio background (warm off-white or soft stone). "
        "Soft, even directional studio lighting from camera-left. "
        "Full length, head to shoe, model centred, calm composed expression, "
        "hands relaxed at the sides or loosely clasped at the waist. "
        "Show construction details — seams, collar, buttons, embroidery, "
        "fabric pattern — at a level the customer can read at a glance. "
        "4:5 vertical composition. Photorealistic, magazine-quality, "
        "premium African menswear editorial."
    )


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


async def render_one(entry: dict[str, Any]) -> tuple[bytes, str]:
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_designer
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"], temperature=0.7
    )
    prompt = _build_prompt(entry)
    log.info("showcase.render.start", id=entry["id"])
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=config,
    )
    extracted = _extract_image(response)
    if extracted is None:
        raise RuntimeError(
            f"Gemini returned no image for {entry['id']} — likely a safety "
            "block; try a tamer brief or rerun."
        )
    image_bytes, mime = extracted
    log.info(
        "showcase.render.ok",
        id=entry["id"],
        bytes=len(image_bytes),
        mime=mime,
    )
    return image_bytes, mime


async def main(force: bool, only: str | None) -> int:
    # Backend lives at backend/, frontend at ../frontend.
    here = Path(__file__).resolve().parent.parent
    out_dir = here.parent / "frontend" / "public" / "bespoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_dir}")

    # Warn about orphan PNGs (files on disk for IDs no longer in
    # SHOWCASES). The customer-facing API hides them once Mongo is
    # cleaned up via seed_inspirations.py, but the files themselves
    # should be deleted to avoid dead weight in the repo.
    valid_ids = {e["id"] for e in SHOWCASES}
    orphans = sorted(
        p.stem for p in out_dir.glob("*.png") if p.stem not in valid_ids
    )
    if orphans:
        print(f"Orphan PNGs ({len(orphans)} — delete from disk):")
        for orphan in orphans:
            print(f"  - {orphan}.png")

    targets = [e for e in SHOWCASES if not only or e["id"] == only]
    if not targets:
        print(f"No matching showcase for --only={only}.")
        return 1

    written = 0
    skipped = 0
    failed = 0
    for entry in targets:
        path = out_dir / f"{entry['id']}.png"
        if path.exists() and not force:
            print(f"  skipped   {entry['id']}  (exists; --force to overwrite)")
            skipped += 1
            continue
        try:
            image_bytes, _mime = await render_one(entry)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED    {entry['id']}  {exc}")
            failed += 1
            continue
        path.write_bytes(image_bytes)
        print(f"  wrote     {entry['id']}  {path.name}  ({len(image_bytes):,} bytes)")
        written += 1

    print()
    print(f"Wrote: {written}   Skipped: {skipped}   Failed: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Regenerate even if file exists.")
    parser.add_argument("--only", default=None, help="Render only this inspiration id.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(force=args.force, only=args.only)))
