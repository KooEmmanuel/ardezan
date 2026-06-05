import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  Series,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { AiPill, AppChrome, PrimaryButton } from "../components/AppChrome";
import { Cursor } from "../components/Cursor";
import { COLORS, FONTS, SLOWDOWN, TIMING } from "../theme";

const img = (name: string) => staticFile(`site/${name}`);

const RESULTS = [
  { src: "hero_look_01.png", label: "Burgundy Set", price: "$284" },
  { src: "hero_look_02.png", label: "Kente Set", price: "$386" },
  { src: "hero_look_06.png", label: "Royal Agbada", price: "$418" },
];

// Each scene fades in over its first 8 frames so hard cuts feel intentional.
const SceneFade: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

export const Act2Flow: React.FC = () => {
  const t = TIMING.act2;
  return (
    <Series>
      <Series.Sequence durationInFrames={t.button}>
        <SceneFade><SceneButton /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.card}>
        <SceneFade><SceneCard /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.upload}>
        <SceneFade><SceneUpload /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.tryOn}>
        <SceneFade><SceneTryOn /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.processing}>
        <SceneFade><SceneProcessing /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.reveal}>
        <SceneFade><SceneReveal /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.scroll}>
        <SceneFade><SceneScroll /></SceneFade>
      </Series.Sequence>
      <Series.Sequence durationInFrames={t.checkout}>
        <SceneFade><SceneCheckout /></SceneFade>
      </Series.Sequence>
    </Series>
  );
};

// ─── Scene 1: hero headline + animated CTA, cursor clicks it ──────────
const SceneButton: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  const clickAt = TIMING.act2.button - 18;
  const pressed = frame >= clickAt ? interpolate(frame, [clickAt, clickAt + 6], [0, 1], { extrapolateRight: "clamp" }) : 0;

  return (
    <AppChrome>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        <div style={{ maxWidth: 1100, transform: `translateY(${interpolate(enter, [0, 1], [30, 0])}px)`, opacity: enter }}>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.18em", fontSize: 15, color: COLORS.muted, marginBottom: 18 }}>
            An AI-native fitting room
          </div>
          <div style={{ fontFamily: FONTS.serif, fontSize: 92, lineHeight: 1.0, color: COLORS.ink }}>
            See clothes on <i>you</i>,<br />not on a model.
          </div>
          <div style={{ marginTop: 44, display: "flex", justifyContent: "center" }}>
            <PrimaryButton pressed={pressed} style={{ fontSize: 22, minHeight: 64, padding: "0 44px" }}>
              Try it on
            </PrimaryButton>
          </div>
        </div>
      </AbsoluteFill>
      <Cursor
        waypoints={[
          { frame: 0, x: 1500, y: 980 },
          { frame: clickAt, x: 960, y: 712 },
          { frame: TIMING.act2.button, x: 960, y: 712 },
        ]}
        clickFrames={[clickAt]}
      />
    </AppChrome>
  );
};

// ─── Scene 2: the upload card slides in ──────────────────────────────
const SceneCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 130 } });
  return (
    <AppChrome>
      <Centered>
        <div style={{ transform: `scale(${interpolate(enter, [0, 1], [0.9, 1])})`, opacity: enter }}>
          <UploadCard state="empty" />
        </div>
      </Centered>
    </AppChrome>
  );
};

// ─── Scene 3: cursor clicks dropzone, photo fills the card ───────────
const SceneUpload: React.FC = () => {
  const frame = useCurrentFrame();
  const clickAt = 18;
  const filled = interpolate(frame, [clickAt + 4, clickAt + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AppChrome>
      <Centered>
        <UploadCard state="filling" fill={filled} />
      </Centered>
      <Cursor
        waypoints={[
          { frame: 0, x: 1300, y: 320 },
          { frame: clickAt, x: 960, y: 470 },
          { frame: TIMING.act2.upload, x: 960, y: 470 },
        ]}
        clickFrames={[clickAt]}
      />
    </AppChrome>
  );
};

// ─── Scene 4: "Try On Now" button + click ────────────────────────────
const SceneTryOn: React.FC = () => {
  const frame = useCurrentFrame();
  const clickAt = TIMING.act2.tryOn - 16;
  const pressed = frame >= clickAt ? interpolate(frame, [clickAt, clickAt + 6], [0, 1], { extrapolateRight: "clamp" }) : 0;
  return (
    <AppChrome>
      <Centered>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 26 }}>
          <UploadCard state="filled" fill={1} />
          <PrimaryButton pressed={pressed} style={{ fontSize: 21, minHeight: 60, padding: "0 48px" }}>
            Try On Now
          </PrimaryButton>
        </div>
      </Centered>
      <Cursor
        waypoints={[
          { frame: 0, x: 960, y: 470 },
          { frame: clickAt, x: 960, y: 838 },
          { frame: TIMING.act2.tryOn, x: 960, y: 838 },
        ]}
        clickFrames={[clickAt]}
      />
    </AppChrome>
  );
};

// ─── Scene 5: processing — Re-imagining / Re-designing ───────────────
const STATUS = ["Re-imagining your look…", "Re-designing the fit…", "Styling ten complete outfits…"];
const SceneProcessing: React.FC = () => {
  const frame = useCurrentFrame();
  const dur = TIMING.act2.processing;
  const idx = Math.min(STATUS.length - 1, Math.floor((frame / dur) * STATUS.length));
  const progress = interpolate(frame, [0, dur - 6], [0, 1], { extrapolateRight: "clamp" });
  const scanY = interpolate(frame % 30, [0, 30], [0, 100]);
  return (
    <AppChrome>
      <Centered>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
          <div style={{ position: "relative", width: 360, height: 480, borderRadius: 18, overflow: "hidden", boxShadow: "0 40px 80px -30px rgba(0,0,0,0.4)" }}>
            <Img src={img("hero_mobile.png")} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "saturate(0.6) brightness(1.04)" }} />
            <div style={{ position: "absolute", left: 0, right: 0, top: `${scanY}%`, height: "10%", background: "linear-gradient(180deg, transparent, rgba(255,255,255,0.75), transparent)", filter: "blur(3px)" }} />
            <AiPill style={{ position: "absolute", top: 16, left: 16 }} />
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontFamily: FONTS.serif, fontSize: 34, color: COLORS.ink }}>{STATUS[idx]}</div>
            <div style={{ width: 360, height: 4, background: COLORS.line, borderRadius: 99, marginTop: 18, overflow: "hidden" }}>
              <div style={{ width: `${progress * 100}%`, height: "100%", background: COLORS.ink }} />
            </div>
          </div>
        </div>
      </Centered>
    </AppChrome>
  );
};

// ─── Scene 6: final looks reveal (cascade) ───────────────────────────
const SceneReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AppChrome>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.18em", fontSize: 14, color: COLORS.muted }}>Ten looks · on you</div>
          <div style={{ fontFamily: FONTS.serif, fontSize: 48, color: COLORS.ink, marginTop: 6 }}>Your fitting room</div>
        </div>
        <div style={{ display: "flex", gap: 30 }}>
          {RESULTS.map((r, i) => {
            const e = spring({ frame: frame - i * 8, fps, config: { damping: 15, stiffness: 110 } });
            return (
              <div key={r.src} style={{ transform: `translateY(${interpolate(e, [0, 1], [60, 0])}px)`, opacity: e }}>
                <ResultCard {...r} />
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AppChrome>
  );
};

// ─── Scene 7: storefront auto-scroll ─────────────────────────────────
const GRID = [
  { src: "hero_look_03.png", label: "Linen Overshirt", price: "$190" },
  { src: "hero_look_04.png", label: "Wide Trouser", price: "$160" },
  { src: "hero_look_05.png", label: "Ankara Wrap Dress", price: "$240" },
  { src: "hero_look_01.png", label: "Burgundy Set", price: "$284" },
  { src: "hero_look_02.png", label: "Kente Set", price: "$386" },
  { src: "hero_look_06.png", label: "Royal Agbada", price: "$418" },
];
const SceneScroll: React.FC = () => {
  const frame = useCurrentFrame();
  const scrollY = interpolate(frame, [0, TIMING.act2.scroll], [0, 520], { extrapolateRight: "clamp" });
  return (
    <AppChrome scrollY={scrollY}>
      <div style={{ padding: "48px 80px 80px" }}>
        <div style={{ fontFamily: FONTS.serif, fontSize: 40, color: COLORS.ink, marginBottom: 28 }}>New this week</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 30 }}>
          {GRID.map((p) => (
            <ProductTile key={p.label} {...p} />
          ))}
        </div>
      </div>
    </AppChrome>
  );
};

// ─── Scene 8: product → add to bag → buy → done ──────────────────────
const SceneCheckout: React.FC = () => {
  const frame = useCurrentFrame();
  const dur = TIMING.act2.checkout;
  // Internal beats scaled by the same slowdown so the clicks aren't rushed.
  const addAt = Math.round(16 * SLOWDOWN);
  const buyAt = Math.round(38 * SLOWDOWN);
  const doneAt = Math.round(54 * SLOWDOWN);
  const bagCount = frame >= addAt ? 1 : 0;
  const showBuy = frame >= addAt + 4;
  const done = frame >= doneAt;
  const doneScale = done ? interpolate(frame, [doneAt, doneAt + 8], [0.7, 1], { extrapolateRight: "clamp" }) : 0;
  const addPressed = frame >= addAt && frame < addAt + 6 ? 1 : 0;
  const buyPressed = frame >= buyAt && frame < buyAt + 6 ? 1 : 0;

  return (
    <AppChrome>
      <div style={{ position: "absolute", top: 0, right: 56, height: 84, display: "flex", alignItems: "center", color: COLORS.ink, fontSize: 16, zIndex: 30 }}>
        Bag ({bagCount})
      </div>
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 60, padding: "0 100px", opacity: done ? 0.25 : 1 }}>
        <ResultCard src="hero_look_01.png" label="" price="" big />
        <div style={{ width: 420 }}>
          <div style={{ fontFamily: FONTS.serif, fontSize: 52, color: COLORS.ink, lineHeight: 1.05 }}>Burgundy Set</div>
          <div style={{ fontSize: 26, color: COLORS.ink, margin: "14px 0 26px" }}>$284</div>
          <div style={{ display: "flex", gap: 12, marginBottom: 30 }}>
            {["S", "M", "L"].map((s) => (
              <div key={s} style={{ width: 52, height: 52, border: `1px solid ${s === "M" ? COLORS.ink : COLORS.line}`, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: COLORS.ink }}>{s}</div>
            ))}
          </div>
          <PrimaryButton pressed={addPressed} style={{ width: "100%", marginBottom: 14 }}>Add to bag</PrimaryButton>
          {showBuy ? (
            <div style={{ opacity: interpolate(frame, [addAt + 4, addAt + 12], [0, 1], { extrapolateRight: "clamp" }) }}>
              <PrimaryButton pressed={buyPressed} style={{ width: "100%", background: "#5b1a1a" }}>Buy now</PrimaryButton>
            </div>
          ) : null}
        </div>
      </AbsoluteFill>

      {done ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <div style={{ transform: `scale(${doneScale})`, textAlign: "center" }}>
            <div style={{ width: 96, height: 96, borderRadius: "50%", background: COLORS.ink, margin: "0 auto 22px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="46" height="46" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
            <div style={{ fontFamily: FONTS.serif, fontSize: 46, color: COLORS.ink }}>Order placed</div>
          </div>
        </AbsoluteFill>
      ) : null}

      <Cursor
        waypoints={[
          { frame: 0, x: 1400, y: 300 },
          { frame: addAt, x: 1180, y: 690 },
          { frame: buyAt, x: 1180, y: 762 },
          { frame: dur, x: 1180, y: 762 },
        ]}
        clickFrames={[addAt, buyAt]}
      />
    </AppChrome>
  );
};

// ─── Shared bits ─────────────────────────────────────────────────────
const Centered: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>{children}</AbsoluteFill>
);

const UploadCard: React.FC<{ state: "empty" | "filling" | "filled"; fill?: number }> = ({ state, fill = 0 }) => (
  <div style={{ width: 360, height: 480, borderRadius: 18, overflow: "hidden", position: "relative", background: COLORS.white, border: `1px ${state === "empty" ? "dashed" : "solid"} ${state === "empty" ? COLORS.muted : COLORS.line}`, boxShadow: "0 40px 80px -30px rgba(0,0,0,0.35)", display: "flex", alignItems: "center", justifyContent: "center" }}>
    {state === "empty" ? (
      <div style={{ textAlign: "center", color: COLORS.muted }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" style={{ margin: "0 auto 16px" }}><path d="M12 16V4m0 0l-5 5m5-5l5 5M5 20h14" stroke={COLORS.muted} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        <div style={{ fontSize: 18, color: COLORS.inkSoft }}>Upload a full-body photo</div>
        <div style={{ fontSize: 13, marginTop: 6 }}>PNG or JPG · stays on your device</div>
      </div>
    ) : (
      <>
        <Img src={img("hero_mobile.png")} style={{ width: "100%", height: "100%", objectFit: "cover", clipPath: `inset(${(1 - fill) * 100}% 0 0 0)` }} />
        <div style={{ position: "absolute", left: 14, bottom: 14, background: "rgba(0,0,0,0.72)", color: "#fff", fontSize: 12, padding: "5px 10px", borderRadius: 6 }}>photo.jpg</div>
      </>
    )}
  </div>
);

const ResultCard: React.FC<{ src: string; label: string; price: string; big?: boolean }> = ({ src, label, price, big }) => (
  <div style={{ width: big ? 380 : 300, borderRadius: 16, overflow: "hidden", background: COLORS.white, boxShadow: "0 36px 70px -28px rgba(0,0,0,0.32)" }}>
    <div style={{ position: "relative", width: "100%", height: big ? 506 : 400 }}>
      <Img src={img(src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <AiPill style={{ position: "absolute", top: 12, left: 12 }} />
    </div>
    {label ? (
      <div style={{ padding: "14px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontFamily: FONTS.serif, fontSize: 20, color: COLORS.ink }}>{label}</div>
          <div style={{ fontSize: 12, color: COLORS.muted }}>On you · size M</div>
        </div>
        <div style={{ fontSize: 16, color: COLORS.ink }}>{price}</div>
      </div>
    ) : null}
  </div>
);

const ProductTile: React.FC<{ src: string; label: string; price: string }> = ({ src, label, price }) => (
  <div style={{ borderRadius: 14, overflow: "hidden", background: COLORS.white, border: `1px solid ${COLORS.line}` }}>
    <div style={{ width: "100%", height: 360 }}>
      <Img src={img(src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>
    <div style={{ padding: "14px 16px", display: "flex", justifyContent: "space-between" }}>
      <div style={{ fontSize: 17, color: COLORS.ink }}>{label}</div>
      <div style={{ fontSize: 16, color: COLORS.muted }}>{price}</div>
    </div>
  </div>
);
