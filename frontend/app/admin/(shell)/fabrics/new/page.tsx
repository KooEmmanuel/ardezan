"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { API_BASE_URL } from "@/lib/api";

const PIECE_OPTIONS = [
  "shirt", "blouse", "trouser", "skirt", "dress",
  "jacket", "blazer", "coat", "overshirt", "tee",
  "caftan", "agbada", "dashiki", "kaba",
];

export default function NewFabricPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [colorFamily, setColorFamily] = useState("warm-neutrals");
  const [costPerYardDollars, setCostPerYardDollars] = useState("");
  const [weight, setWeight] = useState<"light" | "medium" | "heavy">("medium");
  const [finish, setFinish] = useState("");
  const [gradient, setGradient] = useState("");
  const [pieces, setPieces] = useState<Set<string>>(new Set());
  const [swatchFile, setSwatchFile] = useState<File | null>(null);
  const [swatchPreview, setSwatchPreview] = useState<string | null>(null);
  const [active, setActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePiece(p: string) {
    const next = new Set(pieces);
    if (next.has(p)) next.delete(p);
    else next.add(p);
    setPieces(next);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const cents = Math.round(parseFloat(costPerYardDollars) * 100);
      if (Number.isNaN(cents) || cents < 0) {
        throw new Error("Enter a valid cost per yard.");
      }
      if (pieces.size === 0) {
        throw new Error("Pick at least one piece type this fabric works for.");
      }
      const body = new FormData();
      body.set("name", name);
      body.set("description", description);
      body.set("color_family", colorFamily);
      body.set("cost_per_yard_amount", String(cents));
      body.set("suitable_for", [...pieces].join(","));
      body.set("weight", weight);
      if (finish) body.set("finish", finish);
      if (gradient) body.set("gradient", gradient);
      body.set("active", String(active));
      if (swatchFile) body.set("swatch_image", swatchFile, swatchFile.name);

      const r = await fetch(`${API_BASE_URL}/api/v1/admin/fabrics`, {
        method: "POST",
        body,
        credentials: "include",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err?.error?.message ?? `Create failed (${r.status})`);
      }
      toast({ title: "Fabric created", kind: "success" });
      router.push("/admin/fabrics");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)] mb-4">
        <Link className="underline underline-offset-2" href="/admin/fabrics">Fabrics</Link>
        <span aria-hidden>›</span>
        <span>New</span>
      </nav>

      <h1 className="font-display text-3xl mb-5">New fabric</h1>

      <form className="card-solid p-6 space-y-5 max-w-[760px]" onSubmit={onSubmit}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Name *</div>
            <input className="input" onChange={(e) => setName(e.target.value)} required value={name} />
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Color family *</div>
            <select className="input" onChange={(e) => setColorFamily(e.target.value)} value={colorFamily}>
              <option value="warm-neutrals">Warm neutrals</option>
              <option value="cool-neutrals">Cool neutrals</option>
              <option value="rich-tones">Rich tones</option>
              <option value="denim">Denim</option>
              <option value="vibrant">Vibrant</option>
            </select>
          </label>
        </div>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Description *</div>
          <textarea className="input" onChange={(e) => setDescription(e.target.value)} required rows={3} value={description} />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Cost per yard (USD) *</div>
            <input className="input" inputMode="decimal" onChange={(e) => setCostPerYardDollars(e.target.value)} placeholder="45.00" required value={costPerYardDollars} />
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Weight</div>
            <select className="input" onChange={(e) => setWeight(e.target.value as typeof weight)} value={weight}>
              <option value="light">Light</option>
              <option value="medium">Medium</option>
              <option value="heavy">Heavy</option>
            </select>
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Finish</div>
            <input className="input" onChange={(e) => setFinish(e.target.value)} placeholder="matte, lustrous, structured…" value={finish} />
          </label>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">Suitable for *</div>
          <div className="flex flex-wrap gap-1.5">
            {PIECE_OPTIONS.map((p) => {
              const on = pieces.has(p);
              return (
                <button
                  className="px-2.5 h-7 inline-flex items-center text-[12px] rounded-md border capitalize"
                  key={p}
                  onClick={() => togglePiece(p)}
                  style={{
                    background: on ? "var(--ink)" : "var(--paper)",
                    color: on ? "var(--paper)" : "var(--ink-soft)",
                    borderColor: on ? "var(--ink)" : "var(--line)",
                  }}
                  type="button"
                >
                  {p}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">CSS gradient (fallback)</div>
            <input
              className="input"
              onChange={(e) => setGradient(e.target.value)}
              placeholder="linear-gradient(135deg, #e8b923 0%, #c83a2a 50%, #1c1c2e 100%)"
              value={gradient}
            />
            {gradient ? (
              <div className="mt-2 h-10 rounded-md border border-[color:var(--line)]" style={{ background: gradient }} />
            ) : null}
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Swatch photo</div>
            <input
              accept="image/jpeg,image/png,image/webp"
              className="block w-full text-[11px] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-[color:var(--ivory)] file:text-[color:var(--ink)] file:cursor-pointer cursor-pointer"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (swatchPreview) URL.revokeObjectURL(swatchPreview);
                setSwatchFile(f);
                setSwatchPreview(f ? URL.createObjectURL(f) : null);
              }}
              type="file"
            />
            {swatchPreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt="Swatch preview" className="mt-2 w-20 h-20 object-cover rounded-md border border-[color:var(--line)]" src={swatchPreview} />
            ) : null}
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input checked={active} onChange={(e) => setActive(e.target.checked)} type="checkbox" />
          Show on Design Me right away
        </label>

        {error ? (
          <div className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
            {error}
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={submitting} type="submit">
            {submitting ? "Saving…" : "Create fabric"}
          </button>
          <Link className="btn-ghost text-sm underline underline-offset-2" href="/admin/fabrics">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}
