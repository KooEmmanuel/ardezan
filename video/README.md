# Ardezan hero video (Remotion)

The homepage hero cinematic, as one looping ~29s reel:

- **Act 1 — The Studio** (AI video): black → slow dolly-in through a dark studio →
  the model revealed → photographer shoots him while he poses. Generated with
  **Gemini keyframes → Veo image-to-video**.
- **Act 2 — The Product** (coded): animated CTA → cursor click → upload a photo →
  "Try On Now" → "Re-imagining / Re-designing" → ten looks revealed → storefront
  auto-scroll → product → add to bag → buy → "Order placed." Pure Remotion, real
  Ardezan brand tokens (Inter + Cormorant Garamond, mono palette), real look images.

The two acts crossfade and the whole thing loops.

## Render

```bash
npm install
npm run render          # → out/hero.mp4  (h264)
npm run render:webm     # → out/hero.webm (vp8, ~1.2 MB)
npm run still           # → out/poster.png
npm run dev             # Remotion Studio — live-edit at localhost:3000
```

Then publish to the storefront:

```bash
cp out/hero.mp4 out/hero.webm out/poster.png ../frontend/public/site/
```

`components/hero-cinematic.tsx` in the frontend consumes those three files.

## Compositions

| id           | what                                  | use                         |
|--------------|---------------------------------------|-----------------------------|
| `HeroVideo`  | full reel (Act 1 + crossfade + Act 2) | the deliverable             |
| `Act2Flow`   | just the coded product flow           | fast iteration on the UI    |
| `Act1Studio` | just the studio cinematic             | fast iteration on the intro |

All timing lives in `src/theme.ts` (`TIMING`) — change a scene's seconds there and
every Sequence + the composition length follow automatically.

## Act 1: generating the real Veo footage

Out of the box Act 1 renders a **coded placeholder** (dark studio + silhouette) so
the reel renders with zero API cost. To swap in real AI footage:

```bash
set -a && source ../backend/.env && set +a     # GOOGLE_API_KEY / GEMINI_API_KEY
python3 scripts/generate-images.py             # → public/images/studio_{reveal,posing}.png
python3 scripts/generate-videos.py             # → public/videos/studio_{reveal,posing}.mp4  (Veo, paid)
```

Then flip the flag in `src/acts/Act1Studio.tsx`:

```ts
export const HAS_VEO_FOOTAGE = true;
```

…and re-render. The `Series.Sequence` durations trim each 8s Veo clip to the
timeline (6s reveal + 5s posing). Veo bills to Google Cloud — render one id first
to confirm billing, exactly like the kooe pipeline this is adapted from.

> Tip for seamless continuity: use the **last frame of `studio_reveal.mp4`** as the
> start-frame for `studio_posing.png` so the two clips read as one continuous shot.
