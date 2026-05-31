"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { PhotoPreview } from "@/components/photo-preview";
import { ensureAnonId } from "@/lib/anon";
import { api } from "@/lib/api";
import { maybeConvertHeic } from "@/lib/heic-to-jpeg";
import { clearPhoto, loadPhoto, savePhoto } from "@/lib/photo-cache";
import type { TryOnFormInput } from "@/lib/types";

const FIT_OPTIONS: NonNullable<TryOnFormInput["fit_preference"]>[] = [
  "slim",
  "regular",
  "relaxed",
  "oversized",
];

const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
]);

export default function TryOnPage() {
  return (
    <Suspense fallback={null}>
      <TryOnInner />
    </Suspense>
  );
}

function TryOnInner() {
  const router = useRouter();
  const search = useSearchParams();
  const seededProductId = search.get("seed") ?? undefined;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoIsFromCache, setPhotoIsFromCache] = useState(false);

  // Mode-fork: once a photo is uploaded, the customer chooses between
  // "Try-On" (existing flow) and "Design Me" (custom-design flow).
  // Seeded product links pin the mode to try-on.
  const [mode, setMode] = useState<"tryon" | "design">("tryon");

  const [fit, setFit] = useState<TryOnFormInput["fit_preference"]>("regular");
  const [occasion, setOccasion] = useState("");
  const [prompt, setPrompt] = useState("");
  const [height, setHeight] = useState("");
  const [age, setAge] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Restore cached photo on mount so a returning visitor sees the saved
  // shot ready to go.
  useEffect(() => {
    let cancelled = false;
    void loadPhoto().then((cached) => {
      if (cancelled || !cached) return;
      setPhoto(cached);
      setPhotoIsFromCache(true);
      setAge(true); // they confirmed previously
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const accept = useCallback(async (file: File | null) => {
    if (!file) return;
    if (!ALLOWED_MIME.has(file.type.toLowerCase())) {
      setError(`Unsupported file type: ${file.type}.`);
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("File is over 20 MB — pick a smaller one.");
      return;
    }
    setError(null);
    // iPhone HEIC photos won't render in Chrome / Firefox previews.
    // Convert here once, store the JPEG, and let every downstream
    // surface (cache, mini-thumb, hero preview) treat it normally.
    const usable = await maybeConvertHeic(file);
    setPhoto(usable);
    setPhotoIsFromCache(false);
  }, []);

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    accept(e.target.files?.[0] ?? null);
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

  async function onClearCached() {
    await clearPhoto();
    setPhoto(null);
    setPhotoIsFromCache(false);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!photo) return setError("Pick a full-body photo first.");
    if (!age) return setError("Confirm you're 18 or older to continue.");
    setSubmitting(true);
    setError(null);
    try {
      const anonId = ensureAnonId();
      // Cache the photo for next time before submit — so even if the API
      // call fails, the user doesn't lose their upload on retry.
      await savePhoto(photo);

      const session = await api.createTryOnSession(photo, {
        age_confirmed: true,
        height: height || undefined,
        fit_preference: fit,
        occasion: occasion || undefined,
        prompt: prompt || undefined,
        seeded_product_id: seededProductId,
        anonymous_session_id: anonId,
      });
      router.push(
        `/try-on/jobs/${session.job_id}?session=${session.try_on_session_id}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start try-on.");
      setSubmitting(false);
    }
  }

  async function onContinueToDesign() {
    if (!photo) return setError("Pick a full-body photo first.");
    if (!age) return setError("Confirm you're 18 or older to continue.");
    // Persist the photo so the design page picks it up — same cache the
    // try-on path uses, so navigating between modes stays seamless.
    await savePhoto(photo);
    router.push("/try-on/design");
  }

  return (
    <section className="ai-canvas">
      <div className="max-w-[1100px] mx-auto px-5 py-10 sm:py-14">
        <div className="mb-6 text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-2">
            {seededProductId ? "Step 1 · Upload your photo" : "Step 1 of 2"}
          </div>
          <h1 className="font-display text-4xl sm:text-5xl leading-[1.02]">
            Upload one photo.<br />We&apos;ll do the rest.
          </h1>
          {seededProductId ? (
            <p className="text-[color:var(--muted)] mt-3 text-sm">
              We&apos;ll style this piece on you alongside complementary outfits.
            </p>
          ) : null}
        </div>

        <form
          className="grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-6 items-start"
          onSubmit={onSubmit}
        >
          <div
            className="glass-strong p-5"
            onDragLeave={onDragLeave}
            onDragOver={onDragOver}
            onDrop={onDrop}
          >
            {photo ? (
              <PhotoPreview
                badge={
                  photoIsFromCache ? (
                    <span className="pill pill-ai">Saved photo</span>
                  ) : null
                }
                file={photo}
              />
            ) : (
              <button
                className="w-full rounded-xl border-2 border-dashed py-16 text-center bg-white/30 hover:bg-white/40 transition"
                onClick={() => inputRef.current?.click()}
                style={{
                  borderColor: dragging ? "var(--ink)" : "rgba(255,255,255,0.7)",
                  background: dragging ? "rgba(255,255,255,0.55)" : undefined,
                }}
                type="button"
              >
                <div className="mx-auto mb-3 w-12 h-12 rounded-full bg-black/10 flex items-center justify-center">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                    <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
                  </svg>
                </div>
                <div className="text-sm font-medium">
                  {dragging ? "Drop the photo to upload" : "Drag a full-body photo here"}
                </div>
                <div className="text-xs text-[color:var(--muted)] mt-1">
                  or <span className="underline">choose from your device</span> ·
                  JPEG / PNG / WebP / HEIC, max 20 MB
                </div>
              </button>
            )}
            <input
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              aria-label="Upload a full-body photo"
              className="hidden"
              onChange={onFile}
              ref={inputRef}
              type="file"
            />
            <div className="flex items-center justify-between mt-4 gap-3">
              <div className="flex items-center gap-2">
                <button
                  className="btn-secondary"
                  onClick={() => inputRef.current?.click()}
                  type="button"
                >
                  {photo ? "Replace photo" : "Choose photo"}
                </button>
                {photoIsFromCache ? (
                  <button
                    className="btn-ghost text-xs underline underline-offset-2"
                    onClick={onClearCached}
                    type="button"
                  >
                    Remove saved photo
                  </button>
                ) : null}
              </div>
              {photo ? (
                <span className="text-[11px] text-[color:var(--muted)] truncate max-w-[60%]">
                  {photo.name} · {(photo.size / 1024 / 1024).toFixed(2)} MB
                </span>
              ) : null}
            </div>
          </div>

          <div className="card-solid p-5 space-y-4">
            {/* Mode toggle — only useful once a photo's in hand. Hidden
                when the page is seeded with a specific product to try on. */}
            {photo && !seededProductId ? (
              <div
                className="grid grid-cols-2 gap-1 p-1 rounded-lg"
                role="tablist"
                style={{ background: "var(--ivory)" }}
              >
                <button
                  aria-selected={mode === "tryon"}
                  className="text-xs font-medium py-2 rounded-md transition"
                  onClick={() => setMode("tryon")}
                  role="tab"
                  style={
                    mode === "tryon"
                      ? {
                          background: "var(--paper)",
                          color: "var(--ink)",
                          boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                        }
                      : { color: "var(--muted)" }
                  }
                  type="button"
                >
                  Try on our pieces
                </button>
                <button
                  aria-selected={mode === "design"}
                  className="text-xs font-medium py-2 rounded-md transition"
                  onClick={() => setMode("design")}
                  role="tab"
                  style={
                    mode === "design"
                      ? {
                          background: "var(--paper)",
                          color: "var(--ink)",
                          boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                        }
                      : { color: "var(--muted)" }
                  }
                  type="button"
                >
                  Design something custom
                </button>
              </div>
            ) : null}

            {mode === "tryon" ? (
              <>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Fit preference
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    {FIT_OPTIONS.map((value) => (
                      <button
                        className="btn-secondary text-xs capitalize"
                        key={value}
                        onClick={() => setFit(value)}
                        style={
                          value === fit
                            ? { background: "var(--ink)", color: "var(--paper)", borderColor: "var(--ink)" }
                            : undefined
                        }
                        type="button"
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Height (optional)
                  </div>
                  <input
                    aria-label="Height (optional)"
                    className="input"
                    onChange={(e) => setHeight(e.target.value)}
                    placeholder='5&apos; 9" / 175 cm'
                    value={height}
                  />
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Occasion (optional)
                  </div>
                  <input
                    aria-label="Occasion (optional)"
                    className="input"
                    onChange={(e) => setOccasion(e.target.value)}
                    placeholder="Dinner · weekend · work"
                    value={occasion}
                  />
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Style notes (optional)
                  </div>
                  <input
                    aria-label="Style notes (optional)"
                    className="input"
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Linen-forward, neutral palette"
                    value={prompt}
                  />
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Design Me
                  </div>
                  <p className="text-sm leading-snug">
                    Pick a fabric, describe the piece you want made, and we&apos;ll
                    render you wearing it before a tailor brings it to life.
                  </p>
                </div>
                <ul className="text-[12px] text-[color:var(--muted)] space-y-1.5">
                  <li>· Choose from six curated fabrics</li>
                  <li>· Describe the piece in your own words</li>
                  <li>· See the design on you in seconds</li>
                  <li>· Estimated price upfront, made-to-order after checkout</li>
                </ul>
              </div>
            )}

            <label className="flex items-start gap-2 pt-1">
              <input
                checked={age}
                className="mt-1"
                onChange={(e) => setAge(e.target.checked)}
                type="checkbox"
              />
              <span className="text-[11px] text-[color:var(--muted)] leading-snug">
                I&apos;m 18 or older and consent to AI image generation on my photo for this session.
              </span>
            </label>

            {error ? (
              <p className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
                {error}
              </p>
            ) : null}

            {mode === "tryon" ? (
              <button
                className="btn-primary w-full"
                disabled={!photo || !age || submitting}
                type="submit"
              >
                {submitting ? "Starting…" : "Generate 10 looks"}
              </button>
            ) : (
              <button
                className="btn-primary w-full"
                disabled={!photo || !age}
                onClick={onContinueToDesign}
                type="button"
              >
                Continue to Design Me
              </button>
            )}
            <p className="text-[11px] text-center text-[color:var(--muted)]">
              Your photo is cached on this device so you can try more pieces without re-uploading.
            </p>
          </div>
        </form>
      </div>
    </section>
  );
}
