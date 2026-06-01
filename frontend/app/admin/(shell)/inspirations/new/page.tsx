"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { adminApi, type AdminFabric } from "@/lib/admin-api";
import { API_BASE_URL } from "@/lib/api";

const PIECE_OPTIONS = [
  "shirt", "blouse", "trouser", "skirt", "dress",
  "jacket", "blazer", "coat", "overshirt", "tee",
  "caftan", "agbada", "dashiki", "kaba",
];

export default function NewInspirationPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [fabrics, setFabrics] = useState<AdminFabric[]>([]);
  const [fabricId, setFabricId] = useState("");
  const [pieceType, setPieceType] = useState("shirt");
  const [complexity, setComplexity] = useState<
    "simple" | "standard" | "intricate"
  >("standard");
  const [title, setTitle] = useState("");
  const [tagline, setTagline] = useState("");
  const [brief, setBrief] = useState("");
  const [fitNote, setFitNote] = useState("");
  const [gradient, setGradient] = useState("");
  const [sortOrder, setSortOrder] = useState("100");
  const [active, setActive] = useState(true);
  const [heroFile, setHeroFile] = useState<File | null>(null);
  const [heroPreview, setHeroPreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void adminApi.listFabrics().then((r) => {
      if (r.kind === "ok") setFabrics(r.data.items);
    });
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (!fabricId) throw new Error("Pick a fabric.");
      if (brief.trim().length < 8) throw new Error("Brief is too short.");

      const body = new FormData();
      body.set("fabric_id", fabricId);
      body.set("piece_type", pieceType);
      body.set("complexity", complexity);
      body.set("title", title);
      body.set("tagline", tagline);
      body.set("brief", brief);
      if (fitNote) body.set("fit_note", fitNote);
      if (gradient) body.set("gradient", gradient);
      body.set("sort_order", sortOrder || "100");
      body.set("active", String(active));
      if (heroFile) body.set("hero_image", heroFile, heroFile.name);

      const r = await fetch(`${API_BASE_URL}/api/v1/admin/inspirations`, {
        method: "POST",
        body,
        credentials: "include",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err?.error?.message ?? `Create failed (${r.status})`);
      }
      toast({ title: "Inspiration created", kind: "success" });
      router.push("/admin/inspirations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)] mb-4">
        <Link className="underline underline-offset-2" href="/admin/inspirations">Inspirations</Link>
        <span aria-hidden>›</span>
        <span>New</span>
      </nav>

      <h1 className="font-display text-3xl mb-5">New inspiration</h1>

      <form className="card-solid p-6 space-y-5 max-w-[760px]" onSubmit={onSubmit}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Fabric *</div>
            <select className="input" onChange={(e) => setFabricId(e.target.value)} required value={fabricId}>
              <option value="">— pick a fabric —</option>
              {fabrics.map((f) => (
                <option key={f.fabric_id} value={f.fabric_id}>{f.name}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Piece type *</div>
            <select className="input capitalize" onChange={(e) => setPieceType(e.target.value)} value={pieceType}>
              {PIECE_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Complexity *</div>
            <select className="input" onChange={(e) => setComplexity(e.target.value as typeof complexity)} value={complexity}>
              <option value="simple">Simple</option>
              <option value="standard">Standard</option>
              <option value="intricate">Intricate</option>
            </select>
          </label>
        </div>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Title *</div>
          <input className="input" onChange={(e) => setTitle(e.target.value)} placeholder="Camp-collar linen shirt" required value={title} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Tagline</div>
          <input className="input" onChange={(e) => setTagline(e.target.value)} placeholder="One-line marketing description" value={tagline} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Brief *</div>
          <textarea className="input" onChange={(e) => setBrief(e.target.value)} placeholder="Describe the piece in detail — fed to Gemini and shown to the tailor." required rows={3} value={brief} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Fit note</div>
          <input className="input" onChange={(e) => setFitNote(e.target.value)} placeholder="Tailored at the waist, slight taper" value={fitNote} />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">CSS gradient fallback</div>
            <input className="input" onChange={(e) => setGradient(e.target.value)} placeholder="linear-gradient(135deg, …)" value={gradient} />
            {gradient ? <div className="mt-2 h-10 rounded-md border border-[color:var(--line)]" style={{ background: gradient }} /> : null}
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Hero image</div>
            <input
              accept="image/jpeg,image/png,image/webp"
              className="block w-full text-[11px] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-[color:var(--ivory)] file:text-[color:var(--ink)] file:cursor-pointer cursor-pointer"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (heroPreview) URL.revokeObjectURL(heroPreview);
                setHeroFile(f);
                setHeroPreview(f ? URL.createObjectURL(f) : null);
              }}
              type="file"
            />
            {heroPreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt="Hero preview" className="mt-2 w-24 h-24 object-cover rounded-md border border-[color:var(--line)]" src={heroPreview} />
            ) : null}
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Sort order (lower shows first)</div>
            <input className="input" inputMode="numeric" onChange={(e) => setSortOrder(e.target.value)} value={sortOrder} />
          </label>
          <label className="flex items-center gap-2 text-sm pt-5">
            <input checked={active} onChange={(e) => setActive(e.target.checked)} type="checkbox" />
            Show on the storefront now
          </label>
        </div>

        {error ? <div className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>{error}</div> : null}

        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={submitting} type="submit">
            {submitting ? "Saving…" : "Create inspiration"}
          </button>
          <Link className="btn-ghost text-sm underline underline-offset-2" href="/admin/inspirations">Cancel</Link>
        </div>
      </form>
    </>
  );
}
