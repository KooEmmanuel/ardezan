"use client";

import { useMemo, useState } from "react";

import { TryOnButton } from "@/components/try-on-button";
import { formatMoney } from "@/lib/api";
import { addVariantToCart } from "@/lib/cart";
import type { ProductDetail, VariantPublic } from "@/lib/types";

export function ProductBuyPanel({ product }: { product: ProductDetail }) {
  const firstAvailable = product.variants.find((v) => v.available_for_sale > 0);
  const [selectedId, setSelectedId] = useState<string>(firstAvailable?.variant_id ?? "");
  const [feedback, setFeedback] = useState<string | null>(null);

  const selected: VariantPublic | null = useMemo(
    () => product.variants.find((v) => v.variant_id === selectedId) ?? null,
    [product.variants, selectedId],
  );

  // Group variants by color so the UI shows swatches + a size picker. This
  // matches the prototype's two-axis selector and stays readable when the
  // variant grid is sparse.
  const colorMap = useMemo(() => {
    const m = new Map<string, { hex: string | null; sizes: VariantPublic[] }>();
    for (const v of product.variants) {
      const key = v.color || "—";
      if (!m.has(key)) m.set(key, { hex: v.color_hex, sizes: [] });
      m.get(key)!.sizes.push(v);
    }
    return m;
  }, [product.variants]);

  const selectedColor = selected?.color ?? null;
  const sizesForSelectedColor = selectedColor
    ? (colorMap.get(selectedColor)?.sizes ?? [])
    : [];

  function pickColor(color: string) {
    const sizes = colorMap.get(color)?.sizes ?? [];
    const available = sizes.find((v) => v.available_for_sale > 0) ?? sizes[0];
    if (available) setSelectedId(available.variant_id);
  }

  function pickSize(variantId: string) {
    setSelectedId(variantId);
  }

  function onAdd() {
    if (!selected || selected.available_for_sale <= 0) return;
    addVariantToCart({ product_id: product.product_id, variant: selected });
    setFeedback("Added to cart.");
  }

  const price = selected?.pricing.price_amount ?? product.pricing.base_price_amount;
  const compareAt =
    selected?.pricing.compare_at_price_amount ?? product.pricing.compare_at_price_amount;
  const onSale =
    typeof compareAt === "number" && typeof price === "number" && compareAt > price;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
          {product.category}
          {product.subcategory ? ` · ${product.subcategory}` : ""}
        </p>
        <h1 className="font-display text-4xl sm:text-5xl leading-[1.02] tracking-tight">
          {product.title}
        </h1>
      </div>

      <div className="flex items-baseline gap-3">
        <span className="font-display text-2xl">
          {formatMoney(price, product.pricing.currency)}
        </span>
        {onSale ? (
          <span className="text-[color:var(--muted)] line-through text-sm">
            {formatMoney(compareAt, product.pricing.currency)}
          </span>
        ) : null}
        {onSale ? <span className="pill pill-sale">Sale</span> : null}
      </div>

      {product.description ? (
        <p className="text-[color:var(--muted)] leading-relaxed">
          {product.description}
        </p>
      ) : null}

      {colorMap.size > 1 ? (
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
            Color {selectedColor ? `· ${selectedColor}` : ""}
          </div>
          <div className="flex flex-wrap gap-2">
            {Array.from(colorMap.entries()).map(([color, info]) => {
              const isActive = color === selectedColor;
              const anyAvail = info.sizes.some((v) => v.available_for_sale > 0);
              return (
                <button
                  className="relative"
                  disabled={!anyAvail}
                  key={color}
                  onClick={() => pickColor(color)}
                  title={color + (anyAvail ? "" : " — sold out")}
                  type="button"
                >
                  <span
                    className="block w-9 h-9 rounded-full border"
                    style={{
                      background: info.hex ?? "#cccccc",
                      borderColor: isActive ? "var(--ink)" : "var(--line)",
                      boxShadow: isActive ? "0 0 0 2px var(--paper) inset, 0 0 0 4px var(--ink)" : undefined,
                      opacity: anyAvail ? 1 : 0.35,
                    }}
                  />
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {sizesForSelectedColor.length > 0 ? (
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
            Size
          </div>
          <div className="flex flex-wrap gap-2">
            {sizesForSelectedColor.map((v) => {
              const sold = v.available_for_sale <= 0;
              const isActive = v.variant_id === selectedId;
              return (
                <button
                  className="min-w-[3rem] px-3 py-2 rounded-md border text-sm"
                  disabled={sold}
                  key={v.variant_id}
                  onClick={() => pickSize(v.variant_id)}
                  style={{
                    background: isActive ? "var(--ink)" : "#fff",
                    color: isActive ? "var(--paper)" : "var(--ink)",
                    borderColor: isActive ? "var(--ink)" : "var(--line)",
                    opacity: sold ? 0.4 : 1,
                  }}
                  type="button"
                >
                  {v.size}
                  {sold ? <span className="block text-[10px] uppercase">Sold</span> : null}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {selected && selected.available_for_sale > 0 && selected.available_for_sale <= 3 ? (
        <p className="text-[12px] text-[color:var(--ink-soft)]">
          Only {selected.available_for_sale} left in this size.
        </p>
      ) : null}

      <button
        className="btn-primary w-full"
        disabled={!selected || selected.available_for_sale <= 0}
        onClick={onAdd}
        type="button"
      >
        {selected && selected.available_for_sale > 0 ? "Add to bag" : "Sold out"}
      </button>

      <TryOnButton
        className="w-full"
        label="See it on me"
        productId={product.product_id}
        productSlug={product.slug}
        variant="pill"
      />

      {feedback ? (
        <p className="text-sm text-[color:#166534] mt-2">{feedback}</p>
      ) : null}

      {product.product_details.material || product.product_details.fit_notes ? (
        <div className="border-t border-[color:var(--line)] pt-5 space-y-3 text-sm">
          {product.product_details.material ? (
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-0.5">
                Material
              </div>
              <p>{product.product_details.material}</p>
            </div>
          ) : null}
          {product.product_details.fit_notes ? (
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-0.5">
                Fit
              </div>
              <p>{product.product_details.fit_notes}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
