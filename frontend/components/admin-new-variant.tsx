"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { LabeledField, SelectField } from "@/components/form-fields";
import { Modal } from "@/components/modal";
import { useToast } from "@/components/toast";
import { API_BASE_URL } from "@/lib/api";

type ProductOption = { product_id: string; title: string; currency: string };

export function NewVariantWidget({ products }: { products: ProductOption[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [productId, setProductId] = useState(products[0]?.product_id ?? "");
  const [sku, setSku] = useState("");
  const [size, setSize] = useState("");
  const [color, setColor] = useState("");
  const [priceStr, setPriceStr] = useState("");
  const [stockStr, setStockStr] = useState("0");
  const [thresholdStr, setThresholdStr] = useState("5");
  const [busy, setBusy] = useState(false);

  const selected = products.find((p) => p.product_id === productId);
  const currency = selected?.currency ?? "USD";

  function reset() {
    setSku("");
    setSize("");
    setColor("");
    setPriceStr("");
    setStockStr("0");
    setThresholdStr("5");
  }

  async function submit() {
    if (!productId) {
      toast({ title: "Pick a product.", kind: "warning" });
      return;
    }
    if (!sku.trim() || !size.trim() || !color.trim()) {
      toast({
        title: "SKU, size and color are required.",
        kind: "warning",
      });
      return;
    }
    const priceCents = Math.round(parseFloat(priceStr) * 100);
    if (Number.isNaN(priceCents) || priceCents <= 0) {
      toast({ title: "Price must be a positive number.", kind: "warning" });
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/products/${encodeURIComponent(productId)}/variants`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            sku: sku.trim(),
            size: size.trim(),
            color: color.trim(),
            pricing: { price_amount: priceCents, currency },
            inventory: {
              stock_on_hand: Math.max(0, parseInt(stockStr, 10) || 0),
              low_stock_threshold: Math.max(0, parseInt(thresholdStr, 10) || 5),
              track_inventory: true,
            },
          }),
        },
      );
      if (!r.ok) {
        let detail = `${r.status}`;
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          detail = body.error?.message ?? detail;
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
      setOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        className="btn-primary text-sm inline-flex items-center gap-1.5"
        onClick={() => setOpen(true)}
        type="button"
      >
        <svg
          aria-hidden
          fill="none"
          height="14"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
          width="14"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        New variant
      </button>

      <Modal
        description="Variants belong to a product. Pick one to attach to."
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
              onClick={submit}
              type="button"
            >
              {busy ? "Creating…" : "Create variant"}
            </button>
          </>
        }
        onClose={() => setOpen(false)}
        open={open}
        size="md"
        title="New variant"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="sm:col-span-2">
            <LabeledField label="Product">
              <SelectField
                dim="md"
                onChange={(e) => setProductId(e.target.value)}
                value={productId}
              >
                {products.map((p) => (
                  <option key={p.product_id} value={p.product_id}>
                    {p.title}
                  </option>
                ))}
              </SelectField>
            </LabeledField>
          </div>
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
    </>
  );
}
