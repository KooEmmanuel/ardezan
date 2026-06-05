import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

type Point = { x: number; y: number };

// A macOS-style pointer that eases between waypoints and pulses on "click".
// Waypoints are [frame, x, y]; clickFrames trigger a ring + dip.
export const Cursor: React.FC<{
  waypoints: { frame: number; x: number; y: number }[];
  clickFrames?: number[];
}> = ({ waypoints, clickFrames = [] }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pos = positionAt(frame, waypoints);
  const click = clickFrames.find((c) => frame >= c && frame < c + fps * 0.4);
  const clickProgress = click
    ? spring({ frame: frame - click, fps, config: { damping: 12, stiffness: 220 } })
    : 0;
  const dip = click ? interpolate(clickProgress, [0, 0.5, 1], [0, 0.85, 1]) : 1;

  return (
    <div
      style={{
        position: "absolute",
        left: pos.x,
        top: pos.y,
        transform: `scale(${0.96 + 0.04 * dip})`,
        zIndex: 100,
        pointerEvents: "none",
        filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.35))",
      }}
    >
      {/* Click ripple */}
      {click ? (
        <div
          style={{
            position: "absolute",
            left: 2,
            top: 2,
            width: 40,
            height: 40,
            marginLeft: -20,
            marginTop: -20,
            borderRadius: "50%",
            border: "2px solid rgba(0,0,0,0.5)",
            transform: `scale(${interpolate(clickProgress, [0, 1], [0.2, 1.6])})`,
            opacity: interpolate(clickProgress, [0, 1], [0.6, 0]),
          }}
        />
      ) : null}
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
        <path
          d="M5 3 L5 19 L9.2 15 L12 21 L14.5 19.8 L11.7 14 L17 14 Z"
          fill="#fff"
          stroke="#050505"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};

function positionAt(frame: number, waypoints: { frame: number; x: number; y: number }[]): Point {
  if (waypoints.length === 0) return { x: 0, y: 0 };
  if (frame <= waypoints[0].frame) return waypoints[0];
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    if (frame >= a.frame && frame <= b.frame) {
      // Ease-in-out between the two waypoints.
      const t = interpolate(frame, [a.frame, b.frame], [0, 1], {
        easing: easeInOut,
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
    }
  }
  return waypoints[waypoints.length - 1];
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const easeInOut = (t: number) =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
