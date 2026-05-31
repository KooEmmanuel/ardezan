import { cookies } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { CustomerOrderActions } from "@/components/customer-order-actions";
import { TrackingCard } from "@/components/tracking-card";
import { formatMoney } from "@/lib/api";
import { serverApi } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function AccountOrderDetailPage({
  params,
}: {
  params: Promise<{ order_id: string }>;
}) {
  const { order_id } = await params;
  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  let order;
  try {
    order = await serverApi.getOrder(order_id, { cookie: cookieHeader });
  } catch {
    // Either 401 (not signed in) or 404 (not found / not owner).
    if (!cookieHeader.includes("customer_session=")) {
      redirect(
        `/auth/login?next=${encodeURIComponent(`/account/orders/${order_id}`)}`,
      );
    }
    notFound();
  }

  const currency = order.totals.currency;

  return (
    <section className="max-w-[900px] mx-auto px-5 py-12">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
            Order
          </div>
          <h1 className="font-display text-4xl">{order.order_number}</h1>
          <div className="text-xs text-[color:var(--muted)] mt-1 capitalize">
            {order.status.replace(/_/g, " ")} · placed{" "}
            {new Date(order.created_at).toLocaleDateString()}
          </div>
        </div>
        <Link className="btn-ghost underline underline-offset-4 text-sm" href="/account/orders">
          ← All orders
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        <div className="card-solid p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
            Items
          </div>
          <div className="space-y-3">
            {order.lines.map((line, i) => (
              <div className="flex items-start justify-between gap-4" key={`${line.variant_id}-${i}`}>
                <div className="flex-1 min-w-0">
                  <Link
                    className="font-display text-base hover:underline"
                    href={`/product/${line.product_id}`}
                  >
                    {line.title_snapshot}
                  </Link>
                  <div className="text-[12px] text-[color:var(--muted)]">
                    {[line.size, line.color, `× ${line.quantity}`].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="text-sm shrink-0">
                  {formatMoney(line.line_total_amount, currency)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <aside className="card-solid p-5 h-fit lg:sticky lg:top-24 space-y-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
              Delivering to
            </div>
            <div className="text-sm">{order.shipping_address.name}</div>
            <div className="text-[12px] text-[color:var(--muted)]">
              {order.shipping_address.line1}
              {order.shipping_address.line2 ? `, ${order.shipping_address.line2}` : ""}
            </div>
            <div className="text-[12px] text-[color:var(--muted)]">
              {[
                order.shipping_address.city,
                order.shipping_address.region,
                order.shipping_address.postal_code,
              ]
                .filter(Boolean)
                .join(", ")}
              <br />
              {order.shipping_address.country}
            </div>
          </div>
          <TrackingCard order={order} />
          <CustomerOrderActions order={order} />
          <div className="border-t border-[color:var(--line)] pt-3 text-sm space-y-1.5">
            <div className="flex justify-between"><span className="text-[color:var(--muted)]">Subtotal</span><span>{formatMoney(order.totals.subtotal_amount, currency)}</span></div>
            <div className="flex justify-between"><span className="text-[color:var(--muted)]">Shipping</span><span>{formatMoney(order.totals.shipping_amount, currency)}</span></div>
            <div className="flex justify-between"><span className="text-[color:var(--muted)]">Tax</span><span>{formatMoney(order.totals.tax_amount, currency)}</span></div>
            <div className="flex justify-between text-base font-medium pt-2 border-t border-[color:var(--line)]">
              <span>Total</span>
              <span>{formatMoney(order.totals.total_amount, currency)}</span>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
