import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONTS } from "../theme";

// The bridge between Act 1 (studio) and Act 2 (UI). Thematically a camera
// FLASH: the photographer fires, the frame blooms to white, and we land in
// the bright product UI. An animated serif line rides through the bloom.
//
// `boundary` is the local frame where Act 1 ends / Act 2 begins (the white
// peak). The overlay is mounted from (boundary - pre) and runs (pre + post).
export const Transition: React.FC<{ boundary: number }> = ({ boundary }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Flash: blooms to white just before the cut, HOLDS opaque while the line
  // is on screen (so Act 2 forms hidden behind it), then lifts to reveal Act 2.
  const flashUp = interpolate(frame, [boundary - 8, boundary], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const flashDown = interpolate(frame, [boundary + 30, boundary + 44], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const flash = Math.min(flashUp, flashDown);

  // Animated line — words spring up one after another over the bloom, then lift
  // away in sync with the white, so it never overlaps Act 2's headline.
  const words = ["Now", "it's", "your", "turn."];
  const textIn = interpolate(frame, [boundary - 4, boundary + 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textOut = interpolate(frame, [boundary + 22, boundary + 30], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textOpacity = Math.min(textIn, textOut);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* White camera-flash bloom */}
      <AbsoluteFill style={{ background: "#ffffff", opacity: flash }} />

      {/* Kinetic line, centered, ink on the bloom */}
      {textOpacity > 0.01 ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <div style={{ display: "flex", gap: 22, opacity: textOpacity }}>
            {words.map((w, i) => {
              const wp = spring({ frame: frame - (boundary - 2) - i * 4, fps, config: { damping: 16, stiffness: 140 } });
              return (
                <span
                  key={w}
                  style={{
                    fontFamily: FONTS.serif,
                    fontSize: 84,
                    fontStyle: i === 3 ? "italic" : "normal",
                    color: COLORS.ink,
                    transform: `translateY(${interpolate(wp, [0, 1], [40, 0])}px)`,
                    opacity: wp,
                  }}
                >
                  {w}
                </span>
              );
            })}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
