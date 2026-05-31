import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { formatMoney } from "@/lib/api";
import { serverApi } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function AccountOrdersPage() {
  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  let result;
  try {
    result = await serverApi.listMyOrders(cookieHeader, { limit: 50 });
  } catch {
    return (
      <section className="max-w-[600px] mx-auto px-5 py-12">
        <div className="card-solid p-6 text-center">
          <div className="font-display text-2xl mb-2">Couldn&apos;t load orders.</div>
          <p className="text-[color:var(--muted)] mb-4">
            The server may be restarting — try again in a moment.
          </p>
          <Link className="btn-primary" href="/account/orders">
            Retry
          </Link>
        </div>
      </section>
    );
  }
  if (result === null) {
    redirect(`/auth/login?next=${encodeURIComponent("/account/orders")}`);
  }

  const { items, total } = result;

  return (
    <section className="max-w-[900px] mx-auto px-5 py-12">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between mb-6">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
            Your account
          </div>
          <h1 className="font-display text-4xl">Order history</h1>
          <div className="text-xs text-[color:var(--muted)] mt-1">{total} total</div>
        </div>
        <Link className="btn-ghost underline underline-offset-4 text-sm shrink-0 self-start sm:self-auto" href="/account/me">
          ← Account
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="card-solid p-10 text-center">
          <div className="font-display text-2xl mb-2">No orders yet.</div>
          <p className="text-[color:var(--muted)] mb-5">
            Try on a few looks — add the ones that land to your bag.
          </p>
          <Link className="btn-primary" href="/try-on">Style me</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((order) => (
            <Link
              className="card-solid p-4 flex items-start justify-between gap-4 product-card"
              href={`/account/orders/${order.order_id}`}
              key={order.order_id}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-display text-lg">{order.order_number}</span>
                  <span
                    className="pill pill-soft text-[10px] capitalize"
                  >
                    {order.status.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="text-[12px] text-[color:var(--muted)]">
                  {new Date(order.created_at).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                  })}
                  {" · "}
                  {order.lines.length} item{order.lines.length === 1 ? "" : "s"}
                </div>
              </div>
              <div className="font-display text-lg shrink-0">
                {formatMoney(order.totals.total_amount, order.totals.currency)}
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
