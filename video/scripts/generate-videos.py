#!/usr/bin/env python3
"""
Animate the Act 1 start-frames into 8-second clips via the Gemini Veo API,
then write them where Remotion expects them:

    public/videos/studio_reveal.mp4   (slow dolly-in, lights rise, guy revealed)
    public/videos/studio_posing.mp4   (the shoot — model poses, subtle flashes)

Veo is a paid, long-running operation (bills to Google Cloud). Run one id first
to confirm billing before batching. Mirrors clients/kooe/scripts/generate-videos.py.

Usage:
    set -a && source ../backend/.env && set +a
    python3 scripts/generate-videos.py studio_reveal     # one clip
    python3 scripts/generate-videos.py                   # both

After both clips land, flip HAS_VEO_FOOTAGE = true in src/acts/Act1Studio.tsx
and re-render: npm run render
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("MODEL", "veo-3.1-fast-generate-preview")
BASE = "https://generativelanguage.googleapis.com/v1beta"
IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "images")
VID_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "videos")

PROMPTS = {
    "studio_reveal": (
        "Cinematic slow dolly-in from far away through a dark photography studio "
        "toward a man standing centered in shadow. The camera glides forward smoothly "
        "as studio lights gradually rise, revealing him and his outfit. Moody to "
        "luminous, 35mm, shallow depth of field, premium fashion-film grade. He stays "
        "mostly still, a faint breath of movement. No text."
    ),
    "studio_posing": (
        "The model shifts confidently between editorial poses under bright studio "
        "light while the foreground photographer's camera fires — subtle bursts of "
        "flash light the scene. Natural, energetic fashion-shoot motion, slight handheld "
        "camera life, shallow depth of field, premium fashion-film grade. No text."
    ),
}


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def generate(key: str, vid: str) -> None:
    instance = {"prompt": PROMPTS[vid]}
    # Animate the matching start-frame unless USE_IMAGE=0 (pure text-to-video).
    if os.environ.get("USE_IMAGE", "1") != "0":
        img_path = os.path.abspath(os.path.join(IMG_DIR, f"{vid}.png"))
        if not os.path.exists(img_path):
            print(f"  ✗ {vid}: missing start-frame {img_path} — run generate-images.py first (or USE_IMAGE=0)")
            return
        with open(img_path, "rb") as f:
            instance["image"] = {
                "bytesBase64Encoded": base64.b64encode(f.read()).decode(),
                "mimeType": "image/png",
            }

    print(f"  • {vid}: submitting to {MODEL} ({'image' if 'image' in instance else 'text'}-to-video) ...")
    try:
        op = post(
            f"{BASE}/models/{MODEL}:predictLongRunning?key={key}",
            {"instances": [instance], "parameters": {"aspectRatio": "16:9"}},
        )
    except urllib.error.HTTPError as e:
        print(f"  ✗ {vid}: HTTP {e.code} — {e.read().decode()[:500]}")
        return

    op_name = op.get("name")
    if not op_name:
        print(f"  ✗ {vid}: no operation returned — {json.dumps(op)[:400]}")
        return

    for _ in range(60):  # up to ~10 min
        time.sleep(10)
        status = get(f"{BASE}/{op_name}?key={key}")
        if status.get("done"):
            break
        print(f"    … {vid}: still rendering")
    else:
        print(f"  ✗ {vid}: timed out")
        return

    if "error" in status:
        print(f"  ✗ {vid}: {json.dumps(status['error'])[:500]}")
        return

    resp = status.get("response", {})
    samples = (
        resp.get("generateVideoResponse", {}).get("generatedSamples")
        or resp.get("generatedSamples")
        or []
    )
    if not samples:
        print(f"  ✗ {vid}: no video in response — {json.dumps(resp)[:500]}")
        return

    video = samples[0].get("video", {})
    out = os.path.abspath(os.path.join(VID_DIR, f"{vid}.mp4"))
    if video.get("uri"):
        uri = video["uri"]
        dl = uri + (("&" if "?" in uri else "?") + f"key={key}")
        with urllib.request.urlopen(dl, timeout=300) as r, open(out, "wb") as f:
            f.write(r.read())
    elif video.get("bytesBase64Encoded"):
        with open(out, "wb") as f:
            f.write(base64.b64decode(video["bytesBase64Encoded"]))
    else:
        print(f"  ✗ {vid}: unrecognized payload — {json.dumps(video)[:300]}")
        return

    print(f"  ✓ {vid}: saved {out} ({os.path.getsize(out)//1024} KB)")


def main() -> None:
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GOOGLE_API_KEY (or GEMINI_API_KEY) not set — source backend/.env first")
    os.makedirs(VID_DIR, exist_ok=True)
    wanted = sys.argv[1:] or list(PROMPTS.keys())
    print(f"Veo image-to-video — model={MODEL}, clips={wanted}")
    for vid in wanted:
        if vid not in PROMPTS:
            print(f"  ✗ unknown id '{vid}' (choose from {list(PROMPTS)})")
            continue
        generate(key, vid)


if __name__ == "__main__":
    main()
