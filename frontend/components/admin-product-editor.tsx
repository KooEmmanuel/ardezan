"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { LabeledField, SelectField } from "@/components/form-fields";
import { Modal } from "@/components/modal";
import { StockAdjuster } from "@/components/admin-stock-adjuster";
import { useToast } from "@/components/toast";
import { API_BASE_URL, formatMoney } from "@/lib/api";
import type { AdminProductDetailFull, AdminVariantDetail } from "@/lib/admin-api";

type Status = "draft" | "published" | "archived";

/**
 * Renders the right-hand column of the product detail page:
 *   - Visibility (3-way status segmented control)
 *   - Catalog image (open modal to confirm AI regenerate)
 *   - Variants table (with per-row StockAdjuster + Add variant modal)
 *
 * All feedback goes through the toast system — no inline strings.
 */
export function AdminProductEditor({
  product,
}: {
  product: AdminProductDetailFull;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [status, setStatus] = useState<Status>(product.status);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [addVariantOpen, setAddVariantOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/products/${encodeURIComponent(product.product_id)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        },
      );
      if (!r.ok) throw new Error(`${r.status}`);
      toast({ title: "Saved.", kind: "success" });
      router.refresh();
    } catch (e) {
      toast({
        title: "Save failed.",
        description: e instanceof Error ? e.message : undefined,
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function setStatusAndSave(next: Status) {
    setStatus(next);
    await patch({ status: next });
  }

  async function confirmRegenerate() {
    setRegenerating(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/products/${encodeURIComponent(product.product_id)}/media/ai-generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ set_as_primary: true }),
        },
      );
      if (!r.ok) throw new Error(`${r.status}`);
      toast({ title: "New image generated.", kind: "success" });
      setRegenerateOpen(false);
      router.refresh();
    } catch (e) {
      toast({
        title: "Generation failed.",
        description: e instanceof Error ? e.message : undefined,
        kind: "error",
      });
    } finally {
      setRegenerating(false);
    }
  }

  return (
    <>
      <div className="space-y-5 min-w-0">
        <VisibilityCard busy={busy} onChange={setStatusAndSave} status={status} />

        <GenderCard
          busy={busy}
          current={product.gender}
          onChange={async (g) => {
            await patch({ gender: g });
          }}
        />

        <CatalogImageCard
          onRegenerate={() => setRegenerateOpen(true)}
          regenerating={regenerating}
        />

        <VariantsCard
          onAddVariant={() => setAddVariantOpen(true)}
          variants={product.variants}
        />
      </div>

      {/* AI regenerate confirmation modal */}
      <Modal
        description="This replaces the current primary photo. The old image is marked for the retention sweep."
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={regenerating}
              onClick={() => setRegenerateOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={regenerating}
              onClick={confirmRegenerate}
              type="button"
            >
              {regenerating ? "Generating…" : "Generate image"}
            </button>
          </>
        }
        onClose={() => setRegenerateOpen(false)}
        open={regenerateOpen}
        size="sm"
        title="Regenerate catalog image"
      >
        <p className="text-[13px] leading-relaxed text-[color:var(--ink-soft)]">
          Uses the product&apos;s title, category, material, and palette as the prompt.
          Generation typically takes 5-10 seconds.
        </p>
      </Modal>

      {/* Add-variant modal scoped to this product */}
      <AddVariantModal
        currency={product.pricing.currency}
        onClose={() => setAddVariantOpen(false)}
        open={addVariantOpen}
        productId={product.product_id}
        productTitle={product.title}
      />
    </>
  );
}

function VisibilityCard({
  status,
  busy,
  onChange,
}: {
  status: Status;
  busy: boolean;
  onChange: (s: Status) => void;
}) {
  const options: Status[] = ["draft", "published", "archived"];
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
        Visibility
      </div>
      <div className="flex gap-1 p-1 bg-[color:var(--ivory)] rounded-md max-w-md">
        {options.map((s) => {
          const active = status === s;
          return (
            <button
              className={
                "flex-1 text-[12px] px-3 py-1.5 rounded transition-colors capitalize " +
                (active
                  ? "bg-white text-[color:var(--ink)] shadow-sm font-medium"
                  : "text-[color:var(--muted)] hover:text-[color:var(--ink)]")
              }
              disabled={busy}
              key={s}
              onClick={() => onChange(s)}
              type="button"
            >
              {s}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function GenderCard({
  current,
  busy,
  onChange,
}: {
  current: "women" | "men" | "unisex";
  busy: boolean;
  onChange: (g: "women" | "men" | "unisex") => void | Promise<void>;
}) {
  const options: Array<"women" | "men" | "unisex"> = ["women", "men", "unisex"];
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        Gender
      </div>
      <p className="text-[11px] text-[color:var(--muted)] mb-3">
        Unisex appears under both Women and Men in the storefront nav.
      </p>
      <div className="flex gap-1 p-1 bg-[color:var(--ivory)] rounded-md max-w-md">
        {options.map((g) => {
          const active = current === g;
          return (
            <button
              className={
                "flex-1 text-[12px] px-3 py-1.5 rounded transition-colors capitalize " +
                (active
                  ? "bg-white text-[color:var(--ink)] shadow-sm font-medium"
                  : "text-[color:var(--muted)] hover:text-[color:var(--ink)]")
              }
              disabled={busy}
              key={g}
              onClick={() => void onChange(g)}
              type="button"
            >
              {g}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CatalogImageCard({
  regenerating,
  onRegenerate,
}: {
  regenerating: boolean;
  onRegenerate: () => void;
}) {
  return (
    <div className="card-solid p-5">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
          Catalog image
        </div>
        <button
          className="btn-secondary text-[12px] h-8 inline-flex items-center gap-1.5"
          disabled={regenerating}
          onClick={onRegenerate}
          type="button"
        >
          <svg
            aria-hidden
            fill="none"
            height="13"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            width="13"
          >
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2" />
            <circle cx="12" cy="12" r="4.5" />
          </svg>
          Regenerate via AI
        </button>
      </div>
      <p className="text-[12px] text-[color:var(--muted)]">
        Uses the product&apos;s title, category, material, and palette as a prompt.
        The replaced image is marked for the retention sweep.
      </p>
    </div>
  );
}

function variantStockState(v: AdminVariantDetail): "healthy" | "low" | "oos" | "untracked" {
  if (!v.inventory.track_inventory) return "untracked";
  if (v.inventory.stock_on_hand === 0) return "oos";
  if (v.inventory.stock_on_hand <= v.inventory.low_stock_threshold) return "low";
  return "healthy";
}

function statePill(state: ReturnType<typeof variantStockState>): {
  label: string;
  className: string;
} {
  switch (state) {
    case "oos":
      return {
        label: "Out",
        className: "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]",
      };
    case "low":
      return {
        label: "Low",
        className: "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]",
      };
    case "untracked":
      return {
        label: "Untracked",
        className:
          "bg-[color:var(--ivory)] text-[color:var(--muted)] border-[color:var(--line)]",
      };
    default:
      return {
        label: "Healthy",
        className: "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]",
      };
  }
}

function VariantsCard({
  variants,
  onAddVariant,
}: {
  variants: AdminVariantDetail[];
  onAddVariant: () => void;
}) {
  return (
    <div className="card-solid p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Catalog
          </div>
          <div className="font-display text-lg leading-tight">
            Variants &amp; stock
          </div>
          <p className="text-[11px] text-[color:var(--muted)] mt-0.5">
            {variants.length} variant{variants.length === 1 ? "" : "s"} attached
          </p>
        </div>
        <button
          className="btn-primary text-[12px] h-8 inline-flex items-center gap-1.5"
          onClick={onAddVariant}
          type="button"
        >
          <svg
            aria-hidden
            fill="none"
            height="13"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            width="13"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add variant
        </button>
      </div>

      {variants.length === 0 ? (
        <div className="py-10 text-center text-sm text-[color:var(--muted)]">
          No variants yet. Add the first one to start tracking stock.
        </div>
      ) : (
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-[13px] min-w-[640px]">
            <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
              <tr className="text-left border-b border-[color:var(--line)]">
                <th className="py-2 px-5 font-normal">SKU</th>
                <th className="font-normal">Variant</th>
                <th className="font-normal text-right">Price</th>
                <th className="font-normal text-right">Stock</th>
                <th className="font-normal text-center">State</th>
                <th className="font-normal text-right px-5">Adjust</th>
              </tr>
            </thead>
            <tbody>
              {variants.map((v) => {
                const state = variantStockState(v);
                const pill = statePill(state);
                const tint =
                  state === "oos"
                    ? "bg-[#fdecec]"
                    : state === "low"
                      ? "bg-[#fff7e6]"
                      : "";
                return (
                  <tr
                    className={`border-b border-[color:var(--line)] ${tint}`}
                    key={v.variant_id}
                  >
                    <td className="py-2.5 px-5 font-mono text-[11px]">{v.sku}</td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-1.5">
                        {v.color_hex ? (
                          <span
                            aria-hidden
                            className="inline-block h-3 w-3 rounded-full border border-[color:var(--line)]"
                            style={{ background: v.color_hex }}
                          />
                        ) : null}
                        <span>{v.color}</span>
                        <span className="text-[color:var(--muted)]">·</span>
                        <span className="font-mono text-[12px]">{v.size}</span>
                      </div>
                    </td>
                    <td className="py-2.5 text-right tabular-nums whitespace-nowrap">
                      {formatMoney(v.pricing.price_amount, v.pricing.currency)}
                    </td>
                    <td className="py-2.5 text-right tabular-nums font-medium">
                      {v.inventory.track_inventory ? v.inventory.stock_on_hand : "—"}
                    </td>
                    <td className="py-2.5 text-center">
                      <span
                        className={
                          "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border " +
                          pill.className
                        }
                      >
                        {pill.label}
                      </span>
                    </td>
                    <td className="py-2.5 px-5 text-right">
                      <StockAdjuster
                        current={v.inventory.stock_on_hand}
                        productId={v.product_id}
                        threshold={v.inventory.low_stock_threshold}
                        tracked={v.inventory.track_inventory}
                        variantId={v.variant_id}
                        variantLabel={`${v.sku} · ${v.color} ${v.size}`}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddVariantModal({
  open,
  onClose,
  productId,
  productTitle,
  currency,
}: {
  open: boolean;
  onClose: () => void;
  productId: string;
  productTitle: string;
  currency: string;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [sku, setSku] = useState("");
  const [size, setSize] = useState("");
  const [color, setColor] = useState("");
  const [colorHex, setColorHex] = useState("");
  const [priceStr, setPriceStr] = useState("");
  const [stockStr, setStockStr] = useState("0");
  const [thresholdStr, setThresholdStr] = useState("5");
  const [statusVal, setStatusVal] = useState<"active" | "archived">("active");
  const [busy, setBusy] = useState(false);

  function reset() {
    setSku("");
    setSize("");
    setColor("");
    setColorHex("");
    setPriceStr("");
    setStockStr("0");
    setThresholdStr("5");
    setStatusVal("active");
  }

  async function submit() {
    if (!sku.trim() || !size.trim() || !color.trim()) {
      toast({ title: "SKU, size and color are required.", kind: "warning" });
      return;
    }
    const priceCents = Math.round(parseFloat(priceStr) * 100);
    if (Number.isNaN(priceCents) || priceCents <= 0) {
      toast({ title: "Price must be a positive number.", kind: "warning" });
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        sku: sku.trim(),
        size: size.trim(),
        color: color.trim(),
        status: statusVal,
        pricing: { price_amount: priceCents, currency },
        inventory: {
          stock_on_hand: Math.max(0, parseInt(stockStr, 10) || 0),
          low_stock_threshold: Math.max(0, parseInt(thresholdStr, 10) || 5),
          track_inventory: true,
        },
      };
      if (colorHex.trim()) body.color_hex = colorHex.trim();

      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/products/${encodeURIComponent(productId)}/variants`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        },
      );
      if (!r.ok) {
        let detail = `${r.status}`;
        try {
          const b = (await r.json()) as { error?: { message?: string } };
          detail = b.error?.message ?? detail;
        } catch {
          // ignore
        }
        toast({
          title: "Couldn’t create variant.",
          description: detail,
          kind: "error",
        });
        return;
      }
      toast({ title: "Variant created.", kind: "success" });
      reset();
      onClose();
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      description={`On ${productTitle}`}
      footer={
        <>
          <button
            className="btn-ghost text-[13px]"
            disabled={busy}
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="btn-primary text-[13px]"
            disabled={busy}
            onClick={submit}
            type="button"
          >
            {busy ? "Creating…" : "Create variant"}
          </button>
        </>
      }
      onClose={onClose}
      open={open}
      size="md"
      title="Add variant"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <LabeledField label="SKU">
          <input
            className="input h-9 text-[13px]"
            onChange={(e) => setSku(e.target.value)}
            placeholder="ABC-BLA-M"
            value={sku}
          />
        </LabeledField>
        <LabeledField label={`Price (${currency})`}>
          <input
            className="input h-9 text-[13px]"
            inputMode="decimal"
            onChange={(e) => setPriceStr(e.target.value)}
            placeholder="49.00"
            value={priceStr}
          />
        </LabeledField>
        <LabeledField label="Size">
          <input
            className="input h-9 text-[13px]"
            onChange={(e) => setSize(e.target.value)}
            placeholder="M"
            value={size}
          />
        </LabeledField>
        <LabeledField label="Color">
          <input
            className="input h-9 text-[13px]"
            onChange={(e) => setColor(e.target.value)}
            placeholder="Black"
            value={color}
          />
        </LabeledField>
        <LabeledField hint="Optional. Used for the swatch dot." label="Colour hex">
          <input
            className="input h-9 text-[13px]"
            onChange={(e) => setColorHex(e.target.value)}
            placeholder="#0a0a0a"
            value={colorHex}
          />
        </LabeledField>
        <LabeledField label="Status">
          <SelectField
            dim="md"
            onChange={(e) => setStatusVal(e.target.value as "active" | "archived")}
            value={statusVal}
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </SelectField>
        </LabeledField>
        <LabeledField label="Initial stock">
          <input
            className="input h-9 text-[13px]"
            inputMode="numeric"
            onChange={(e) => setStockStr(e.target.value)}
            value={stockStr}
          />
        </LabeledField>
        <LabeledField label="Low-stock threshold">
          <input
            className="input h-9 text-[13px]"
            inputMode="numeric"
            onChange={(e) => setThresholdStr(e.target.value)}
            value={thresholdStr}
          />
        </LabeledField>
      </div>
    </Modal>
  );
}
