import Image from "next/image";
import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { SearchField } from "@/components/form-fields";
import { formatMoney } from "@/lib/api";
import { adminApi, type AdminProductListItem } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type SearchParams = { status?: string; category?: string; q?: string };

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "published", label: "Published" },
  { value: "draft", label: "Drafts" },
  { value: "archived", label: "Archived" },
];

function priceLabel(p: AdminProductListItem): string {
  const cur = p.pricing.currency;
  if (
    p.price_min_amount != null &&
    p.price_max_amount != null &&
    p.price_min_amount !== p.price_max_amount
  ) {
    return `${formatMoney(p.price_min_amount, cur)} – ${formatMoney(p.price_max_amount, cur)}`;
  }
  return formatMoney(p.pricing.base_price_amount, cur);
}

function rowTint(p: AdminProductListItem): string {
  if (p.out_of_stock_variant_count > 0 && p.stock_on_hand_total === 0) {
    return "bg-[#fdecec]";
  }
  if (p.low_stock_variant_count > 0 || p.out_of_stock_variant_count > 0) {
    return "bg-[#fff7e6]";
  }
  return "";
}

function statusPill(status: string): string {
  switch (status) {
    case "published":
      return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
    case "draft":
      return "bg-[#f3f1ea] text-[#6b5c2a] border-[#e3dec7]";
    case "archived":
      return "bg-[#f1f1f1] text-[color:var(--muted)] border-[color:var(--line)]";
    default:
      return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
  }
}

export default async function AdminProductsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { status, category, q } = await searchParams;

  const result = await adminApi.listProducts({
    status: status || undefined,
    category: category || undefined,
    q: q || undefined,
    limit: 100,
  });

  if (result.kind === "unauth") return null;

  return (
    <>
      <PageHeader
        eyebrow="Catalog"
        title="Products"
        subtitle={
          result.kind === "ok" ? (
            <span>
              {result.data.total} total
              {status ? <> · filtered by <strong>{status}</strong></> : null}
              {category ? <> · in <strong>{category}</strong></> : null}
              {q ? <> · matching “{q}”</> : null}
            </span>
          ) : (
            "Couldn’t reach the catalog."
          )
        }
        actions={
          <Link className="btn-primary text-sm" href="/admin/products/new">
            + New product
          </Link>
        }
      />

      <FilterBar status={status ?? ""} category={category ?? ""} q={q ?? ""} />

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn’t load products: {result.message}
        </div>
      ) : (
        <ProductsTable items={result.data.items} />
      )}
    </>
  );
}

function FilterBar({
  status,
  category,
  q,
}: {
  status: string;
  category: string;
  q: string;
}) {
  return (
    <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-1">
        {STATUS_TABS.map((tab) => {
          const isActive = (status || "") === tab.value;
          const params = new URLSearchParams();
          if (tab.value) params.set("status", tab.value);
          if (category) params.set("category", category);
          if (q) params.set("q", q);
          const href = `/admin/products${params.toString() ? `?${params.toString()}` : ""}`;
          return (
            <Link
              aria-current={isActive ? "page" : undefined}
              className={
                "px-3 h-8 inline-flex items-center rounded-md text-[12px] border transition-colors " +
                (isActive
                  ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                  : "bg-white text-[color:var(--ink-soft)] border-[color:var(--line)] hover:bg-[color:var(--ivory)]")
              }
              href={href}
              key={tab.value || "all"}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <form className="flex flex-wrap items-center gap-2" method="get">
        {status ? <input name="status" type="hidden" value={status} /> : null}
        <input
          aria-label="Filter by category"
          className="h-8 px-3 text-[13px] rounded-md bg-white border border-[color:var(--line)] focus:outline-none focus:border-[color:var(--ink)] w-32"
          defaultValue={category}
          name="category"
          placeholder="Category"
        />
        <SearchField
          aria-label="Search products"
          className="w-56"
          defaultValue={q}
          name="q"
          placeholder="Search title, slug, tag…"
        />
        {(category || q) && (
          <Link
            className="text-[12px] text-[color:var(--muted)] hover:underline"
            href={status ? `/admin/products?status=${status}` : "/admin/products"}
          >
            Clear
          </Link>
        )}
      </form>
    </div>
  );
}

function ProductsTable({ items }: { items: AdminProductListItem[] }) {
  if (items.length === 0) {
    return (
      <div className="card-solid p-10 text-center text-sm text-[color:var(--muted)]">
        No products match these filters.
      </div>
    );
  }

  return (
    <div className="card-solid overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px] min-w-[860px]">
          <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            <tr>
              <th className="py-2.5 px-4 font-normal text-left w-[44%]">Product</th>
              <th className="py-2.5 px-3 font-normal text-left">Category</th>
              <th className="py-2.5 px-3 font-normal text-right">Variants</th>
              <th className="py-2.5 px-3 font-normal text-right">Stock</th>
              <th className="py-2.5 px-3 font-normal text-right">Price</th>
              <th className="py-2.5 px-3 font-normal text-center">Status</th>
              <th className="py-2.5 px-4 font-normal text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr
                className={`border-t border-[color:var(--line)] ${rowTint(p)}`}
                key={p.product_id}
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-14 w-11 rounded bg-[color:var(--ivory)] border border-[color:var(--line)] overflow-hidden shrink-0 relative">
                      {p.primary_image_url ? (
                        <Image
                          alt=""
                          className="object-cover"
                          fill
                          sizes="44px"
                          src={p.primary_image_url}
                        />
                      ) : (
                        <div className="flex items-center justify-center h-full w-full text-[10px] text-[color:var(--muted)]">
                          —
                        </div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <Link
                        className="font-display text-[15px] hover:underline truncate block"
                        href={`/admin/products/${p.product_id}`}
                      >
                        {p.title}
                      </Link>
                      <div className="text-[11px] text-[color:var(--muted)] truncate">
                        /{p.slug}
                      </div>
                      {p.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {p.tags.slice(0, 3).map((t) => (
                            <span
                              className="px-1.5 py-px text-[9px] uppercase tracking-[0.08em] rounded-sm bg-white border border-[color:var(--line)] text-[color:var(--muted)]"
                              key={t}
                            >
                              {t}
                            </span>
                          ))}
                          {p.tags.length > 3 ? (
                            <span className="text-[10px] text-[color:var(--muted)]">
                              +{p.tags.length - 3}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 align-middle">
                  <div className="capitalize">{p.category}</div>
                  {p.subcategory ? (
                    <div className="text-[11px] text-[color:var(--muted)]">
                      {p.subcategory}
                    </div>
                  ) : null}
                  <div className="mt-1">
                    <span
                      className={
                        "inline-flex items-center px-1.5 py-px text-[9px] uppercase tracking-[0.08em] rounded-sm border " +
                        (p.gender === "women"
                          ? "bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]"
                          : p.gender === "men"
                            ? "bg-[#eaf1fb] text-[#1f4b8d] border-[#c2d6ef]"
                            : "bg-[color:var(--ivory)] text-[color:var(--muted)] border-[color:var(--line)]")
                      }
                    >
                      {p.gender}
                    </span>
                  </div>
                </td>
                <td className="py-3 px-3 align-middle text-right tabular-nums">
                  {p.variant_count}
                </td>
                <td className="py-3 px-3 align-middle text-right">
                  <StockCell item={p} />
                </td>
                <td className="py-3 px-3 align-middle text-right tabular-nums whitespace-nowrap">
                  {priceLabel(p)}
                </td>
                <td className="py-3 px-3 align-middle text-center">
                  <span
                    className={
                      "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] tracking-[0.06em] uppercase border " +
                      statusPill(p.status)
                    }
                  >
                    {p.status}
                  </span>
                </td>
                <td className="py-3 px-4 align-middle text-right">
                  <Link
                    className="text-xs underline underline-offset-2"
                    href={`/admin/products/${p.product_id}`}
                  >
                    Edit
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StockCell({ item }: { item: AdminProductListItem }) {
  if (item.variant_count === 0) {
    return (
      <span className="text-[color:var(--muted)] text-[11px] italic">No variants</span>
    );
  }
  const allOut =
    item.out_of_stock_variant_count > 0 && item.stock_on_hand_total === 0;
  return (
    <div className="flex items-center justify-end gap-2">
      <span className="tabular-nums">{item.stock_on_hand_total}</span>
      {allOut ? (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] uppercase tracking-[0.06em] bg-[#fdecec] text-[#8d1717] border border-[#f0c2c2]">
          Out
        </span>
      ) : item.low_stock_variant_count > 0 || item.out_of_stock_variant_count > 0 ? (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] uppercase tracking-[0.06em] bg-[#fff7e6] text-[#8a5a00] border border-[#f0d8a0]">
          Low {item.low_stock_variant_count + item.out_of_stock_variant_count}
        </span>
      ) : null}
    </div>
  );
}
