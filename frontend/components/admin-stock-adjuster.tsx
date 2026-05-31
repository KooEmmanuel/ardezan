"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { LabeledField } from "@/components/form-fields";
import { Modal } from "@/components/modal";
import { useToast } from "@/components/toast";
import { API_BASE_URL } from "@/lib/api";

/**
 * Stock adjuster — opens a small modal where the operator can either set
 * an absolute stock level, apply a +/- delta, change the low-stock
 * threshold, or toggle inventory tracking for the variant.
 *
 * All paths translate to PATCH /admin/variants/{id} with the inventory
 * subdoc set. The service layer auto-records an inventory_movement when
 * stock_on_hand actually changes.
 */
export function StockAdjuster({
  variantId,
  productId: _productId,
  current,
  threshold,
  tracked,
  variantLabel,
}: {
  variantId: string;
  productId: string;
  current: number;
  threshold: number;
  tracked: boolean;
  variantLabel?: string;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"delta" | "set">("delta");
  const [valueStr, setValueStr] = useState("");
  const [thresholdStr, setThresholdStr] = useState(String(threshold));
  const [track, setTrack] = useState(tracked);
  const [busy, setBusy] = useState(false);

  function reset() {
    setValueStr("");
    setMode("delta");
    setThresholdStr(String(threshold));
    setTrack(tracked);
  }

  async function save() {
    setBusy(true);
    try {
      const inventory: Record<string, number | boolean> = {};

      if (valueStr.trim() !== "") {
        const parsed = parseInt(valueStr, 10);
        if (Number.isNaN(parsed)) {
          toast({ title: "Stock must be a number.", kind: "warning" });
          setBusy(false);
          return;
        }
        const target = mode === "set" ? parsed : current + parsed;
        if (target < 0) {
          toast({ title: "Stock can’t go below zero.", kind: "warning" });
          setBusy(false);
          return;
        }
        inventory.stock_on_hand = target;
      }

      const parsedThreshold = parseInt(thresholdStr, 10);
      if (!Number.isNaN(parsedThreshold) && parsedThreshold !== threshold) {
        inventory.low_stock_threshold = Math.max(0, parsedThreshold);
      }
      if (track !== tracked) {
        inventory.track_inventory = track;
      }

      if (Object.keys(inventory).length === 0) {
        toast({ title: "Nothing to change.", kind: "info" });
        setOpen(false);
        setBusy(false);
        return;
      }

      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/variants/${encodeURIComponent(variantId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ inventory }),
        },
      );
      if (!r.ok) {
        const text = await r.text().catch(() => `${r.status}`);
        toast({
          title: "Couldn’t adjust stock.",
          description: text.slice(0, 160),
          kind: "error",
        });
        return;
      }
      toast({ title: "Stock adjusted.", kind: "success" });
      setOpen(false);
      reset();
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        className="inline-flex items-center gap-1 h-7 px-2 rounded-md text-[11px] border border-[color:var(--line)] bg-white text-[color:var(--ink-soft)] hover:bg-[color:var(--ivory)]"
        onClick={() => setOpen(true)}
        type="button"
      >
        <svg aria-hidden fill="none" height="11" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="11">
          <path d="M11 4H4v7M4 4l7 7M13 20h7v-7M20 20l-7-7" />
        </svg>
        Adjust
      </button>

      <Modal
        description={variantLabel ? `Variant: ${variantLabel}` : undefined}
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={busy}
              onClick={() => setOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={busy}
              onClick={save}
              type="button"
            >
              {busy ? "Saving…" : "Apply"}
            </button>
          </>
        }
        onClose={() => setOpen(false)}
        open={open}
        size="sm"
        title="Adjust stock"
      >
        <div className="space-y-4">
          <div>
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
                Current stock
              </span>
              <span className="font-display text-2xl tabular-nums leading-none">
                {current}
              </span>
            </div>
            <div className="flex gap-1 p-1 bg-[color:var(--ivory)] rounded-md">
              <button
                className={
                  "flex-1 text-[12px] px-2 py-1.5 rounded transition-colors " +
                  (mode === "delta"
                    ? "bg-white text-[color:var(--ink)] shadow-sm"
                    : "text-[color:var(--muted)]")
                }
                onClick={() => setMode("delta")}
                type="button"
              >
                ± Delta
              </button>
              <button
                className={
                  "flex-1 text-[12px] px-2 py-1.5 rounded transition-colors " +
                  (mode === "set"
                    ? "bg-white text-[color:var(--ink)] shadow-sm"
                    : "text-[color:var(--muted)]")
                }
                onClick={() => setMode("set")}
                type="button"
              >
                = Set to
              </button>
            </div>
            <input
              autoFocus
              className="input h-9 text-[13px] mt-2"
              inputMode="numeric"
              onChange={(e) => setValueStr(e.target.value)}
              placeholder={mode === "delta" ? "e.g. +10 or -2" : "e.g. 50"}
              value={valueStr}
            />
          </div>

          <LabeledField label="Low-stock threshold">
            <input
              className="input h-9 text-[13px]"
              inputMode="numeric"
              onChange={(e) => setThresholdStr(e.target.value)}
              value={thresholdStr}
            />
          </LabeledField>

          <label className="flex items-center gap-2 text-[13px]">
            <input
              checked={track}
              onChange={(e) => setTrack(e.target.checked)}
              type="checkbox"
            />
            Track inventory for this variant
          </label>
        </div>
      </Modal>
    </>
  );
}
