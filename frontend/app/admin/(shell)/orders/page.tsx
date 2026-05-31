import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type SearchParams = { status?: string; custom?: string };

const FILTERS: { label: string; value?: string }[] = [
  { label: "All" },
  { label: "Pending pay", value: "pending_payment" },
  { label: "Paid", value: "paid" },
  { label: "Packed", value: "packed" },
  { label: "Shipped", value: "shipped" },
  { label: "Delivered", value: "delivered" },
  { label: "Returns", value: "return_requested" },
  { label: "Refunded", value: "refunded" },
  { label: "Cancelled", value: "cancelled" },
];

function statusStyle(status: string): string {
  if (status === "paid" || status === "packed")
    return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
  if (status === "shipped")
    return "bg-[#eaf1fb] text-[#1f4b8d] border-[#c2d6ef]";
  if (status === "delivered")
    return "bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]";
  if (status === "pending_payment")
    return "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]";
  if (status === "cancelled" || status === "refunded" || status === "partially_refunded")
    return "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]";
  return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
}

export default async function AdminOrdersPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { status, custom } = await searchParams;
  const onlyCustom = custom === "1";
  const result = await adminApi.listOrders({
    status,
    limit: 100,
    has_custom_design: onlyCustom || undefined,
  });
  if (result.kind === "unauth") return null;

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Orders"
        subtitle={
          result.kind === "ok"
            ? `${result.data.total} total${status ? ` · ${status.replace(/_/g, " ")}` : ""}`
            : "Couldn’t reach orders."
        }
      />

      <div className="flex flex-wrap items-center gap-1">
        {FILTERS.map((f) => {
          const active = (f.value ?? "") === (status ?? "");
          const qs = new URLSearchParams();
          if (f.value) qs.set("status", f.value);
          if (onlyCustom) qs.set("custom", "1");
          const href = qs.toString() ? `/admin/orders?${qs.toString()}` : "/admin/orders";
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
              key={f.label}
            >
              {f.label}
            </Link>
          );
        })}
        {/* Cross-cutting toggle: any status, but only orders that contain
            at least one custom_design line. */}
        {(() => {
          const qs = new URLSearchParams();
          if (status) qs.set("status", status);
          if (!onlyCustom) qs.set("custom", "1");
          const href = qs.toString() ? `/admin/orders?${qs.toString()}` : "/admin/orders";
          return (
            <Link
              aria-current={onlyCustom ? "page" : undefined}
              className={
                "ml-2 px-3 h-8 inline-flex items-center rounded-md text-[12px] border transition-colors " +
                (onlyCustom
                  ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                  : "bg-white text-[color:var(--ink-soft)] border-[color:var(--line)] hover:bg-[color:var(--ivory)]")
              }
              href={href}
            >
              Custom designs
            </Link>
          );
        })()}
      </div>

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn’t load orders: {result.message}
        </div>
      ) : (
        <div className="card-solid overflow-x-auto">
          <table className="w-full text-[13px] min-w-[720px]">
            <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
              <tr>
                <th className="py-2.5 px-4 font-normal text-left">Order</th>
                <th className="py-2.5 px-3 font-normal text-left">Date</th>
                <th className="py-2.5 px-3 font-normal text-left">Customer</th>
                <th className="py-2.5 px-3 font-normal text-center">Status</th>
                <th className="py-2.5 px-4 font-normal text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.length === 0 ? (
                <tr>
                  <td className="py-10 px-4 text-center text-[color:var(--muted)]" colSpan={5}>
                    No orders match these filters.
                  </td>
                </tr>
              ) : (
                result.data.items.map((o) => {
                  const hasCustom = (o.lines ?? []).some(
                    (l) => l.kind === "custom_design",
                  );
                  return (
                  <tr className="border-t border-[color:var(--line)]" key={o.order_id}>
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-1.5">
                        <Link className="font-mono text-[12px] underline underline-offset-2" href={`/admin/orders/${o.order_id}`}>
                          {o.order_number}
                        </Link>
                        {hasCustom ? (
                          <span
                            className="inline-flex items-center px-1.5 py-0 rounded text-[9.5px] tracking-[0.06em] uppercase border bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]"
                            title="Order contains a Design Me piece"
                          >
                            Custom
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                      {new Date(o.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2.5 px-3 truncate max-w-[220px]">
                      {o.customer_id ? "Registered" : (o.guest_email ?? "Guest")}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={
                          "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] tracking-[0.06em] uppercase border " +
                          statusStyle(o.status)
                        }
                      >
                        {o.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right tabular-nums whitespace-nowrap">
                      {formatMoney(o.totals.total_amount, o.totals.currency)}
                    </td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
