"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import {
  adminApi,
  type AdminFabric,
  type AdminInspiration,
} from "@/lib/admin-api";
import { API_BASE_URL } from "@/lib/api";

const PIECE_OPTIONS = [
  "shirt", "blouse", "trouser", "skirt", "dress",
  "jacket", "blazer", "coat", "overshirt", "tee",
  "caftan", "agbada", "dashiki", "kaba",
];

export default function EditInspirationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const { id } = use(params);

  const [ins, setIns] = useState<AdminInspiration | null>(null);
  const [fabrics, setFabrics] = useState<AdminFabric[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [heroFile, setHeroFile] = useState<File | null>(null);
  const [heroUploading, setHeroUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([adminApi.getInspiration(id), adminApi.listFabrics()]).then(
      ([insR, fabR]) => {
        if (cancelled) return;
        if (insR.kind !== "ok") {
          setLoadError(insR.kind === "error" ? insR.message : "Unauthorized");
          return;
        }
        if (fabR.kind === "ok") setFabrics(fabR.data.items);
        const x = insR.data;
        setIns(x);
        setFabricId(x.fabric_id);
        setPieceType(x.piece_type);
        setComplexity(x.complexity);
        setTitle(x.title);
        setTagline(x.tagline);
        setBrief(x.brief);
        setFitNote(x.fit_note ?? "");
        setGradient(x.gradient ?? "");
        setSortOrder(String(x.sort_order));
        setActive(x.active);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const r = await adminApi.patchInspiration(id, {
        fabric_id: fabricId,
        piece_type: pieceType,
        complexity,
        title,
        tagline,
        brief,
        fit_note: fitNote || null,
        gradient: gradient || null,
        sort_order: parseInt(sortOrder, 10) || 100,
        active,
      });
      if (r.kind === "ok") {
        toast({ title: "Saved", kind: "success" });
        setIns(r.data);
      } else {
        throw new Error(r.kind === "error" ? r.message : "Unauthorized");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function onHeroUpload() {
    if (!heroFile) return;
    setHeroUploading(true);
    try {
      const body = new FormData();
      body.set("hero_image", heroFile, heroFile.name);
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/inspirations/${encodeURIComponent(id)}/hero-image`,
        { method: "POST", body, credentials: "include" },
      );
      if (!r.ok) throw new Error(`Upload failed (${r.status})`);
      const updated = (await r.json()) as AdminInspiration;
      setIns(updated);
      setHeroFile(null);
      toast({ title: "Hero image uploaded", kind: "success" });
    } catch (err) {
      toast({
        title: "Couldn't upload",
        description: err instanceof Error ? err.message : undefined,
        kind: "error",
      });
    } finally {
      setHeroUploading(false);
    }
  }

  async function onDelete() {
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;
    const r = await adminApi.deleteInspiration(id);
    if (r.kind === "ok") {
      toast({ title: "Inspiration deleted", kind: "success" });
      router.push("/admin/inspirations");
    } else {
      toast({
        title: "Couldn't delete",
        description: r.kind === "error" ? r.message : undefined,
        kind: "error",
      });
    }
  }

  if (loadError) return <div className="card-solid p-6 text-sm">Couldn&apos;t load: {loadError}</div>;
  if (!ins) return <div className="text-sm text-[color:var(--muted)]">Loading…</div>;

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)] mb-4">
        <Link className="underline underline-offset-2" href="/admin/inspirations">Inspirations</Link>
        <span aria-hidden>›</span>
        <span className="font-mono">{ins.inspiration_id}</span>
      </nav>

      <div className="flex items-end justify-between mb-5 gap-4">
        <h1 className="font-display text-3xl">{ins.title}</h1>
        <button className="btn-ghost text-sm underline underline-offset-2" onClick={onDelete} style={{ color: "#8d1717" }} type="button">
          Delete
        </button>
      </div>

      {/* Hero image */}
      <div className="card-solid p-5 mb-5 flex items-start gap-4">
        <div
          className="w-32 h-40 rounded-md overflow-hidden border border-[color:var(--line)] relative shrink-0"
          style={{ background: ins.gradient ?? "var(--ivory)" }}
        >
          {ins.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img alt={ins.title} className="absolute inset-0 w-full h-full object-cover" src={ins.image_url} />
          ) : null}
        </div>
        <div className="flex-1">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Hero image</div>
          <div className="text-[12px] text-[color:var(--muted)] mb-2">
            Shown on /catalog?cat=bespoke and /try-on/design. Uploading replaces any bundled image.
          </div>
          <div className="flex items-center gap-3">
            <input
              accept="image/jpeg,image/png,image/webp"
              className="block text-[11px] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-[color:var(--ivory)] file:text-[color:var(--ink)] file:cursor-pointer cursor-pointer"
              onChange={(e) => setHeroFile(e.target.files?.[0] ?? null)}
              type="file"
            />
            <button className="btn-secondary text-sm" disabled={!heroFile || heroUploading} onClick={onHeroUpload} type="button">
              {heroUploading ? "Uploading…" : "Replace hero"}
            </button>
          </div>
        </div>
      </div>

      <form className="card-solid p-6 space-y-5 max-w-[760px]" onSubmit={onSave}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Fabric</div>
            <select className="input" onChange={(e) => setFabricId(e.target.value)} value={fabricId}>
              {fabrics.map((f) => <option key={f.fabric_id} value={f.fabric_id}>{f.name}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Piece type</div>
            <select className="input capitalize" onChange={(e) => setPieceType(e.target.value)} value={pieceType}>
              {PIECE_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Complexity</div>
            <select className="input" onChange={(e) => setComplexity(e.target.value as typeof complexity)} value={complexity}>
              <option value="simple">Simple</option>
              <option value="standard">Standard</option>
              <option value="intricate">Intricate</option>
            </select>
          </label>
        </div>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Title</div>
          <input className="input" onChange={(e) => setTitle(e.target.value)} value={title} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Tagline</div>
          <input className="input" onChange={(e) => setTagline(e.target.value)} value={tagline} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Brief</div>
          <textarea className="input" onChange={(e) => setBrief(e.target.value)} rows={3} value={brief} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Fit note</div>
          <input className="input" onChange={(e) => setFitNote(e.target.value)} value={fitNote} />
        </label>

        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">CSS gradient fallback</div>
          <input className="input" onChange={(e) => setGradient(e.target.value)} value={gradient} />
          {gradient ? <div className="mt-2 h-10 rounded-md border border-[color:var(--line)]" style={{ background: gradient }} /> : null}
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Sort order</div>
            <input className="input" inputMode="numeric" onChange={(e) => setSortOrder(e.target.value)} value={sortOrder} />
          </label>
          <label className="flex items-center gap-2 text-sm pt-5">
            <input checked={active} onChange={(e) => setActive(e.target.checked)} type="checkbox" />
            Active (shown on storefront)
          </label>
        </div>

        {error ? <div className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>{error}</div> : null}

        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={saving} type="submit">
            {saving ? "Saving…" : "Save changes"}
          </button>
          <Link className="btn-ghost text-sm underline underline-offset-2" href="/admin/inspirations">Back</Link>
        </div>
      </form>
    </>
  );
}
