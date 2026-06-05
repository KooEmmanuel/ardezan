// Brand tokens mirrored from frontend/app/globals.css so the coded Act 2
// reads as the real Ardezan UI, not a lookalike.
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadCormorant } from "@remotion/google-fonts/CormorantGaramond";

const { fontFamily: sansFamily } = loadInter("normal", {
  weights: ["300", "400", "500", "600"],
});
const { fontFamily: serifFamily } = loadCormorant("normal", {
  weights: ["400", "500", "600", "700"],
});

export const FONTS = {
  sans: sansFamily,
  // Cormorant Garamond — used for headlines/prices, matches .font-display.
  serif: serifFamily,
};

export const COLORS = {
  paper: "#fafafa",
  ink: "#050505",
  inkSoft: "#1a1a1a",
  muted: "#6b6b6b",
  line: "#e5e5e5",
  white: "#ffffff",
  // Subtle warm-to-cool bespoke gradient (the "Design your own" chip).
  bespoke: "linear-gradient(135deg, #c79a3d 0%, #5b1a1a 50%, #1a3a5b 100%)",
};

export const VIDEO = {
  fps: 30,
  width: 1920,
  height: 1080,
};

// Global pacing knob — raise to slow the whole reel down, lower to speed up.
export const SLOWDOWN = 1.5;
// Gentle slow-mo applied to the Veo footage so Act 1 doesn't feel rushed.
export const ACT1_PLAYBACK = 0.85;

// Single source of truth for the timeline (in frames @ 30fps). Tweak here
// and every Sequence + the composition durationInFrames follow.
const s = (sec: number) => Math.round(sec * VIDEO.fps);
// Act 2 scene length, scaled by the global slowdown.
const a2 = (sec: number) => Math.round(sec * VIDEO.fps * SLOWDOWN);

export const TIMING = {
  // ── Act 1: studio cinematic (Veo footage / coded placeholder) ──
  // Longer windows so the slow-mo'd dolly-in + posing play out fully.
  act1: {
    start: 0,
    reveal: s(9), // black → dolly-in → guy revealed
    posing: s(8), // photographer shoots, he poses
  },
  // ── Act 2: coded try-on → buy flow (all scaled by SLOWDOWN) ──
  act2: {
    button: a2(2.6), // animated CTA + cursor click
    card: a2(1.6), // result/upload card slides in
    upload: a2(2.4), // pick a photo
    tryOn: a2(1.6), // "Try On Now" click
    processing: a2(3.0), // "Re-imagining… / Re-designing…"
    reveal: a2(2.6), // final looks reveal
    scroll: a2(2.4), // storefront auto-scroll
    checkout: a2(2.2), // click product → add to cart → buy
  },
  crossfade: s(0.5),
};

export const act1Total = TIMING.act1.reveal + TIMING.act1.posing;
export const act2Total =
  TIMING.act2.button +
  TIMING.act2.card +
  TIMING.act2.upload +
  TIMING.act2.tryOn +
  TIMING.act2.processing +
  TIMING.act2.reveal +
  TIMING.act2.scroll +
  TIMING.act2.checkout;

// Act 1 and Act 2 sit back-to-back; the flash Transition straddles the cut.
export const TRANSITION = { pre: 10, post: 50 };
export const HERO_DURATION = act1Total + act2Total;
