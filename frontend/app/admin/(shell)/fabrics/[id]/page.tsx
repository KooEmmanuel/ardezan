"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { adminBrowser } from "@/lib/admin-browser";
import type { AdminFabric } from "@/lib/admin-types";
import { API_BASE_URL } from "@/lib/api";

const PIECE_OPTIONS = [
  "shirt", "blouse", "trouser", "skirt", "dress",
  "jacket", "blazer", "coat", "overshirt", "tee",
  "caftan", "agbada", "dashiki", "kaba",
];

export default function EditFabricPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const { id } = use(params);

  const [fabric, setFabric] = useState<AdminFabric | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Editable state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [colorFamily, setColorFamily] = useState("");
  const [costDollars, setCostDollars] = useState("");
  const [weight, setWeight] = useState<"light" | "medium" | "heavy">("medium");
  const [finish, setFinish] = useState("");
  const [gradient, setGradient] = useState("");
  const [pieces, setPieces] = useState<Set<string>>(new Set());
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Swatch upload
  const [swatchFile, setSwatchFile] = useState<File | null>(null);
  const [swatchUploading, setSwatchUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void adminBrowser.getFabric(id).then((r) => {
      if (cancelled) return;
      if (r.kind !== "ok") {
        setLoadError(r.kind === "error" ? r.message : "Unauthorized");
        return;
      }
      const f = r.data;
      setFabric(f);
      setName(f.name);
      setDescription(f.description);
      setColorFamily(f.color_family);
      setCostDollars((f.cost_per_yard_amount / 100).toFixed(2));
      setWeight(f.weight);
      setFinish(f.finish ?? "");
      setGradient(f.swatch.gradient ?? "");
      setPieces(new Set(f.suitable_for));
      setActive(f.active);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  function togglePiece(p: string) {
    const next = new Set(pieces);
    if (next.has(p)) next.delete(p);
    else next.add(p);
    setPieces(next);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const cents = Math.round(parseFloat(costDollars) * 100);
      if (Number.isNaN(cents) || cents < 0) throw new Error("Invalid cost.");
      const r = await adminBrowser.patchFabric(id, {
        name,
        description,
        color_family: colorFamily,
        cost_per_yard_amount: cents,
        suitable_for: [...pieces],
        weight,
        finish: finish || null,
        gradient: gradient || null,
        active,
      });
      if (r.kind === "ok") {
        toast({ title: "Saved", kind: "success" });
        setFabric(r.data);
      } else {
        throw new Error(r.kind === "error" ? r.message : "Unauthorized");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function onSwatchUpload() {
    if (!swatchFile) return;
    setSwatchUploading(true);
    try {
      const body = new FormData();
      body.set("swatch_image", swatchFile, swatchFile.name);
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/fabrics/${encodeURIComponent(id)}/swatch-image`,
        { method: "POST", body, credentials: "include" },
      );
      if (!r.ok) throw new Error(`Upload failed (${r.status})`);
      const updated = (await r.json()) as AdminFabric;
      setFabric(updated);
      setSwatchFile(null);
      toast({ title: "Swatch photo uploaded", kind: "success" });
    } catch (err) {
      toast({
        title: "Couldn't upload swatch",
        description: err instanceof Error ? err.message : undefined,
        kind: "error",
      });
    } finally {
      setSwatchUploading(false);
    }
  }

  async function onDelete() {
    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;
    const r = await adminBrowser.deleteFabric(id);
    if (r.kind === "ok") {
      toast({ title: "Fabric deleted", kind: "success" });
      router.push("/admin/fabrics");
    } else {
      toast({
        title: "Couldn't delete",
        description: r.kind === "error" ? r.message : undefined,
        kind: "error",
      });
    }
  }

  if (loadError) {
    return (
      <div className="card-solid p-6 text-sm">Couldn&apos;t load fabric: {loadError}</div>
    );
  }
  if (!fabric) {
    return <div className="text-sm text-[color:var(--muted)]">Loading…</div>;
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)] mb-4">
        <Link className="underline underline-offset-2" href="/admin/fabrics">Fabrics</Link>
        <span aria-hidden>›</span>
        <span className="font-mono">{fabric.fabric_id}</span>
      </nav>

      <div className="flex items-end justify-between mb-5 gap-4">
        <h1 className="font-display text-3xl">{fabric.name}</h1>
        <button className="btn-ghost text-sm underline underline-offset-2" onClick={onDelete} style={{ color: "#8d1717" }} type="button">
          Delete
        </button>
      </div>

      {/* Swatch image manager */}
      <div className="card-solid p-5 mb-5 flex items-center gap-4">
        <div
          className="w-24 h-24 rounded-md overflow-hidden border border-[color:var(--line)] relative shrink-0"
          style={{ background: fabric.swatch.gradient ?? "var(--ivory)" }}
        >
          {fabric.swatch.image_url ? (
            <Image alt={fabric.name} className="object-cover" fill sizes="96px" src={fabric.swatch.image_url} />
          ) : null}
        </div>
        <div className="flex-1">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Swatch photo</div>
          <div className="text-[12px] text-[color:var(--muted)] mb-2">
            Upload a real fabric photo. The CSS gradient stays as a fallback.
          </div>
          <div className="flex items-center gap-3">
            <input
              accept="image/jpeg,image/png,image/webp"
              className="block text-[11px] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-[color:var(--ivory)] file:text-[color:var(--ink)] file:cursor-pointer cursor-pointer"
              onChange={(e) => setSwatchFile(e.target.files?.[0] ?? null)}
              type="file"
            />
            <button
              className="btn-secondary text-sm"
              disabled={!swatchFile || swatchUploading}
              onClick={onSwatchUpload}
              type="button"
            >
              {swatchUploading ? "Uploading…" : "Replace swatch"}
            </button>
          </div>
        </div>
      </div>

      <form className="card-solid p-6 space-y-5 max-w-[760px]" onSubmit={onSave}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Name</div>
            <input className="input" onChange={(e) => setName(e.target.value)} value={name} />
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Color family</div>
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
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Description</div>
          <textarea className="input" onChange={(e) => setDescription(e.target.value)} rows={3} value={description} />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Cost per yard (USD)</div>
            <input className="input" inputMode="decimal" onChange={(e) => setCostDollars(e.target.value)} value={costDollars} />
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
            <input className="input" onChange={(e) => setFinish(e.target.value)} value={finish} />
          </label>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">Suitable for</div>
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

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">CSS gradient (fallback)</div>
          <input className="input" onChange={(e) => setGradient(e.target.value)} value={gradient} />
          {gradient ? <div className="mt-2 h-10 rounded-md border border-[color:var(--line)]" style={{ background: gradient }} /> : null}
        </label>

        <label className="flex items-center gap-2 text-sm">
          <input checked={active} onChange={(e) => setActive(e.target.checked)} type="checkbox" />
          Active (shows up on Design Me)
        </label>

        {error ? <div className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>{error}</div> : null}

        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={saving} type="submit">
            {saving ? "Saving…" : "Save changes"}
          </button>
          <Link className="btn-ghost text-sm underline underline-offset-2" href="/admin/fabrics">
            Back
          </Link>
        </div>
      </form>
    </>
  );
}
