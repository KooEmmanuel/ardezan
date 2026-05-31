import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminProductEditor } from "@/components/admin-product-editor";
import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

function statusStyle(status: string): string {
  switch (status) {
    case "published":
      return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
    case "draft":
      return "bg-[#f3f1ea] text-[#6b5c2a] border-[#e3dec7]";
    case "archived":
      return "bg-[color:var(--ivory)] text-[color:var(--muted)] border-[color:var(--line)]";
    default:
      return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
  }
}

export default async function AdminProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await adminApi.getProduct(id);
  if (result.kind === "unauth") return null;
  if (result.kind === "error") notFound();

  const product = result.data;

  const totalStock = product.variants.reduce(
    (acc, v) =>
      acc + (v.inventory.track_inventory ? v.inventory.stock_on_hand : 0),
    0,
  );

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)]">
        <Link className="underline underline-offset-2" href="/admin/products">
          Products
        </Link>
        <span aria-hidden>›</span>
        <span className="truncate">{product.title}</span>
      </nav>

      <PageHeader
        eyebrow="Catalog"
        title={product.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] text-[color:var(--muted)]">
              /{product.slug}
            </span>
            <span
              className={
                "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border " +
                statusStyle(product.status)
              }
            >
              {product.status}
            </span>
            <span className="text-[color:var(--muted)]">·</span>
            <span className="capitalize">{product.category}</span>
            {product.subcategory ? (
              <span className="text-[color:var(--muted)]">/ {product.subcategory}</span>
            ) : null}
          </span>
        }
        actions={
          <Link
            className="btn-secondary text-sm inline-flex items-center gap-1.5"
            href={`/p/${product.slug}`}
            target="_blank"
          >
            View live
            <svg aria-hidden fill="none" height="12" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="12">
              <path d="M14 3h7v7M21 3l-9 9M10 4H4v16h16v-6" />
            </svg>
          </Link>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6 items-start">
        <SummaryCard
          currency={product.pricing.currency}
          mediaUrls={product.media_urls}
          price={product.pricing.base_price_amount}
          primary={product.primary_image_url}
          productId={product.product_id}
          tags={product.tags}
          title={product.title}
          totalStock={totalStock}
          variantCount={product.variants.length}
        />

        <AdminProductEditor product={product} />
      </div>
    </>
  );
}

function SummaryCard({
  primary,
  mediaUrls,
  title,
  productId,
  price,
  currency,
  variantCount,
  totalStock,
  tags,
}: {
  primary: string | null;
  mediaUrls: string[];
  title: string;
  productId: string;
  price: number;
  currency: string;
  variantCount: number;
  totalStock: number;
  tags: string[];
}) {
  return (
    <div className="card-solid overflow-hidden lg:sticky lg:top-6">
      <div className="ratio-45 relative bg-[color:var(--ivory)]">
        {primary ? (
          <Image
            alt={title}
            className="object-cover"
            fill
            sizes="280px"
            src={primary}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[color:var(--muted)] text-xs">
            no image
          </div>
        )}
      </div>

      {mediaUrls.length > 1 ? (
        <div className="px-3 pt-3 flex gap-1.5 overflow-x-auto scrollbar-thin">
          {mediaUrls.slice(0, 6).map((url, i) => (
            <div
              className="relative h-12 w-10 rounded bg-[color:var(--ivory)] border border-[color:var(--line)] overflow-hidden shrink-0"
              key={url + i}
            >
              <Image alt="" className="object-cover" fill sizes="40px" src={url} />
            </div>
          ))}
        </div>
      ) : null}

      <div className="p-4 space-y-3">
        <div>
          <div className="font-display text-base leading-tight">{title}</div>
          <div className="font-mono text-[10px] text-[color:var(--muted)] mt-0.5 truncate">
            {productId}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <Stat label="Price" value={formatMoney(price, currency)} />
          <Stat label="Variants" value={String(variantCount)} />
          <Stat label="Stock" value={String(totalStock)} />
        </div>

        {tags.length > 0 ? (
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)] mb-1.5">
              Tags
            </div>
            <div className="flex flex-wrap gap-1">
              {tags.slice(0, 8).map((t) => (
                <span
                  className="px-1.5 py-px text-[10px] uppercase tracking-[0.06em] rounded-sm bg-[color:var(--ivory)] border border-[color:var(--line)] text-[color:var(--muted)]"
                  key={t}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[color:var(--ivory)] rounded-md px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
        {label}
      </div>
      <div className="text-[13px] tabular-nums leading-tight mt-0.5 truncate">
        {value}
      </div>
    </div>
  );
}
