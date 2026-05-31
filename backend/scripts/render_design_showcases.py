"""Render the Bespoke / Design Me showcase tiles via Gemini 2.5 Flash Image.

The customer-facing Bespoke gallery and the Design Me inspiration row
both want a real, photographic hero for each pairing — gradients don't
sell the idea. This script generates one image per inspiration entry
(text-only prompt, no reference photo needed) and writes them to
``frontend/public/bespoke/<id>.png`` so the frontend can serve them as
static assets.

Re-runs are idempotent: existing files are skipped unless ``--force``.

Run::

    .venv/bin/python -m scripts.render_design_showcases          # generate missing
    .venv/bin/python -m scripts.render_design_showcases --force  # regenerate all
    .venv/bin/python -m scripts.render_design_showcases --only ins_cashmere_coat
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


# Mirror of the curated inspiration list on the frontend
# (``lib/design-inspirations.ts``). Kept in sync by hand — these are
# both small, stable lists, and a dedicated script run is cheap.
SHOWCASES: list[dict[str, Any]] = [
    {
        "id": "ins_linen_shirt",
        "title": "Camp-collar linen shirt",
        "fabric": "Italian linen — warm sand and stone tones, lightweight, soft drape, matte surface",
        "piece_brief": (
            "Camp-collar shirt with short sleeves, single chest pocket, "
            "mother-of-pearl buttons, boxy through the body."
        ),
    },
    {
        "id": "ins_wool_blazer",
        "title": "Unstructured wool blazer",
        "fabric": "English wool flannel — cool grey and slate tones, medium-heavy weight, brushed surface",
        "piece_brief": (
            "Single-breasted blazer with notched lapels, two-button closure, "
            "soft shoulder, side vents, working cuffs."
        ),
    },
    {
        "id": "ins_khaki_trouser",
        "title": "Pleated khaki trouser",
        "fabric": "Cotton twill — warm khaki tones, medium weight, structured surface",
        "piece_brief": (
            "Double-pleated trouser, mid-rise, side adjusters, slight taper, "
            "finished with a 1.5-inch turn-up at the hem."
        ),
    },
    {
        "id": "ins_poplin_dress",
        "title": "Cotton poplin shirt-dress",
        "fabric": "Cotton poplin — cool white tones, light weight, matte surface, crisp drape",
        "piece_brief": (
            "Collared shirt-dress with a fitted waist, thin self-belt, "
            "knee-length, button-through front."
        ),
    },
    {
        "id": "ins_denim_overshirt",
        "title": "Japanese denim overshirt",
        "fabric": "Selvedge Japanese denim — deep indigo, medium weight, structured surface",
        "piece_brief": (
            "Western-yoke overshirt with two chest pockets with flaps, "
            "point collar, pearl-snap closure, roomy through the body."
        ),
    },
    {
        "id": "ins_cashmere_coat",
        "title": "Cashmere overcoat",
        "fabric": "Italian cashmere — deep chocolate brown, medium weight, lustrous surface",
        "piece_brief": (
            "Double-breasted overcoat with peak lapels, six-button closure, "
            "two flap pockets, back vent, mid-thigh length, structured shoulders."
        ),
    },
    # ── Kente + Ankara — brand-anchoring pieces. The fabric blurb
    # is long on purpose; Gemini needs an explicit visual reference
    # to render real Kente / wax-print patterns instead of a vague
    # "African pattern."
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
        "id": "ins_kente_dress",
        "title": "Kente column dress",
        "fabric": (
            "Traditional hand-woven Ghanaian Kente strip-cloth — bold "
            "geometric blocks of saffron yellow, vermillion red, emerald "
            "green, and deep indigo/black, arranged in horizontal bands."
        ),
        "piece_brief": (
            "Floor-length column dress with a strapless sweetheart bodice, "
            "fitted through the waist and hips, a single side slit rising to "
            "mid-thigh. Fully lined. The Kente strips run horizontally across "
            "the body."
        ),
    },
    {
        "id": "ins_ankara_wrap",
        "title": "Ankara wrap dress",
        "fabric": (
            "West African Ankara wax-print cotton — a vibrant high-contrast "
            "tribal pattern of stylised florals and geometric motifs in "
            "saturated cream, amber, vermillion, and indigo. Crisp, light "
            "cotton with the characteristic waxed sheen."
        ),
        "piece_brief": (
            "Knee-length wrap dress with a deep V neckline, three-quarter "
            "sleeves, a self-tie at the waist, and an A-line skirt that "
            "flares gently from the waist."
        ),
    },
]


def _build_prompt(entry: dict[str, Any]) -> str:
    """Studio editorial prompt — no person, just the garment.

    We've found this style reliably produces a clean, magazine-feel
    product hero that scales well into a catalog tile. We avoid asking
    for a mannequin or a person so the model doesn't accidentally make
    a face we then need to worry about.
    """
    return (
        f"Editorial flat-lay product photograph of: {entry['piece_brief']} "
        f"The fabric is {entry['fabric']}. "
        "Show the full garment, slightly arranged with natural folds "
        "to convey the drape and weight of the fabric. "
        "Plain neutral background (warm off-white or soft stone). "
        "Soft, even studio lighting from above. "
        "Photorealistic, high-end fashion-magazine quality. "
        "Composition: 4:5 vertical, garment centred, plenty of negative space. "
        "Show construction details — seams, lapels, collar, buttons, hems — "
        "at a level a customer can read at a glance. "
        "Do not render a model, person, mannequin, hanger, or hands."
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
