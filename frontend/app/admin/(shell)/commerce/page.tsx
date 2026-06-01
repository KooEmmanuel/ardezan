"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { adminBrowser } from "@/lib/admin-browser";
import type { AdminCommerceConfig } from "@/lib/admin-types";

const PIECE_TYPES = [
  "shirt", "blouse", "trouser", "skirt", "dress",
  "jacket", "blazer", "coat", "overshirt", "tee",
  "caftan", "agbada", "dashiki", "kaba",
];

export default function CommerceAdminPage() {
  const { toast } = useToast();

  const [cfg, setCfg] = useState<AdminCommerceConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void adminBrowser.getCommerceConfig().then((r) => {
      if (r.kind === "ok") setCfg(r.data);
      else if (r.kind === "error") setError(r.message);
    });
  }, []);

  if (error) return <div className="card-solid p-6 text-sm">Couldn&apos;t load: {error}</div>;
  if (!cfg) return <div className="text-sm text-[color:var(--muted)]">Loading…</div>;

  async function onSave() {
    if (!cfg) return;
    setSaving(true);
    const r = await adminBrowser.patchCommerceConfig({
      yardage_by_piece: cfg.yardage_by_piece,
      base_tailoring_by_piece: cfg.base_tailoring_by_piece,
      complexity_multiplier: cfg.complexity_multiplier,
      shipping: cfg.shipping,
    });
    setSaving(false);
    if (r.kind === "ok") {
      setCfg(r.data);
      toast({ title: "Saved", kind: "success" });
    } else {
      toast({ title: "Save failed", kind: "error" });
    }
  }

  return (
    <>
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">Settings</div>
        <h1 className="font-display text-3xl">Pricing & shipping</h1>
        <p className="text-sm text-[color:var(--muted)] mt-1 max-w-xl">
          Tune the Design Me cost estimate (fabric yardage × cost-per-yard + tailoring fee × complexity)
          and the flat shipping rates checkout uses. Values fall back to sensible defaults when blank.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">
        {/* Yardage */}
        <div className="card-solid p-5">
          <h2 className="font-display text-xl mb-3">Yardage per piece</h2>
          <p className="text-[11px] text-[color:var(--muted)] mb-3">How many yards of fabric a typical piece uses.</p>
          <div className="space-y-2">
            {PIECE_TYPES.map((p) => (
              <label className="flex items-center justify-between gap-3" key={p}>
                <span className="text-[12px] capitalize">{p}</span>
                <input
                  className="input w-24 text-right tabular-nums"
                  inputMode="decimal"
                  onChange={(e) =>
                    setCfg({
                      ...cfg,
                      yardage_by_piece: {
                        ...cfg.yardage_by_piece,
                        [p]: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  value={cfg.yardage_by_piece[p] ?? ""}
                />
              </label>
            ))}
          </div>
        </div>

        {/* Tailoring */}
        <div className="card-solid p-5">
          <h2 className="font-display text-xl mb-3">Tailoring fee per piece</h2>
          <p className="text-[11px] text-[color:var(--muted)] mb-3">Base tailoring fee in USD (before complexity multiplier).</p>
          <div className="space-y-2">
            {PIECE_TYPES.map((p) => (
              <label className="flex items-center justify-between gap-3" key={p}>
                <span className="text-[12px] capitalize">{p}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[12px] text-[color:var(--muted)]">$</span>
                  <input
                    className="input w-24 text-right tabular-nums"
                    inputMode="numeric"
                    onChange={(e) => {
                      const dollars = parseFloat(e.target.value);
                      setCfg({
                        ...cfg,
                        base_tailoring_by_piece: {
                          ...cfg.base_tailoring_by_piece,
                          [p]: Math.round((isNaN(dollars) ? 0 : dollars) * 100),
                        },
                      });
                    }}
                    value={((cfg.base_tailoring_by_piece[p] ?? 0) / 100).toFixed(0)}
                  />
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Complexity + shipping */}
        <div className="space-y-5">
          <div className="card-solid p-5">
            <h2 className="font-display text-xl mb-3">Complexity multiplier</h2>
            <p className="text-[11px] text-[color:var(--muted)] mb-3">Multiplies tailoring fee. Standard = 1.0×.</p>
            <div className="space-y-2">
              {(["simple", "standard", "intricate"] as const).map((c) => (
                <label className="flex items-center justify-between gap-3" key={c}>
                  <span className="text-[12px] capitalize">{c}</span>
                  <input
                    className="input w-24 text-right tabular-nums"
                    inputMode="decimal"
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        complexity_multiplier: {
                          ...cfg.complexity_multiplier,
                          [c]: parseFloat(e.target.value) || 0,
                        },
                      })
                    }
                    value={cfg.complexity_multiplier[c] ?? ""}
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="card-solid p-5">
            <h2 className="font-display text-xl mb-3">Shipping rates</h2>
            <p className="text-[11px] text-[color:var(--muted)] mb-3">
              Flat rates by method. International triggers when the order ships outside the US.
            </p>
            {(
              [
                ["standard_cents", "Standard (US)"],
                ["express_cents", "Express (US)"],
                ["international_cents", "International"],
              ] as const
            ).map(([key, label]) => (
              <label className="flex items-center justify-between gap-3 mb-2" key={key}>
                <span className="text-[12px]">{label}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[12px] text-[color:var(--muted)]">$</span>
                  <input
                    className="input w-24 text-right tabular-nums"
                    inputMode="decimal"
                    onChange={(e) => {
                      const dollars = parseFloat(e.target.value);
                      setCfg({
                        ...cfg,
                        shipping: {
                          ...cfg.shipping,
                          [key]: Math.round((isNaN(dollars) ? 0 : dollars) * 100),
                        },
                      });
                    }}
                    value={(cfg.shipping[key] / 100).toFixed(2)}
                  />
                </div>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={saving} onClick={onSave} type="button">
          {saving ? "Saving…" : "Save changes"}
        </button>
        <Link className="btn-ghost text-sm underline underline-offset-2" href="/admin">Back</Link>
      </div>
    </>
  );
}
