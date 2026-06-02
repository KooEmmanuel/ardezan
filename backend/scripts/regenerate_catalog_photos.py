"""Regenerate clean catalog imagery from your cousin's raw reference photos.

For each raw photo in ``marketing and videos/raw images and videos/`` this
script makes two Gemini Image calls, using the raw photo as a *visual
reference only*:

1. A clean **catalog product shot** — garment isolated on a neutral
   studio background, no model, no street, premium fashion magazine
   aesthetic. This is what lands on the product detail page + catalog grid.

2. An **editorial lifestyle shot** — a model wearing the piece in a
   clean modern setting. Drops the original Ghana street context but
   keeps the garment intact. This is what powers Instagram + hero
   slots on the storefront.

It also asks Gemini Flash (text) to classify each piece — proposing a
name, piece type, color story, and fabric guess. Output lands in a
JSON sidecar so you can review + correct with your cousin before
listing anything.

The reference photo's pattern, color, and silhouette are preserved
because Gemini Image accepts multi-modal inputs — we pass the raw
photo bytes as a Part, then prompt for the new aesthetic.

Run::

    .venv/bin/python -m scripts.regenerate_catalog_photos --limit 5  # test
    .venv/bin/python -m scripts.regenerate_catalog_photos             # full run
    .venv/bin/python -m scripts.regenerate_catalog_photos --force     # rerun all

Costs (Gemini 2.5 Flash Image): ~$0.04 per image generation.
50 photos × 2 generations + 50 classification calls ≈ ~$5 total.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from google.genai import types

from app.config import get_settings
from app.logging_setup import get_logger
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)

# Where the raw photos live (relative to the repo root).
RAW_DIR_REL = Path("marketing and videos") / "raw images and videos"
OUT_DIR_REL = Path("marketing and videos") / "processed"


# ── Prompts ────────────────────────────────────────────────────────
CATALOG_PROMPT = """\
Regenerate the garment from the reference photo as a clean editorial
product photograph.

Requirements:
- Drop the model entirely. Show the garment alone — laid out flat, on
  an invisible mannequin, or floating gently as if worn but with no
  person visible.
- Drop the original setting entirely. Use a clean, neutral studio
  background — soft warm off-white, gentle gradient, or pure white.
- Lighting: soft, even, diffuse — magazine-quality.
- Preserve EXACTLY: the fabric's pattern, color, weave, drape, and
  every visible construction detail (seams, hems, collar, embroidery,
  embellishments, buttons, closures).
- Composition: garment centered, full piece visible head-to-hem,
  generous negative space around it.
- Photorealistic, high-end fashion magazine quality, 4:5 vertical
  aspect ratio.
- Do not invent extra pieces or accessories. If the reference shows a
  two-piece (top + trouser), show both. Otherwise, show only the
  garment(s) in the reference.
"""

LIFESTYLE_PROMPT = """\
Regenerate the garment from the reference photo on a model in a clean
editorial setting.

Requirements:
- Choose a tall, slender model with a friendly, confident expression.
  Use a model whose skin tone harmonises with the garment. Either a
  black African woman OR a black African man as appropriate for the
  piece. Do NOT replicate the person from the reference photo — make
  someone different.
- Preserve EXACTLY: the fabric's pattern, color, weave, drape, and
  every visible construction detail of the original garment.
- Setting: clean modern editorial — neutral studio background, soft
  natural light, OR a minimal contemporary interior (warm wood floor,
  off-white wall, single sculptural plant or chair).
- Composition: full-length, head-to-shoe, model centered or slightly
  off-center, premium fashion magazine framing. 4:5 vertical.
- Photorealistic, soft cinematic lighting, magazine-quality.
- Do NOT use the street, brick walls, sandals, or domestic scene from
  the reference photo. Keep the *garment*, drop the *context*.
"""

CLASSIFY_PROMPT = """\
Look at this photo of a tailored garment. Respond with a single JSON
object — no prose, no markdown fence, just the JSON. Schema:

{
  "piece_type": one of "caftan", "agbada", "dashiki", "kaba", "kente_set",
                       "ankara_dress", "shirt", "blouse", "trouser",
                       "skirt", "dress", "jacket", "blazer", "coat",
                       "overshirt", "tee", "two_piece_set", "other",
  "is_set":     true if it's clearly a coordinated set (top + bottom or
                more), false if it's a single piece,
  "color_story":  short phrase like "saffron and indigo Kente",
                  "deep burgundy", "earth-tone Ankara wax print",
  "fabric_guess": one of "kente", "ankara_wax_print", "adinkra",
                  "cotton", "linen", "silk", "wool", "denim", "unknown",
  "proposed_name":   a short product name (4-7 words) that combines
                     piece type + fabric + color, e.g.
                     "Maroon Kente Kaftan Set",
                     "Indigo Ankara Wrap Dress",
                     "Hand-woven Agbada in Saffron",
  "short_description": one full sentence describing the piece for the
                       product detail page,
  "confidence": float between 0 and 1 — how sure you are about the
                piece_type classification.
}
"""


# ── Image extraction (same helper used elsewhere) ──────────────────
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


def _extract_text(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "".join(chunks).strip()


# ── Per-photo workers ─────────────────────────────────────────────
async def classify_garment(
    raw_bytes: bytes, raw_mime: str
) -> dict[str, Any]:
    settings = get_settings()
    client = get_gemini_client()
    image_part = types.Part.from_bytes(data=raw_bytes, mime_type=raw_mime)
    config = types.GenerateContentConfig(response_modalities=["TEXT"])
    response = await client.aio.models.generate_content(
        model=settings.gemini_model_analyzer,
        contents=[image_part, CLASSIFY_PROMPT],
        config=config,
    )
    text = _extract_text(response)
    # Gemini sometimes wraps JSON in ```json fences despite instructions.
    cleaned = text.strip().lstrip("`").rstrip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].lstrip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("classify.json_parse_failed", text=text[:200])
        return {
            "piece_type": "other",
            "is_set": False,
            "color_story": "",
            "fabric_guess": "unknown",
            "proposed_name": "Untitled piece",
            "short_description": "",
            "confidence": 0.0,
            "_raw_response": text,
        }


async def regenerate(
    raw_bytes: bytes, raw_mime: str, prompt: str, *, label: str
) -> bytes | None:
    settings = get_settings()
    client = get_gemini_client()
    image_part = types.Part.from_bytes(data=raw_bytes, mime_type=raw_mime)
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"], temperature=0.55
    )
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model_designer,
            contents=[image_part, prompt],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("regenerate.failed", label=label, error=str(exc)[:200])
        return None
    extracted = _extract_image(response)
    if not extracted:
        log.warning("regenerate.no_image", label=label)
        return None
    image_bytes, _mime = extracted
    return image_bytes


async def process_one(
    raw_path: Path, out_dir: Path, force: bool
) -> tuple[bool, str]:
    """Returns (success, status_string)."""
    stem = raw_path.stem.replace(" ", "_")
    catalog_path = out_dir / f"{stem}_catalog.png"
    lifestyle_path = out_dir / f"{stem}_lifestyle.png"
    meta_path = out_dir / f"{stem}_meta.json"

    if not force and catalog_path.exists() and lifestyle_path.exists() and meta_path.exists():
        return True, "skipped (exists; --force to overwrite)"

    raw_bytes = raw_path.read_bytes()
    if not raw_bytes:
        return False, "empty source file"

    suffix = raw_path.suffix.lower()
    raw_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(suffix, "application/octet-stream")

    # Three calls in parallel — classification + two regenerations.
    meta, catalog_bytes, lifestyle_bytes = await asyncio.gather(
        classify_garment(raw_bytes, raw_mime),
        regenerate(raw_bytes, raw_mime, CATALOG_PROMPT, label="catalog"),
        regenerate(raw_bytes, raw_mime, LIFESTYLE_PROMPT, label="lifestyle"),
    )

    meta["source_filename"] = raw_path.name
    meta_path.write_text(json.dumps(meta, indent=2))

    wrote = []
    if catalog_bytes:
        catalog_path.write_bytes(catalog_bytes)
        wrote.append("catalog")
    if lifestyle_bytes:
        lifestyle_path.write_bytes(lifestyle_bytes)
        wrote.append("lifestyle")

    status = (
        f"name={meta.get('proposed_name', '?')!r:50} "
        f"type={meta.get('piece_type', '?')}  "
        f"wrote={','.join(wrote) or 'NONE'}"
    )
    return len(wrote) == 2, status


# ── Driver ────────────────────────────────────────────────────────
async def main(limit: int | None, force: bool) -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    raw_dir = repo_root / RAW_DIR_REL
    out_dir = repo_root / OUT_DIR_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(
        p
        for p in raw_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
    )
    if limit:
        images = images[:limit]

    print(f"Source: {raw_dir}")
    print(f"Output: {out_dir}")
    print(f"Processing {len(images)} image(s).")
    print()

    ok = 0
    bad = 0
    for i, path in enumerate(images, start=1):
        try:
            success, status = await process_one(path, out_dir, force=force)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i:>3}/{len(images)}] FAILED {path.name}: {exc}")
            bad += 1
            continue
        marker = "✓" if success else "✗"
        print(f"  [{i:>3}/{len(images)}] {marker}  {path.name}  →  {status}")
        if success:
            ok += 1
        else:
            bad += 1

    print()
    print(f"OK: {ok}   Failed/partial: {bad}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N images (use to test before a full run).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if outputs already exist.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(limit=args.limit, force=args.force)))
