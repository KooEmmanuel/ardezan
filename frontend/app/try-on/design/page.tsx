"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { ensureAnonId } from "@/lib/anon";
import { api, formatMoney } from "@/lib/api";
import { addCustomDesignToCart } from "@/lib/cart";
import {
  DESIGN_INSPIRATIONS,
  INSPIRATION_IMAGES,
  findInspiration,
  type DesignInspiration,
} from "@/lib/design-inspirations";
import { loadPhoto } from "@/lib/photo-cache";
import type {
  Complexity,
  CostBreakdown,
  DesignSessionCreateResponse,
  FabricPublic,
  PieceType,
} from "@/lib/types";

const PIECE_LABELS: { value: PieceType; label: string }[] = [
  { value: "shirt", label: "Shirt" },
  { value: "blouse", label: "Blouse" },
  { value: "tee", label: "Tee" },
  { value: "trouser", label: "Trouser" },
  { value: "skirt", label: "Skirt" },
  { value: "dress", label: "Dress" },
  { value: "jacket", label: "Jacket" },
  { value: "blazer", label: "Blazer" },
  { value: "overshirt", label: "Overshirt" },
  { value: "coat", label: "Coat" },
];

const COMPLEXITY_OPTIONS: {
  value: Complexity;
  label: string;
  description: string;
}[] = [
  { value: "simple", label: "Simple", description: "Straight cut, minimal details." },
  { value: "standard", label: "Standard", description: "Lined, regular finishing." },
  { value: "intricate", label: "Intricate", description: "Pleats, hand-finishing, embellishments." },
];


export default function DesignMePage() {
  return (
    <Suspense fallback={null}>
      <DesignMeInner />
    </Suspense>
  );
}

function DesignMeInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { toast } = useToast();

  // Deep-link prefill — ``?inspiration=<id>`` lets the catalog Bespoke
  // tiles, or any external link, route here with the form ready to go.
  const inspirationFromUrl = useMemo(
    () => findInspiration(search.get("inspiration")),
    [search],
  );

  const [photo, setPhoto] = useState<File | null>(null);
  const [photoLoading, setPhotoLoading] = useState(true);
  const [fabrics, setFabrics] = useState<FabricPublic[]>([]);
  const [selectedFabric, setSelectedFabric] = useState<FabricPublic | null>(null);
  const [pieceType, setPieceType] = useState<PieceType | null>(null);
  const [complexity, setComplexity] = useState<Complexity>("standard");
  const [brief, setBrief] = useState("");
  const [fitNote, setFitNote] = useState("");

  const [estimate, setEstimate] = useState<CostBreakdown | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DesignSessionCreateResponse | null>(null);

  // Pull the cached photo from /try-on. If none exists, the customer
  // skipped the upload step — send them back. HEIC upgrade (Chrome /
  // Firefox can't decode it natively) runs in the background after the
  // page has rendered so we don't block on a slow WASM load.
  useEffect(() => {
    let cancelled = false;
    void loadPhoto().then(async (cached) => {
      if (cancelled) return;
      if (!cached) {
        router.replace("/try-on");
        return;
      }
      setPhoto(cached);
      setPhotoLoading(false);

      const ext = cached.name.toLowerCase();
      const isHeic =
        cached.type.toLowerCase() === "image/heic" ||
        cached.type.toLowerCase() === "image/heif" ||
        (!cached.type && /\.(heic|heif)$/.test(ext));
      if (!isHeic) return;

      try {
        const { maybeConvertHeic } = await import("@/lib/heic-to-jpeg");
        const { savePhoto } = await import("@/lib/photo-cache");
        const jpeg = await maybeConvertHeic(cached);
        if (cancelled || jpeg === cached) return;
        setPhoto(jpeg);
        // Persist so the next page-load skips the conversion entirely.
        await savePhoto(jpeg);
      } catch {
        // Backend can still read HEIC — only the preview was unavailable.
      }
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    void api
      .listFabrics()
      .then((r) => {
        if (cancelled) return;
        setFabrics(r.items);
      })
      .catch((err) =>
        toast({
          title: "Couldn't load fabrics.",
          description: err instanceof Error ? err.message : undefined,
          kind: "error",
        }),
      );
    return () => {
      cancelled = true;
    };
  }, [toast]);

  // If the customer arrived via a Bespoke catalog tile (which deep-links
  // ``?inspiration=<id>``), pre-fill the form once fabrics are loaded.
  // We only do this once so manual edits afterward aren't overwritten.
  const [didPrefillFromUrl, setDidPrefillFromUrl] = useState(false);
  useEffect(() => {
    if (didPrefillFromUrl) return;
    if (!inspirationFromUrl || fabrics.length === 0) return;
    const fab = fabrics.find((f) => f.fabric_id === inspirationFromUrl.fabric_id);
    if (!fab) return;
    setSelectedFabric(fab);
    setPieceType(inspirationFromUrl.piece_type);
    setComplexity(inspirationFromUrl.complexity);
    setBrief(inspirationFromUrl.brief);
    setFitNote(inspirationFromUrl.fit_note ?? "");
    setDidPrefillFromUrl(true);
  }, [didPrefillFromUrl, fabrics, inspirationFromUrl]);

  // Pieces the chosen fabric is actually suitable for. The piece selector
  // grays out the others so the customer can't pick a doomed combo.
  const allowedPieces = useMemo(
    () => new Set<PieceType>(selectedFabric?.suitable_for ?? []),
    [selectedFabric],
  );

  // When the fabric changes, clear any incompatible piece.
  useEffect(() => {
    if (pieceType && selectedFabric && !allowedPieces.has(pieceType)) {
      setPieceType(null);
      setEstimate(null);
    }
  }, [allowedPieces, pieceType, selectedFabric]);

  // Live estimate as fabric × piece × complexity changes.
  useEffect(() => {
    if (!selectedFabric || !pieceType) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    setEstimateLoading(true);
    void api
      .estimateFabric(selectedFabric.fabric_id, pieceType, complexity)
      .then((b) => {
        if (!cancelled) setEstimate(b);
      })
      .catch(() => {
        if (!cancelled) setEstimate(null);
      })
      .finally(() => {
        if (!cancelled) setEstimateLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFabric, pieceType, complexity]);

  const canSubmit =
    !!photo &&
    !!selectedFabric &&
    !!pieceType &&
    brief.trim().length >= 8 &&
    !submitting;

  const onSubmit = useCallback(async () => {
    if (!photo || !selectedFabric || !pieceType) return;
    setSubmitting(true);
    setError(null);
    try {
      const anonId = ensureAnonId();
      const r = await api.createDesignSession(photo, {
        fabric_id: selectedFabric.fabric_id,
        piece_type: pieceType,
        complexity,
        brief: brief.trim(),
        fit_note: fitNote.trim() || undefined,
        age_confirmed: true,
        anonymous_session_id: anonId,
      });
      setResult(r);
      if (r.status === "failed") {
        setError(
          r.failure_reason ??
            "Couldn't render your design. Try a clearer photo or a shorter brief.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start design.");
    } finally {
      setSubmitting(false);
    }
  }, [photo, selectedFabric, pieceType, complexity, brief, fitNote]);

  // Pre-fill the form from a curated starting point. The fabric must
  // already be loaded so we can resolve the inspiration's fabric_id;
  // if it isn't, we silently no-op — the gallery only renders once
  // fabrics are in hand anyway.
  const applyInspiration = useCallback(
    (ins: DesignInspiration) => {
      const fab = fabrics.find((f) => f.fabric_id === ins.fabric_id);
      if (!fab) return;
      setSelectedFabric(fab);
      setPieceType(ins.piece_type);
      setComplexity(ins.complexity);
      setBrief(ins.brief);
      setFitNote(ins.fit_note ?? "");
      setError(null);
      // Scroll the form back into view so the customer can see what was
      // filled in. Use a short timeout so layout has settled first.
      setTimeout(() => {
        document
          .getElementById("design-form-anchor")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    },
    [fabrics],
  );

  const onAddToCart = useCallback(() => {
    if (!result || result.status !== "ready") return;
    addCustomDesignToCart({
      design_session_id: result.design_session_id,
      expected_unit_price_amount: result.estimate.total_amount,
    });
    toast({
      title: "Added to bag",
      description:
        "We'll email you for measurements after checkout — usually within a day.",
      kind: "success",
    });
    router.push("/cart");
  }, [result, router, toast]);

  if (photoLoading) {
    return (
      <section className="max-w-[1100px] mx-auto px-5 py-16 text-center">
        <p className="text-[color:var(--muted)]">Loading your photo…</p>
      </section>
    );
  }

  return (
    <section className="ai-canvas">
      <div className="max-w-[1180px] mx-auto px-5 py-10 sm:py-14">
        <div className="mb-6 text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-2">
            Design Me
          </div>
          <h1 className="font-display text-4xl sm:text-5xl leading-[1.02]">
            Pick a fabric.<br />Tell us what you want.
          </h1>
          <p className="text-[color:var(--muted)] mt-3 text-sm">
            We&apos;ll render you in the piece and a tailor will bring it
            to life. You only pay when you check out.
          </p>
        </div>

        <div
          className="grid grid-cols-1 lg:grid-cols-[0.95fr_1.05fr] gap-6 items-start"
          id="design-form-anchor"
        >
          {/* Left column.
              - When the AI has rendered a result: show the big render.
              - Otherwise: small "your photo" thumbnail at the top, then
                the inspiration grid filling the rest. The garments are
                the focal point — your photo is a tiny confirmation. */}
          <div className="glass-strong p-5">
            {result?.status === "ready" && result.image_url ? (
              <div className="space-y-3">
                <div className="pill pill-ai inline-block">Your design</div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt="AI-rendered custom design"
                  className="w-full rounded-xl"
                  src={result.image_url}
                />
              </div>
            ) : (
              <>
                {photo ? (
                  <div className="flex items-center gap-3 mb-4 pb-4 border-b border-white/40">
                    <div className="w-14 h-16 rounded-md overflow-hidden bg-black/10 shrink-0">
                      {/* Mini photo preview using object URL — the
                          PhotoPreview component is sized for a hero
                          slot, which is way too big here. */}
                      <MiniPhotoThumb file={photo} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] uppercase tracking-[0.14em] text-[color:var(--ink-soft)]">
                        Your photo
                      </div>
                      <div className="text-[12px] text-[color:var(--muted)] truncate">
                        We&apos;ll render the piece you design on you.
                      </div>
                    </div>
                    <Link
                      className="text-[11px] underline underline-offset-2 text-[color:var(--ink-soft)] shrink-0"
                      href="/try-on"
                    >
                      Change
                    </Link>
                  </div>
                ) : null}

                <div className="mb-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                    Need a starting point
                  </div>
                  <h2 className="font-display text-2xl leading-tight">
                    Inspiration
                  </h2>
                  <p className="text-[11px] text-[color:var(--muted)] mt-1 leading-snug">
                    Each tile is a tested fabric × piece pairing. Tap one
                    to pre-fill the form — you can edit anything before
                    rendering.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {DESIGN_INSPIRATIONS.map((ins) => {
                    const fab = fabrics.find(
                      (f) => f.fabric_id === ins.fabric_id,
                    );
                    if (!fab) return null;
                    const heroUrl = INSPIRATION_IMAGES[ins.id];
                    return (
                      <button
                        className="text-left rounded-xl overflow-hidden border bg-[color:var(--paper)] hover:shadow-md transition group"
                        key={ins.id}
                        onClick={() => applyInspiration(ins)}
                        style={{ borderColor: "var(--line)" }}
                        type="button"
                      >
                        <div
                          className="aspect-[4/5] w-full relative overflow-hidden"
                          style={{
                            background: fab.swatch.gradient ?? "var(--ivory)",
                          }}
                        >
                          {heroUrl ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              alt={ins.title}
                              className="absolute inset-0 w-full h-full object-cover"
                              src={heroUrl}
                            />
                          ) : null}
                          <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/10 to-transparent" />
                          <div className="absolute bottom-2 left-2.5 right-2.5 text-white">
                            <div className="text-[9.5px] uppercase tracking-[0.14em] opacity-80">
                              {fab.name}
                            </div>
                            <div className="font-display text-[13.5px] leading-tight">
                              {ins.title}
                            </div>
                          </div>
                        </div>
                        <div className="px-2.5 py-2">
                          <div className="text-[10.5px] text-[color:var(--muted)] uppercase tracking-[0.06em] group-hover:text-[color:var(--ink)]">
                            Use this →
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {/* Right: form */}
          <div className="card-solid p-5 space-y-5">
            {!result ? (
              <>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Fabric
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {fabrics.map((f) => {
                      const isActive = selectedFabric?.fabric_id === f.fabric_id;
                      return (
                        <button
                          aria-pressed={isActive}
                          className="text-left rounded-lg border p-2 transition"
                          key={f.fabric_id}
                          onClick={() => setSelectedFabric(f)}
                          style={{
                            borderColor: isActive ? "var(--ink)" : "var(--line)",
                            background: isActive ? "var(--ivory)" : "var(--paper)",
                          }}
                          type="button"
                        >
                          <div
                            className="w-full aspect-[3/2] rounded mb-2"
                            style={{
                              background:
                                f.swatch.gradient ?? "var(--ivory)",
                            }}
                          />
                          <div className="text-[12px] font-medium leading-tight">
                            {f.name}
                          </div>
                          <div className="text-[10.5px] text-[color:var(--muted)]">
                            ${(f.cost_per_yard_amount / 100).toFixed(0)}/yd
                          </div>
                        </button>
                      );
                    })}
                  </div>
                  {selectedFabric ? (
                    <p className="text-[11px] text-[color:var(--muted)] mt-2">
                      {selectedFabric.description}
                    </p>
                  ) : null}
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Piece
                  </div>
                  <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                    {PIECE_LABELS.map((p) => {
                      const enabled =
                        !selectedFabric || allowedPieces.has(p.value);
                      const isActive = pieceType === p.value;
                      return (
                        <button
                          className="text-xs py-2 rounded-md border transition"
                          disabled={!enabled}
                          key={p.value}
                          onClick={() => setPieceType(p.value)}
                          style={{
                            borderColor: isActive ? "var(--ink)" : "var(--line)",
                            background: isActive
                              ? "var(--ink)"
                              : enabled
                                ? "var(--paper)"
                                : "transparent",
                            color: isActive
                              ? "var(--paper)"
                              : enabled
                                ? "var(--ink)"
                                : "var(--muted)",
                            opacity: enabled ? 1 : 0.5,
                          }}
                          type="button"
                        >
                          {p.label}
                        </button>
                      );
                    })}
                  </div>
                  {selectedFabric ? (
                    <p className="text-[11px] text-[color:var(--muted)] mt-2">
                      {selectedFabric.name} works best for{" "}
                      {selectedFabric.suitable_for.join(", ")}.
                    </p>
                  ) : null}
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Complexity
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {COMPLEXITY_OPTIONS.map((c) => {
                      const isActive = c.value === complexity;
                      return (
                        <button
                          className="text-xs rounded-md border p-2 text-left transition"
                          key={c.value}
                          onClick={() => setComplexity(c.value)}
                          style={{
                            borderColor: isActive ? "var(--ink)" : "var(--line)",
                            background: isActive ? "var(--ivory)" : "var(--paper)",
                          }}
                          type="button"
                        >
                          <div className="font-medium">{c.label}</div>
                          <div className="text-[10.5px] text-[color:var(--muted)] leading-tight">
                            {c.description}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Describe the piece
                  </div>
                  <textarea
                    aria-label="Design brief"
                    className="input"
                    onChange={(e) => setBrief(e.target.value)}
                    placeholder="Single-breasted blazer, notched lapels, two-button closure, side vents."
                    rows={3}
                    value={brief}
                  />
                  <div className="text-[10.5px] text-[color:var(--muted)] mt-1">
                    {brief.trim().length < 8
                      ? "At least 8 characters."
                      : `${brief.trim().length} / 600`}
                  </div>
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Fit note (optional)
                  </div>
                  <input
                    aria-label="Fit note"
                    className="input"
                    onChange={(e) => setFitNote(e.target.value)}
                    placeholder="Tailored at the waist, slightly tapered."
                    value={fitNote}
                  />
                </div>

                <div
                  className="rounded-lg border p-3"
                  style={{
                    borderColor: "var(--line)",
                    background: "var(--ivory)",
                  }}
                >
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Estimated price
                  </div>
                  {estimate ? (
                    <>
                      <div className="flex justify-between text-sm">
                        <span className="text-[color:var(--muted)]">
                          Fabric ({estimate.yardage} yd)
                        </span>
                        <span>
                          {formatMoney(estimate.material_amount, estimate.currency)}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[color:var(--muted)]">Tailoring</span>
                        <span>
                          {formatMoney(estimate.tailoring_amount, estimate.currency)}
                        </span>
                      </div>
                      <div className="flex justify-between text-base font-medium pt-1.5 mt-1.5 border-t border-[color:var(--line)]">
                        <span>Total</span>
                        <span>
                          {formatMoney(estimate.total_amount, estimate.currency)}
                        </span>
                      </div>
                      <p className="text-[10.5px] text-[color:var(--muted)] mt-2 leading-snug">
                        {estimate.estimate_note}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-[color:var(--muted)]">
                      {estimateLoading
                        ? "Updating…"
                        : "Pick a fabric and piece to see the estimate."}
                    </p>
                  )}
                </div>

                {error ? (
                  <p className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
                    {error}
                  </p>
                ) : null}

                <button
                  className="btn-primary w-full"
                  disabled={!canSubmit}
                  onClick={onSubmit}
                  type="button"
                >
                  {submitting ? "Rendering your design…" : "Render my design"}
                </button>
                <p className="text-[11px] text-center text-[color:var(--muted)]">
                  This takes about 10-15 seconds.
                </p>
              </>
            ) : (
              <>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                    Your design
                  </div>
                  <h2 className="font-display text-2xl leading-tight">
                    Custom {pieceType} in {selectedFabric?.name}
                  </h2>
                  <p className="text-sm text-[color:var(--muted)] mt-1 leading-snug">
                    {brief}
                  </p>
                </div>

                <div
                  className="rounded-lg border p-3"
                  style={{ borderColor: "var(--line)", background: "var(--ivory)" }}
                >
                  <div className="flex justify-between text-base font-medium">
                    <span>Estimated total</span>
                    <span>
                      {formatMoney(
                        result.estimate.total_amount,
                        result.estimate.currency,
                      )}
                    </span>
                  </div>
                  <p className="text-[11px] text-[color:var(--muted)] mt-1 leading-snug">
                    {result.estimate.estimate_note}
                  </p>
                </div>

                {result.status === "failed" ? (
                  <>
                    <p className="text-sm" style={{ color: "#8d1717" }}>
                      {error ?? result.failure_reason}
                    </p>
                    <button
                      className="btn-secondary w-full"
                      onClick={() => {
                        setResult(null);
                        setError(null);
                      }}
                      type="button"
                    >
                      Try again
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="btn-primary w-full"
                      onClick={onAddToCart}
                      type="button"
                    >
                      Add to bag
                    </button>
                    <button
                      className="btn-ghost w-full underline underline-offset-4 text-sm"
                      onClick={() => {
                        setResult(null);
                        setBrief("");
                        setFitNote("");
                      }}
                      type="button"
                    >
                      Design another piece
                    </button>
                  </>
                )}
              </>
            )}

            <Link
              className="block text-center text-[11px] underline underline-offset-4 text-[color:var(--muted)]"
              href="/try-on"
            >
              ← Back to upload
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

// Tiny 56×64 preview of the customer's uploaded photo for the
// inspiration sidebar. Wraps the File in an object URL and revokes
// it on unmount so we don't leak memory between renders.
//
// iPhone HEIC photos can't be decoded by Chrome or Firefox, so we
// detect that ahead of time and also recover via ``onError`` for
// anything else that breaks. The fallback is a small camera icon
// over the dark slot — the photo's still uploaded fine; just the
// browser preview is unavailable.
const UNRENDERABLE_MIME = new Set(["image/heic", "image/heif"]);
function MiniPhotoThumb({ file }: { file: File }) {
  const [url, setUrl] = useState<string | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    setErrored(false);
    const ext = file.name.toLowerCase();
    const isHeic =
      UNRENDERABLE_MIME.has(file.type.toLowerCase()) ||
      (!file.type && /\.heic$|\.heif$/.test(ext));
    if (isHeic) {
      setErrored(true);
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [file]);

  if (errored || !url) {
    return (
      <div
        className="w-full h-full flex items-center justify-center text-white/70"
        title="Photo uploaded (preview unsupported in this browser)"
      >
        <svg
          aria-hidden
          fill="none"
          height="22"
          stroke="currentColor"
          strokeWidth="1.6"
          viewBox="0 0 24 24"
          width="22"
        >
          <rect height="14" rx="2" width="18" x="3" y="6" />
          <circle cx="12" cy="13" r="3" />
          <path d="M8 6l1.5-2h5L16 6" />
        </svg>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt="Your uploaded photo"
      className="w-full h-full object-cover"
      onError={() => setErrored(true)}
      src={url}
    />
  );
}
