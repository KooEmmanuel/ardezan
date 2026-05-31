"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ensureAnonId } from "@/lib/anon";
import { hasCachedPhoto, savePhoto } from "@/lib/photo-cache";
import {
  HERO_LOOK_SLOTS,
  type HeroLookSlot,
  type SiteMediaSlot,
} from "@/lib/types";

const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
]);

// Rotation period for the cascade. Each position advances together so the
// cascade always shows three consecutive looks from the pool.
const CASCADE_ROTATE_MS = 5200;

type SlotMap = Record<SiteMediaSlot, string | null>;

export function HomeHero({
  initialSiteMedia,
  picsumFallback,
}: {
  initialSiteMedia: SlotMap;
  picsumFallback: Record<SiteMediaSlot, string>;
}) {
  const router = useRouter();

  const slotUrl = (slot: SiteMediaSlot): string =>
    initialSiteMedia[slot] ?? picsumFallback[slot];

  return (
    <section className="ai-canvas">
      <div className="max-w-[1280px] mx-auto px-4 sm:px-5 pt-8 sm:pt-14 pb-12 sm:pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.05fr] gap-10 lg:gap-14 items-center">
          <HeroCopyAndForm onStart={() => router.push("/try-on")} />
          <HeroCascade slotUrl={slotUrl} />
        </div>
      </div>
    </section>
  );
}

// ─── Cross-fading image ───────────────────────────────────────────
function FadingImage({ src, alt }: { src: string; alt?: string }) {
  const [layers, setLayers] = useState<{ prev: string | null; current: string }>(
    { prev: null, current: src },
  );
  const [fading, setFading] = useState(false);

  useEffect(() => {
    if (src === layers.current) return;
    setLayers({ prev: layers.current, current: src });
    setFading(true);
    const t = window.setTimeout(() => {
      setFading(false);
      setLayers((l) => ({ prev: null, current: l.current }));
    }, 700);
    return () => window.clearTimeout(t);
  }, [src, layers.current]);

  return (
    <div className="absolute inset-0">
      {layers.prev ? (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          alt=""
          aria-hidden
          className="absolute inset-0 w-full h-full object-cover transition-opacity duration-700 ease-out"
          src={layers.prev}
          style={{ opacity: fading ? 0 : 1 }}
        />
      ) : null}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        alt={alt ?? ""}
        className="absolute inset-0 w-full h-full object-cover transition-opacity duration-700 ease-out"
        src={layers.current}
        style={{
          opacity: 1,
          animation: fading ? "fadeInImage 700ms ease-out" : undefined,
        }}
      />
    </div>
  );
}

// ─── Hero cascade (3 tilted glass cards, rotating through pool) ───
function HeroCascade({ slotUrl }: { slotUrl: (slot: SiteMediaSlot) => string }) {
  const [rotation, setRotation] = useState(0);
  useEffect(() => {
    const id = window.setInterval(
      () => setRotation((r) => (r + 1) % HERO_LOOK_SLOTS.length),
      CASCADE_ROTATE_MS,
    );
    return () => window.clearInterval(id);
  }, []);

  const lookAt = (offset: number): HeroLookSlot =>
    HERO_LOOK_SLOTS[(rotation + offset) % HERO_LOOK_SLOTS.length];

  return (
    <div className="relative h-[440px] sm:h-[520px] lg:h-[600px] hidden sm:block">
      <div
        className="absolute left-0 top-8 w-[55%] glass-strong overflow-hidden"
        style={{
          transform: "rotate(-4deg)",
          boxShadow: "0 30px 60px -25px rgba(0,0,0,0.2)",
        }}
      >
        <div className="ratio-45 relative overflow-hidden">
          <FadingImage src={slotUrl(lookAt(2))} />
        </div>
      </div>

      <div
        className="absolute right-0 top-0 w-[55%] glass-strong overflow-hidden"
        style={{
          transform: "rotate(5deg)",
          boxShadow: "0 30px 60px -25px rgba(0,0,0,0.16)",
        }}
      >
        <div className="ratio-45 relative overflow-hidden">
          <FadingImage src={slotUrl(lookAt(1))} />
        </div>
      </div>

      <div
        className="absolute left-1/2 -translate-x-1/2 bottom-0 w-[62%] glass-strong overflow-hidden"
        style={{ boxShadow: "0 40px 80px -30px rgba(0,0,0,0.35)" }}
      >
        <div className="ratio-45 relative overflow-hidden">
          <FadingImage src={slotUrl(lookAt(0))} />
          <span className="absolute top-3 left-3 pill pill-ai z-10">AI preview</span>
        </div>
        <div className="p-3 bg-white/85 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-display text-base leading-tight">Outdoor Linen</div>
              <div className="text-[11px] text-[color:var(--muted)]">3-piece · size M</div>
            </div>
            <div className="text-sm">$327</div>
          </div>
        </div>
      </div>

      <div
        className="absolute -bottom-4 right-2 sm:right-6 glass-strong px-4 py-2.5 flex items-center gap-3"
        style={{ boxShadow: "0 20px 40px -15px rgba(0,0,0,0.18)" }}
      >
        <div className="w-8 h-8 rounded-full bg-black flex items-center justify-center text-white font-display text-sm">
          O
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Last styled · this morning
          </div>
          <div className="font-display text-sm leading-tight">
            Olivia, 5&apos;7&quot; · regular fit
          </div>
        </div>
      </div>

      <div className="absolute top-4 right-12 text-black opacity-50">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M12 2 L13.5 9 L20 10.5 L13.5 12 L12 19 L10.5 12 L4 10.5 L10.5 9 Z" />
        </svg>
      </div>
    </div>
  );
}

// ─── Hero left: copy + upload form ───────────────────────────────
function HeroCopyAndForm({ onStart }: { onStart: () => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [hasSaved, setHasSaved] = useState(false);
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void hasCachedPhoto().then(setHasSaved);
  }, []);

  function accept(file: File | null) {
    if (!file) return;
    if (!ALLOWED_MIME.has(file.type.toLowerCase())) {
      setError("Unsupported file type. Use JPEG, PNG, WebP, or HEIC.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("File is over 20 MB — pick a smaller one.");
      return;
    }
    setPhoto(file);
    setError(null);
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    accept(event.target.files?.[0] ?? null);
  }
  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragging(true);
  }
  function onDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    accept(e.dataTransfer.files?.[0] ?? null);
  }

  async function onStyleMe() {
    if (submitting) return;
    // No new file, no cached file → can't start. Bounce to /try-on so the
    // upload page guides them.
    if (!photo && !hasSaved) {
      setError("Pick a full-body photo first.");
      return;
    }
    if (!ageConfirmed) {
      setError("Confirm you're 18 or older to continue.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      ensureAnonId();
      // Persist the freshly-picked photo so /try-on (and every product's
      // Try-on button) can reuse it without re-uploading.
      if (photo) await savePhoto(photo);
      onStart();
    } catch {
      setSubmitting(false);
      setError("Couldn't save your photo locally. Try again.");
    }
  }

  return (
    <div className="reveal">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-3">
        An AI-native fitting room
      </div>
      <h1 className="font-display text-[3.1rem] sm:text-6xl leading-[0.98] sm:leading-[1.02] mb-4">
        See clothes on <i>you</i>,<br />not on a model.
      </h1>
      <p className="text-[color:var(--muted)] text-base sm:text-lg leading-relaxed mb-6 max-w-md">
        Upload one full-body photo. Our stylist drapes ten looks onto your shape —
        fit, fabric, and proportion — in about fifteen seconds.
      </p>

      <div
        className="glass p-4 sm:p-6 max-w-md"
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        <label
          className="block cursor-pointer rounded-xl border-2 border-dashed transition py-10 text-center"
          style={{
            borderColor: dragging ? "var(--ink)" : "rgba(255,255,255,0.8)",
            background: dragging ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.3)",
          }}
        >
          <div className="mx-auto mb-3 w-12 h-12 rounded-full bg-black/10 text-black flex items-center justify-center">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
            </svg>
          </div>
          <div className="text-sm font-medium px-3 break-words">
            {photo
              ? photo.name
              : hasSaved
                ? "Saved photo — ready to style"
                : dragging
                  ? "Drop the photo to upload"
                  : "Drag a full-body photo here"}
          </div>
          <div className="text-xs text-[color:var(--muted)] mt-1">
            {photo
              ? `${(photo.size / 1024 / 1024).toFixed(2)} MB · ready`
              : (
                <>
                  or <span className="underline">choose from your device</span>
                </>
              )}
          </div>
          <input
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
            aria-label="Upload a full-body photo"
            className="hidden"
            onChange={onFile}
            ref={inputRef}
            type="file"
          />
        </label>

        <details className="mt-4 group">
          <summary className="cursor-pointer text-sm text-[color:var(--ink-soft)] flex items-center justify-between">
            <span>Refine — height, fit, occasion</span>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="transition group-open:rotate-180"
              aria-hidden
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </summary>
          <div className="mt-3 space-y-3">
            <div>
              <div className="text-xs text-[color:var(--muted)] mb-1">Height</div>
              <input aria-label="Height" className="input input-glass" placeholder='5&apos; 9"' />
            </div>
            <div>
              <div className="text-xs text-[color:var(--muted)] mb-1">Fit preference</div>
              <div className="grid grid-cols-3 gap-2">
                <button className="btn-secondary text-xs" type="button">Slim</button>
                <button
                  className="btn-secondary text-xs"
                  style={{ background: "var(--ivory)", borderColor: "var(--accent)" }}
                  type="button"
                >
                  Regular
                </button>
                <button className="btn-secondary text-xs" type="button">Oversized</button>
              </div>
            </div>
            <div>
              <div className="text-xs text-[color:var(--muted)] mb-1">Occasion</div>
              <input aria-label="Occasion" className="input input-glass" placeholder="e.g. outdoor summer wedding" />
            </div>
          </div>
        </details>

        <label className="flex items-start gap-2 mt-4">
          <input
            checked={ageConfirmed}
            className="mt-1"
            onChange={(e) => setAgeConfirmed(e.target.checked)}
            type="checkbox"
          />
          <span className="text-[11px] text-[color:var(--muted)] leading-snug">
            I&apos;m 18 or older and consent to my photo being processed by Google for AI analysis.
          </span>
        </label>

        {error ? (
          <p className="text-[11px] mt-2" role="alert" style={{ color: "#8d1717" }}>
            {error}
          </p>
        ) : null}

        <button
          className="btn-primary w-full mt-4"
          disabled={submitting || (!photo && !hasSaved)}
          onClick={onStyleMe}
          type="button"
        >
          {submitting ? "Saving photo…" : hasSaved && !photo ? "Use saved photo" : "Style me"}
        </button>
        <div className="text-[11px] text-center text-[color:var(--muted)] mt-3">
          Your photo is cached on this device so every Try-on button works without re-uploading.
        </div>
      </div>
    </div>
  );
}
