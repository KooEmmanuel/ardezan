import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

function statusStyle(status: string): string {
  if (status === "paid" || status === "packed")
    return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
  if (status === "shipped") return "bg-[#eaf1fb] text-[#1f4b8d] border-[#c2d6ef]";
  if (status === "delivered") return "bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]";
  if (status === "pending_payment")
    return "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]";
  if (
    status === "cancelled" ||
    status === "refunded" ||
    status === "partially_refunded"
  )
    return "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]";
  return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
}

export default async function AdminCustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [detail, orders] = await Promise.all([
    adminApi.getCustomer(id),
    adminApi.listCustomerOrders(id, 30),
  ]);

  if (detail.kind === "unauth") return null;
  if (detail.kind === "error") notFound();

  const c = detail.data;
  const ordersData = orders.kind === "ok" ? orders.data : null;

  const avg =
    c.orders_count > 0
      ? Math.round(c.lifetime_spend_amount / c.orders_count)
      : 0;

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)]">
        <Link className="underline underline-offset-2" href="/admin/customers">
          Customers
        </Link>
        <span aria-hidden>›</span>
        <span className="truncate">{c.name || c.email}</span>
      </nav>

      <PageHeader
        eyebrow="Customer"
        title={c.name || c.email}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span>{c.email}</span>
            {c.email_verified_at ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]">
                Verified
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]">
                Email pending
              </span>
            )}
            {c.accepts_marketing ? (
              <span className="pill pill-soft text-[10px]">Marketing opt-in</span>
            ) : null}
          </span>
        }
      />

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Tile
          label="Orders"
          value={String(c.orders_count)}
          foot={
            c.last_order_at
              ? `Last ${new Date(c.last_order_at).toLocaleDateString()}`
              : "No orders yet"
          }
        />
        <Tile
          label="Lifetime spend"
          value={formatMoney(c.lifetime_spend_amount, c.currency)}
          foot={`Avg ${formatMoney(avg, c.currency)}`}
        />
        <Tile
          label="Joined"
          value={new Date(c.created_at).toLocaleDateString()}
          foot={`Joined ${monthsSince(c.created_at)}`}
        />
        <Tile
          label="Last login"
          value={
            c.last_login_at
              ? new Date(c.last_login_at).toLocaleDateString()
              : "Never"
          }
          foot={c.last_login_at ? new Date(c.last_login_at).toLocaleTimeString() : "—"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Orders (2/3) */}
        <div className="lg:col-span-2 card-solid p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                History
              </div>
              <h2 className="font-display text-xl mt-0.5">Order history</h2>
            </div>
          </div>
          {ordersData && ordersData.items.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                  <tr className="text-left">
                    <th className="pb-2 font-normal">Order</th>
                    <th className="font-normal">Date</th>
                    <th className="font-normal">Status</th>
                    <th className="font-normal text-right">Items</th>
                    <th className="font-normal text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {ordersData.items.map((o) => (
                    <tr className="border-t border-[color:var(--line)]" key={o.order_id}>
                      <td className="py-2.5 font-mono text-[11px]">
                        <Link
                          className="underline underline-offset-2"
                          href={`/admin/orders/${o.order_id}`}
                        >
                          {o.order_number}
                        </Link>
                      </td>
                      <td className="text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                        {new Date(o.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <span
                          className={
                            "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border " +
                            statusStyle(o.status)
                          }
                        >
                          {o.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="text-right tabular-nums">{o.line_count}</td>
                      <td className="text-right tabular-nums whitespace-nowrap">
                        {formatMoney(o.total_amount, o.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-[color:var(--muted)] py-6 text-center">
              No orders yet for this customer.
            </p>
          )}
        </div>

        {/* Sidebar (1/3): addresses + privacy */}
        <div className="space-y-5">
          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
              Saved addresses
            </div>
            {c.addresses.length === 0 ? (
              <p className="text-[13px] text-[color:var(--muted)]">
                No addresses saved.
              </p>
            ) : (
              <ul className="space-y-3">
                {c.addresses.map((a, i) => (
                  <li
                    className="text-[13px] leading-relaxed"
                    key={`${a.line1 ?? ""}-${i}`}
                  >
                    {a.is_default ? (
                      <span className="pill pill-soft text-[9px] mb-1 inline-block">
                        Default
                      </span>
                    ) : null}
                    <div>{a.line1}</div>
                    {a.line2 ? <div>{a.line2}</div> : null}
                    <div className="text-[color:var(--muted)]">
                      {[a.city, a.region, a.postal_code].filter(Boolean).join(", ")}
                    </div>
                    <div className="text-[color:var(--muted)]">{a.country}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
              AI privacy state
            </div>
            <dl className="text-[13px] space-y-2">
              <Row label="Saved photo" yes={c.has_saved_photo} />
              <Row label="Body profile opt-in" yes={c.body_profile_opted_in} />
              <Row label="Marketing opt-in" yes={c.accepts_marketing} />
            </dl>
          </div>

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Identifiers
            </div>
            <dl className="text-[12px] space-y-1.5">
              <div>
                <dt className="text-[color:var(--muted)]">Customer ID</dt>
                <dd className="font-mono">{c.customer_id}</dd>
              </div>
              <div>
                <dt className="text-[color:var(--muted)]">Email</dt>
                <dd className="truncate">{c.email}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </>
  );
}

function Tile({
  label,
  value,
  foot,
}: {
  label: string;
  value: string;
  foot: string;
}) {
  return (
    <div className="card-solid p-4">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
        {label}
      </div>
      <div className="font-display text-[24px] leading-none mt-2 tabular-nums truncate">
        {value}
      </div>
      <div className="text-[11px] text-[color:var(--muted)] mt-1.5">{foot}</div>
    </div>
  );
}

function Row({ label, yes }: { label: string; yes: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <dt>{label}</dt>
      <dd
        className={
          "text-[11px] uppercase tracking-[0.08em] " +
          (yes ? "text-[#166534]" : "text-[color:var(--muted)]")
        }
      >
        {yes ? "Yes" : "No"}
      </dd>
    </div>
  );
}

function monthsSince(iso: string): string {
  const then = new Date(iso).getTime();
  const months = Math.max(0, Math.floor((Date.now() - then) / (1000 * 60 * 60 * 24 * 30)));
  if (months === 0) return "this month";
  if (months === 1) return "1 month ago";
  if (months < 12) return `${months} months ago`;
  const yrs = Math.floor(months / 12);
  return yrs === 1 ? "a year ago" : `${yrs} years ago`;
}
