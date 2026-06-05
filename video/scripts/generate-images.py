#!/usr/bin/env python3
"""
Generate the two Act 1 start-frames for the Ardezan hero via the Gemini image
API. These stills become the start-frames fed to Veo in generate-videos.py.

Writes:
    public/images/studio_reveal.png   (dark studio, the guy standing, far)
    public/images/studio_posing.png   (the shoot — photographer + model posing)

Usage:
    set -a && source ../backend/.env && set +a     # provides GOOGLE_API_KEY/GEMINI key
    python3 scripts/generate-images.py                # both frames
    python3 scripts/generate-images.py studio_reveal  # just one

Mirrors clients/kooe/scripts/generate-images.py (same proven call shape).
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

MODEL = os.environ.get("IMAGE_MODEL", "gemini-3-pro-image")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "images")
SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "site")

# CONSISTENCY: every Act 1 keyframe is generated *from* one canonical photo of
# the model — the same image Remotion Act 2 uploads — so the studio guy, the
# uploaded photo, and the try-on are all the same person. Identity comes from
# the reference image; the prompt only changes the scene/lighting/pose.
SOURCE_IMAGE = os.environ.get("SOURCE_IMAGE", "hero_mobile.png")

# Shared cinematic spine so both frames read as one shoot. Photoreal, NOT the
# clean-white product look — Act 1 is a moody editorial studio.
STYLE = (
    "Photorealistic cinematic editorial fashion photography, 35mm, premium fashion-"
    "film color grade. "
    "CRITICAL IDENTITY: keep the exact same man from the reference image — same face, "
    "same skin tone, same hair, same burgundy outfit. Do not change his identity. "
    "CRITICAL FRAMING: full 16:9 widescreen composition, FULL-LENGTH full-body shot "
    "from head to toe — show his entire body including his shoes and the floor, with "
    "generous empty space above his head and on both sides. Do NOT crop the body, do "
    "NOT zoom into a portrait, do NOT cut off the legs or feet. The man should occupy "
    "only the central third of a wide frame. "
    "Absolutely no text, no words, no logos."
)

FRAMES = [
    {
        "id": "studio_reveal",
        "src": SOURCE_IMAGE,
        "prompt": (
            "Re-light and re-stage the same man from the reference as a wide full-length "
            "shot: he stands alone, centered, far back in a large DARK photography studio, "
            "mostly in shadow with a faint rim of light on him, vast empty negative space, "
            "the scene almost black with one distant softbox glowing. Dramatic low-key "
            "lighting, deep shadows, seamless dark charcoal backdrop. Quiet, anticipatory, "
            "the moment before the lights come up. "
        ),
    },
    {
        "id": "studio_posing",
        "src": SOURCE_IMAGE,
        "prompt": (
            "Re-stage the same man from the reference inside a now fully-lit photo studio: "
            "he stands confidently mid-pose under bright softbox light while a photographer "
            "in the left foreground (back to camera, partly silhouetted) raises a DSLR to "
            "shoot him. Energetic editorial fashion-shoot moment, bright softboxes, seamless "
            "dark backdrop. "
        ),
    },
]


def _load_src(name: str) -> dict | None:
    for base in (SITE_DIR, OUT_DIR):
        path = os.path.abspath(os.path.join(base, name))
        if os.path.exists(path):
            with open(path, "rb") as f:
                return {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(f.read()).decode()}}
    print(f"  ! source image '{name}' not found — falling back to text-only (identity NOT preserved)")
    return None


def generate(api_key: str, frame: dict) -> None:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={api_key}"
    )
    parts: list[dict] = [{"text": frame["prompt"] + " " + STYLE}]
    src = frame.get("src")
    if src:
        ref = _load_src(src)
        if ref:
            parts.append(ref)  # reference image → identity-preserving generation
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"  ✗ {frame['id']}: HTTP {e.code} — {e.read().decode()[:400]}")
        return

    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            out = os.path.abspath(os.path.join(OUT_DIR, f"{frame['id']}.png"))
            with open(out, "wb") as f:
                f.write(base64.b64decode(inline["data"]))
            print(f"  ✓ {frame['id']}: saved {out} ({os.path.getsize(out)//1024} KB)")
            return
    txt = " ".join(p.get("text", "") for p in parts) or json.dumps(data)[:400]
    print(f"  ✗ {frame['id']}: no image returned — {txt[:400]}")


def main() -> None:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GOOGLE_API_KEY (or GEMINI_API_KEY) not set — source backend/.env first")
    os.makedirs(OUT_DIR, exist_ok=True)
    wanted = set(sys.argv[1:])
    targets = [f for f in FRAMES if not wanted or f["id"] in wanted]
    print(f"Generating {len(targets)} Act 1 frame(s) with {MODEL} @ 16:9")
    for frame in targets:
        generate(api_key, frame)


if __name__ == "__main__":
    main()
