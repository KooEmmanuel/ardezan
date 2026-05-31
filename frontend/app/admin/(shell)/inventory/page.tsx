import Image from "next/image";
import Link from "next/link";

import { NewVariantWidget } from "@/components/admin-new-variant";
import { PageHeader } from "@/components/admin-page-header";
import { StockAdjuster } from "@/components/admin-stock-adjuster";
import { SearchField } from "@/components/form-fields";
import { formatMoney } from "@/lib/api";
import { adminApi, type InventoryVariant } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type Health = "all" | "low" | "oos" | "healthy" | "untracked";
type SearchParams = { health?: Health; q?: string };

const HEALTH_TABS: { value: Health; label: string }[] = [
  { value: "all", label: "All" },
  { value: "oos", label: "Out of stock" },
  { value: "low", label: "Low stock" },
  { value: "healthy", label: "Healthy" },
  { value: "untracked", label: "Untracked" },
];

const REASON_LABELS: Record<string, string> = {
  admin_adjustment: "Admin adjustment",
  payment_decrement: "Sold (paid)",
  cancel_restock: "Order cancelled",
  refund_restock: "Refund restock",
  import: "Bulk import",
  system_correction: "System correction",
};

function stateStyle(state: InventoryVariant["stock_state"]): string {
  switch (state) {
    case "oos":
      return "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]";
    case "low":
      return "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]";
    case "untracked":
      return "bg-[color:var(--ivory)] text-[color:var(--muted)] border-[color:var(--line)]";
    default:
      return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
  }
}

function stateLabel(state: InventoryVariant["stock_state"]): string {
  switch (state) {
    case "oos":
      return "Out";
    case "low":
      return "Low";
    case "untracked":
      return "Untracked";
    default:
      return "Healthy";
  }
}

export default async function AdminInventoryPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { health, q } = await searchParams;

  const [stockResult, movementsResult, productsResult] = await Promise.all([
    adminApi.listInventoryVariants({
      health: health ?? "all",
      q,
      limit: 200,
    }),
    adminApi.listInventoryMovements({ limit: 30 }),
    adminApi.listProducts({ status: "published", limit: 200 }),
  ]);

  if (stockResult.kind === "unauth") return null;

  const productOptions =
    productsResult.kind === "ok"
      ? productsResult.data.items.map((p) => ({
          product_id: p.product_id,
          title: p.title,
          currency: p.pricing.currency,
        }))
      : [];

  return (
    <>
      <PageHeader
        eyebrow="Catalog"
        title="Inventory"
        subtitle={
          stockResult.kind === "ok"
            ? `${stockResult.data.total} variants${health && health !== "all" ? ` · ${health}` : ""}${q ? ` · matching “${q}”` : ""}`
            : "Couldn’t reach inventory."
        }
        actions={<NewVariantWidget products={productOptions} />}
      />

      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1">
          {HEALTH_TABS.map((tab) => {
            const active = (health ?? "all") === tab.value;
            const params = new URLSearchParams();
            if (tab.value !== "all") params.set("health", tab.value);
            if (q) params.set("q", q);
            const href = `/admin/inventory${params.toString() ? `?${params.toString()}` : ""}`;
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={
                  "px-3 h-8 inline-flex items-center rounded-md text-[12px] border transition-colors " +
                  (active
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "bg-white text-[color:var(--ink-soft)] border-[color:var(--line)] hover:bg-[color:var(--ivory)]")
                }
                href={href}
                key={tab.value}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>

        <form className="flex items-center gap-2" method="get">
          {health && health !== "all" ? (
            <input name="health" type="hidden" value={health} />
          ) : null}
          <SearchField
            aria-label="Search SKU / product / colour"
            className="w-56"
            defaultValue={q}
            name="q"
            placeholder="Search SKU, title, colour…"
          />
        </form>
      </div>

      {stockResult.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn’t load inventory: {stockResult.message}
        </div>
      ) : (
        <StockTable items={stockResult.data.items} />
      )}

      <div className="card-solid p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
              History
            </div>
            <h2 className="font-display text-xl mt-0.5">Recent movements</h2>
            <p className="text-[11px] text-[color:var(--muted)] mt-1">
              Initial stock set during product creation doesn’t appear here.
              Every adjustment, sale, and restock from this point on is logged below.
            </p>
          </div>
        </div>
        {movementsResult.kind === "ok" ? (
          movementsResult.data.items.length === 0 ? (
            <p className="text-sm text-[color:var(--muted)] py-6 text-center">
              No movements yet. Adjust a variant above to start the ledger.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px] min-w-[680px]">
                <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                  <tr className="text-left">
                    <th className="pb-2 font-normal">When</th>
                    <th className="font-normal">Variant</th>
                    <th className="font-normal text-right">Δ</th>
                    <th className="font-normal text-right">After</th>
                    <th className="font-normal">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {movementsResult.data.items.map((m) => (
                    <tr
                      className="border-t border-[color:var(--line)] align-top"
                      key={m.movement_id}
                    >
                      <td className="py-2 text-[color:var(--muted)] whitespace-nowrap">
                        {new Date(m.created_at).toLocaleString()}
                      </td>
                      <td className="font-mono">{m.variant_id}</td>
                      <td
                        className="text-right font-mono tabular-nums"
                        style={{ color: m.delta < 0 ? "#8d1717" : "#166534" }}
                      >
                        {m.delta > 0 ? `+${m.delta}` : m.delta}
                      </td>
                      <td className="text-right tabular-nums">{m.quantity_after}</td>
                      <td>{REASON_LABELS[m.reason] ?? m.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          <p className="text-sm text-[color:var(--muted)]">Couldn’t load movements.</p>
        )}
      </div>
    </>
  );
}

function StockTable({ items }: { items: InventoryVariant[] }) {
  if (items.length === 0) {
    return (
      <div className="card-solid p-10 text-center text-sm text-[color:var(--muted)]">
        No variants match these filters.
      </div>
    );
  }
  return (
    <div className="card-solid overflow-x-auto">
      <table className="w-full text-[13px] min-w-[900px]">
        <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          <tr>
            <th className="py-2.5 px-4 font-normal text-left w-[34%]">Product</th>
            <th className="py-2.5 px-3 font-normal text-left">SKU</th>
            <th className="py-2.5 px-3 font-normal text-left">Variant</th>
            <th className="py-2.5 px-3 font-normal text-right">Price</th>
            <th className="py-2.5 px-3 font-normal text-right">Stock</th>
            <th className="py-2.5 px-3 font-normal text-right">Threshold</th>
            <th className="py-2.5 px-3 font-normal text-center">State</th>
            <th className="py-2.5 px-4 font-normal text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((v) => {
            const tint =
              v.stock_state === "oos"
                ? "bg-[#fdecec]"
                : v.stock_state === "low"
                  ? "bg-[#fff7e6]"
                  : "";
            return (
              <tr
                className={`border-t border-[color:var(--line)] ${tint}`}
                key={v.variant_id}
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-12 w-10 rounded bg-[color:var(--ivory)] border border-[color:var(--line)] overflow-hidden shrink-0 relative">
                      {v.product?.primary_image_url ? (
                        <Image
                          alt=""
                          className="object-cover"
                          fill
                          sizes="40px"
                          src={v.product.primary_image_url}
                        />
                      ) : (
                        <div className="flex items-center justify-center h-full text-[10px] text-[color:var(--muted)]">
                          —
                        </div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <Link
                        className="font-display text-[14px] hover:underline truncate block"
                        href={`/admin/products/${v.product_id}`}
                      >
                        {v.product?.title ?? "(deleted product)"}
                      </Link>
                      <div className="text-[11px] text-[color:var(--muted)] capitalize">
                        {v.product?.category}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 font-mono text-[12px]">{v.sku}</td>
                <td className="py-3 px-3">
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
                <td className="py-3 px-3 text-right tabular-nums whitespace-nowrap">
                  {formatMoney(v.pricing.price_amount, v.pricing.currency)}
                </td>
                <td className="py-3 px-3 text-right tabular-nums font-medium">
                  {v.track_inventory ? v.stock_on_hand : "—"}
                </td>
                <td className="py-3 px-3 text-right tabular-nums text-[color:var(--muted)]">
                  {v.track_inventory ? v.low_stock_threshold : "—"}
                </td>
                <td className="py-3 px-3 text-center">
                  <span
                    className={
                      "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] tracking-[0.06em] uppercase border " +
                      stateStyle(v.stock_state)
                    }
                  >
                    {stateLabel(v.stock_state)}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="inline-flex items-center gap-1.5">
                    <StockAdjuster
                      current={v.stock_on_hand}
                      productId={v.product_id}
                      threshold={v.low_stock_threshold}
                      tracked={v.track_inventory}
                      variantId={v.variant_id}
                      variantLabel={`${v.sku} · ${v.color} ${v.size}`}
                    />
                    <Link
                      className="text-[11px] underline underline-offset-2"
                      href={`/admin/products/${v.product_id}`}
                    >
                      Edit
                    </Link>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
