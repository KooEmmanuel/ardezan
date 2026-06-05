import React from "react";
import { AbsoluteFill } from "remotion";
import { COLORS, FONTS } from "../theme";

// A minimal browser/app shell so Act 2 reads as "this is the Ardezan site",
// not a floating widget. Top bar with the wordmark + faux nav.
export const AppChrome: React.FC<{ children: React.ReactNode; scrollY?: number }> = ({
  children,
  scrollY = 0,
}) => {
  return (
    <AbsoluteFill style={{ background: COLORS.paper, fontFamily: FONTS.sans }}>
      {/* Top bar */}
      <div
        style={{
          height: 84,
          flexShrink: 0,
          borderBottom: `1px solid ${COLORS.line}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 56px",
          background: COLORS.paper,
          zIndex: 20,
        }}
      >
        <div style={{ fontFamily: FONTS.serif, fontSize: 30, letterSpacing: 1, color: COLORS.ink }}>
          Ardezan
        </div>
        <div style={{ display: "flex", gap: 36, color: COLORS.muted, fontSize: 16, letterSpacing: 0.5 }}>
          <span>Women</span>
          <span>Men</span>
          <span>Bespoke</span>
          <span>Try-On</span>
        </div>
        <div style={{ display: "flex", gap: 22, color: COLORS.ink, fontSize: 16 }}>
          <span>Search</span>
          <span>Bag</span>
        </div>
      </div>

      {/* Scrollable canvas */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            transform: `translateY(${-scrollY}px)`,
          }}
        >
          {children}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// Shared primitives ────────────────────────────────────────────────
export const PrimaryButton: React.FC<{
  children: React.ReactNode;
  pressed?: number; // 0..1 press depth
  style?: React.CSSProperties;
}> = ({ children, pressed = 0, style }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      background: COLORS.ink,
      color: COLORS.paper,
      minHeight: 56,
      padding: "0 34px",
      borderRadius: 12,
      fontWeight: 500,
      fontSize: 19,
      transform: `translateY(${pressed * 2}px)`,
      boxShadow: `0 ${18 - pressed * 10}px ${40 - pressed * 16}px -18px rgba(0,0,0,0.5)`,
      ...style,
    }}
  >
    {children}
  </div>
);

export const AiPill: React.FC<{ style?: React.CSSProperties }> = ({ style }) => (
  <span
    style={{
      background: "#000",
      color: "#fff",
      fontWeight: 600,
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      fontSize: 12,
      padding: "5px 11px",
      borderRadius: 999,
      ...style,
    }}
  >
    AI preview
  </span>
);
