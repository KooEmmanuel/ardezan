"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { API_BASE_URL } from "@/lib/api";

// Minimal product-create form. After save, redirect to the edit page so
// the admin can attach media, add variants, and refine the AI metadata.

const CATEGORIES = ["Outerwear", "Tops", "Trousers", "Dresses", "Skirts", "Accessories"];
const GENDERS = ["women", "men", "unisex"] as const;
const FORMALITIES = ["casual", "smart_casual", "evening", "athleisure"];
const FIT_SHAPES = ["slim", "regular", "relaxed", "boxy", "wide_leg", "tailored"];
const SEASONS = ["SS", "AW", "all_season"];

export default function AdminProductNewPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("Tops");
  const [subcategory, setSubcategory] = useState("");
  const [gender, setGender] = useState<(typeof GENDERS)[number]>("unisex");
  const [tags, setTags] = useState("");
  const [basePrice, setBasePrice] = useState(12900);
  const [compareAt, setCompareAt] = useState<number | null>(null);
  const [material, setMaterial] = useState("");
  const [fitNotes, setFitNotes] = useState("");
  const [status, setStatus] = useState<"draft" | "published">("draft");

  const [fabricType, setFabricType] = useState("cotton");
  const [formality, setFormality] = useState("smart_casual");
  const [fitShape, setFitShape] = useState("regular");
  const [season, setSeason] = useState("all_season");
  const [colorPalette, setColorPalette] = useState("");

  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      toast({ title: "Title is required.", kind: "warning" });
      return;
    }
    setBusy(true);
    try {
      const body = {
        title: title.trim(),
        description: description.trim() || null,
        category,
        subcategory: subcategory.trim() || null,
        gender,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        status,
        pricing: {
          base_price_amount: basePrice,
          compare_at_price_amount: compareAt,
          currency: "USD",
        },
        product_details: {
          material: material.trim() || null,
          fit_notes: fitNotes.trim() || null,
          return_eligible: true,
          final_sale: false,
        },
        ai: {
          eligible: true,
          fabric_type: fabricType,
          formality,
          fit_shape: fitShape,
          season,
          color_palette: colorPalette
            .split(",")
            .map((c) => c.trim().toLowerCase())
            .filter(Boolean),
        },
      };
      const r = await fetch(`${API_BASE_URL}/api/v1/admin/products`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        let msg = "Couldn't create the product.";
        try {
          const json = (await r.json()) as { error?: { message?: string } };
          msg = json.error?.message ?? msg;
        } catch {
          // ignore
        }
        throw new Error(msg);
      }
      const data = (await r.json()) as { product_id: string };
      toast({
        title: "Product created.",
        description: "Now add variants and a catalog image.",
        kind: "success",
      });
      router.push(`/admin/products/${data.product_id}`);
    } catch (err) {
      toast({
        title: "Couldn't create the product.",
        description: err instanceof Error ? err.message : undefined,
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-2 text-sm text-[color:var(--muted)]">
        <Link className="underline" href="/admin/products">Products</Link>
        <span>›</span>
        <span>New</span>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
          Catalog
        </div>
        <h1 className="font-display text-3xl">Add a product</h1>
        <p className="text-sm text-[color:var(--muted)] mt-1">
          Save the basics here. You can add variants, a catalog image, and refine
          the AI metadata on the next screen.
        </p>
      </div>

      <form className="space-y-5" onSubmit={onSubmit}>
        <div className="card-solid p-5 space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Basics
          </div>

          <Field label="Title">
            <input className="input" onChange={(e) => setTitle(e.target.value)} required value={title} />
          </Field>

          <Field label="Description">
            <textarea
              className="input min-h-[5rem]"
              onChange={(e) => setDescription(e.target.value)}
              placeholder="One short paragraph, editorial tone."
              value={description}
            />
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Field label="Category">
              <select className="input" onChange={(e) => setCategory(e.target.value)} value={category}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Subcategory">
              <input
                className="input"
                onChange={(e) => setSubcategory(e.target.value)}
                placeholder="e.g. Blazers"
                value={subcategory}
              />
            </Field>
            <Field label="Gender">
              <select
                className="input"
                onChange={(e) =>
                  setGender(e.target.value as (typeof GENDERS)[number])
                }
                value={gender}
              >
                {GENDERS.map((g) => (
                  <option key={g} value={g}>
                    {g[0].toUpperCase() + g.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="Tags (comma-separated)">
            <input
              className="input"
              onChange={(e) => setTags(e.target.value)}
              placeholder="linen, summer, tailored"
              value={tags}
            />
          </Field>
        </div>

        <div className="card-solid p-5 space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Pricing (USD cents)
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Base price">
              <input
                className="input"
                min={0}
                onChange={(e) => setBasePrice(parseInt(e.target.value || "0", 10))}
                type="number"
                value={basePrice}
              />
              <p className="text-[11px] text-[color:var(--muted)]">
                ${(basePrice / 100).toFixed(2)}
              </p>
            </Field>
            <Field label="Compare-at (optional)">
              <input
                className="input"
                min={0}
                onChange={(e) =>
                  setCompareAt(e.target.value ? parseInt(e.target.value, 10) : null)
                }
                placeholder="Leave blank for no sale price"
                type="number"
                value={compareAt ?? ""}
              />
            </Field>
          </div>
        </div>

        <div className="card-solid p-5 space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Product details
          </div>
          <Field label="Material">
            <input
              className="input"
              onChange={(e) => setMaterial(e.target.value)}
              placeholder="100% Italian linen"
              value={material}
            />
          </Field>
          <Field label="Fit notes">
            <input
              className="input"
              onChange={(e) => setFitNotes(e.target.value)}
              placeholder="Relaxed through the shoulder, tapered at the hem."
              value={fitNotes}
            />
          </Field>
        </div>

        <div className="card-solid p-5 space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            AI metadata
          </div>
          <p className="text-[11px] text-[color:var(--muted)]">
            Used by the recommender. You can fine-tune later.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Fabric type">
              <input
                className="input"
                onChange={(e) => setFabricType(e.target.value)}
                placeholder="linen, wool, cotton, silk…"
                value={fabricType}
              />
            </Field>
            <Field label="Formality">
              <select className="input" onChange={(e) => setFormality(e.target.value)} value={formality}>
                {FORMALITIES.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </Field>
            <Field label="Fit shape">
              <select className="input" onChange={(e) => setFitShape(e.target.value)} value={fitShape}>
                {FIT_SHAPES.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </Field>
            <Field label="Season">
              <select className="input" onChange={(e) => setSeason(e.target.value)} value={season}>
                {SEASONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Color palette (comma-separated)">
            <input
              className="input"
              onChange={(e) => setColorPalette(e.target.value)}
              placeholder="black, stone, olive"
              value={colorPalette}
            />
          </Field>
        </div>

        <div className="card-solid p-5 space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Status
          </div>
          <div className="flex gap-2">
            {(["draft", "published"] as const).map((s) => (
              <button
                className="btn-secondary text-xs capitalize"
                key={s}
                onClick={() => setStatus(s)}
                style={
                  status === s
                    ? { background: "var(--ink)", color: "var(--paper)", borderColor: "var(--ink)" }
                    : undefined
                }
                type="button"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <button className="btn-primary" disabled={busy} type="submit">
            {busy ? "Creating…" : "Create + open"}
          </button>
          <Link className="btn-secondary" href="/admin/products">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}
