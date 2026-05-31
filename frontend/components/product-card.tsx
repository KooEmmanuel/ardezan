import Link from "next/link";

import { formatMoney } from "@/lib/api";
import type { ProductListItem } from "@/lib/types";

export function ProductCard({ product }: { product: ProductListItem }) {
  const price = product.pricing.base_price_amount ?? product.pricing.price_amount;

  return (
    <article className="card-solid overflow-hidden product-card">
      <Link className="block ratio-45 relative overflow-hidden" href={`/product/${product.slug}`}>
        {product.primary_image_url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            alt={product.title}
            className="absolute inset-0 w-full h-full object-cover"
            loading="lazy"
            src={product.primary_image_url}
          />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-[color:var(--muted)] text-xs">
            {product.category}
          </span>
        )}
        {product.try_on_eligible ? (
          <span className="absolute top-2 left-2 pill pill-outline">AI ready</span>
        ) : null}
      </Link>
      <div className="p-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            {product.category}
          </p>
          <h3 className="font-display text-lg leading-tight m-0 truncate">{product.title}</h3>
        </div>
        <p className="text-sm m-0 shrink-0">{formatMoney(price, product.pricing.currency)}</p>
      </div>
    </article>
  );
}
