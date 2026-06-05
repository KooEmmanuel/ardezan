import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  OffthreadVideo,
  Series,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { ACT1_PLAYBACK, COLORS, FONTS, TIMING } from "../theme";

// Flip to true once the Veo clips exist at:
//   public/videos/studio_reveal.mp4   (dark dolly-in → guy revealed)
//   public/videos/studio_posing.mp4   (photographer shoots, he poses)
// Generate them with scripts/generate-images.py + generate-videos.py.
export const HAS_VEO_FOOTAGE = true;

export const Act1Studio: React.FC = () => {
  if (HAS_VEO_FOOTAGE) {
    return (
      <Series>
        <Series.Sequence durationInFrames={TIMING.act1.reveal}>
          <AbsoluteFill style={{ background: "#000" }}>
            <OffthreadVideo src={staticFile("videos/studio_reveal.mp4")} playbackRate={ACT1_PLAYBACK} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </AbsoluteFill>
        </Series.Sequence>
        <Series.Sequence durationInFrames={TIMING.act1.posing}>
          <AbsoluteFill style={{ background: "#000" }}>
            <OffthreadVideo src={staticFile("videos/studio_posing.mp4")} playbackRate={ACT1_PLAYBACK} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </AbsoluteFill>
        </Series.Sequence>
      </Series>
    );
  }
  return (
    <Series>
      <Series.Sequence durationInFrames={TIMING.act1.reveal}>
        <RevealPlaceholder />
      </Series.Sequence>
      <Series.Sequence durationInFrames={TIMING.act1.posing}>
        <PosingPlaceholder />
      </Series.Sequence>
    </Series>
  );
};

// ── Coded placeholder: dark studio, slow dolly-in, light comes up ────
const RevealPlaceholder: React.FC = () => {
  const frame = useCurrentFrame();
  const dur = TIMING.act1.reveal;
  const zoom = interpolate(frame, [0, dur], [1.4, 1.0]); // camera pushes in
  const light = interpolate(frame, [0, dur * 0.5, dur], [0, 0.4, 1]); // lights rise
  const figureOpacity = interpolate(frame, [dur * 0.35, dur * 0.8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
        <Studio light={light} figureOpacity={figureOpacity} />
      </AbsoluteFill>
      {/* Cinematic vignette */}
      <AbsoluteFill style={{ boxShadow: "inset 0 0 400px 120px rgba(0,0,0,0.9)" }} />
      {/* Fade up from pure black at the very start */}
      <AbsoluteFill style={{ background: "#000", opacity: interpolate(frame, [0, 18], [1, 0], { extrapolateRight: "clamp" }) }} />
    </AbsoluteFill>
  );
};

// ── Coded placeholder: the shoot — flashes + pose shifts ─────────────
const PosingPlaceholder: React.FC = () => {
  const frame = useCurrentFrame();
  // Camera flash spikes roughly once a second.
  const flash = Math.max(
    0,
    ...[18, 48, 78, 108].map((f) => (frame >= f && frame < f + 5 ? interpolate(frame, [f, f + 5], [0.85, 0], { extrapolateRight: "clamp" }) : 0)),
  );
  const pose = Math.floor(frame / 30) % 3; // shift stance between flashes
  const sway = Math.sin(frame / 10) * 6;
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <Studio light={1} figureOpacity={1} poseIndex={pose} sway={sway} />
      <AbsoluteFill style={{ boxShadow: "inset 0 0 400px 120px rgba(0,0,0,0.85)" }} />
      {/* Photographer silhouette, foreground left */}
      <div style={{ position: "absolute", left: 120, bottom: 0, width: 260, height: 620, opacity: 0.92 }}>
        <Photographer />
      </div>
      {/* Flash */}
      <AbsoluteFill style={{ background: "#fff", opacity: flash }} />
    </AbsoluteFill>
  );
};

// ── A minimalist studio: seamless sweep, softbox glow, standing figure ──
const Studio: React.FC<{ light: number; figureOpacity: number; poseIndex?: number; sway?: number }> = ({ light, figureOpacity, poseIndex = 0, sway = 0 }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end" }}>
    {/* Seamless cyclorama sweep */}
    <AbsoluteFill style={{ background: `radial-gradient(120% 90% at 50% 35%, rgba(70,70,75,${0.25 + light * 0.6}) 0%, rgba(20,20,22,${0.3 + light * 0.3}) 45%, #060607 80%)` }} />
    {/* Softbox key light */}
    <div style={{ position: "absolute", top: "8%", right: "16%", width: 260, height: 360, borderRadius: 24, background: `rgba(255,255,255,${0.06 + light * 0.16})`, filter: "blur(40px)" }} />
    {/* Floor pool of light */}
    <div style={{ position: "absolute", bottom: "6%", width: "60%", height: 120, borderRadius: "50%", background: `rgba(255,255,255,${0.04 + light * 0.1})`, filter: "blur(50px)" }} />
    {/* Standing figure */}
    <div style={{ opacity: figureOpacity, transform: `translateX(${sway}px)`, marginBottom: "4%" }}>
      <Figure pose={poseIndex} light={light} />
    </div>
  </AbsoluteFill>
);

// Stylized standing model silhouette (placeholder for the Veo human).
const Figure: React.FC<{ pose: number; light: number }> = ({ pose, light }) => {
  const armR = pose === 1 ? -28 : pose === 2 ? 14 : -6; // change stance
  const fill = `rgba(${18 + light * 18}, ${18 + light * 18}, ${22 + light * 20}, 1)`;
  const rim = `rgba(255,255,255,${0.18 + light * 0.22})`;
  return (
    <svg width="300" height="640" viewBox="0 0 300 640" style={{ filter: `drop-shadow(0 0 30px rgba(255,255,255,${light * 0.18}))` }}>
      <g fill={fill} stroke={rim} strokeWidth="2">
        <circle cx="150" cy="70" r="46" />
        <rect x="120" y="120" width="60" height="30" rx="14" />
        {/* torso */}
        <path d="M104 150 Q150 138 196 150 L188 360 Q150 374 112 360 Z" />
        {/* legs */}
        <path d="M118 356 L132 620 L150 620 L150 372 Z" />
        <path d="M182 356 L168 620 L150 620 L150 372 Z" />
        {/* arms */}
        <g transform={`rotate(${armR} 110 170)`}>
          <path d="M104 158 L86 350 L102 354 L120 168 Z" />
        </g>
        <g transform={`rotate(${-armR} 190 170)`}>
          <path d="M196 158 L214 350 L198 354 L180 168 Z" />
        </g>
      </g>
    </svg>
  );
};

const Photographer: React.FC = () => (
  <svg width="260" height="620" viewBox="0 0 260 620" style={{ position: "absolute", bottom: 0 }}>
    <g fill="#040405">
      <circle cx="120" cy="120" r="44" />
      <path d="M70 165 Q130 150 190 165 L180 420 L80 420 Z" />
      {/* camera up at face */}
      <rect x="150" y="96" width="86" height="56" rx="8" />
      <circle cx="200" cy="124" r="20" fill="#0b0b0d" stroke="#222" strokeWidth="3" />
      <path d="M180 420 L96 620 L140 620 L160 440 Z" />
      <path d="M100 420 L150 620 L190 620 L150 440 Z" />
    </g>
  </svg>
);

// Optional brand stinger that can ride the end of Act 1 (unused by default).
export const StudioWordmark: React.FC = () => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: FONTS.serif, color: COLORS.white, fontSize: 64, letterSpacing: 2 }}>Ardezan</div>
  </AbsoluteFill>
);
