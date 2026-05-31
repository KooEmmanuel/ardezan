import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import {
  adminApi,
  type AdminAIAnalytics,
  type AdminAISettings,
  type AdminAnalyticsOverview,
  type AdminDashboardMetrics,
} from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminDashboardPage() {
  const [metrics, aiSettings, aiAnalytics, analyticsOverview, recentOrders] =
    await Promise.all([
      adminApi.getDashboardMetrics(),
      adminApi.getAISettings(),
      adminApi.getAIAnalytics(),
      adminApi.getAnalyticsOverview(),
      adminApi.listOrders({ limit: 6 }),
    ]);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Store dashboard"
        subtitle="Real-time view of revenue, fulfilment queue, and catalog health."
        actions={
          <Link className="btn-secondary text-sm" href="/admin/products/new">
            + New product
          </Link>
        }
      />

      {metrics.kind === "ok" ? (
        <KpiRow m={metrics.data} />
      ) : (
        <div className="card-solid p-5 text-sm text-[color:var(--muted)]">
          Couldn’t load dashboard metrics.
        </div>
      )}

      {metrics.kind === "ok" && metrics.data.revenue_sparkline.length > 0 ? (
        <SparklineCard
          currency={metrics.data.currency}
          data={metrics.data.revenue_sparkline}
          weekTotal={metrics.data.revenue_week_amount}
        />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 card-solid p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                Recent activity
              </div>
              <h2 className="font-display text-xl mt-0.5">Recent orders</h2>
            </div>
            <Link className="text-xs underline underline-offset-2" href="/admin/orders">
              View all →
            </Link>
          </div>
          {recentOrders.kind === "ok" ? (
            recentOrders.data.items.length === 0 ? (
              <p className="text-sm text-[color:var(--muted)] py-6">
                No orders yet. Once payments confirm, they’ll show up here.
              </p>
            ) : (
              <table className="w-full text-[13px]">
                <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                  <tr className="text-left">
                    <th className="pb-2 font-normal">Order</th>
                    <th className="font-normal">Customer</th>
                    <th className="font-normal">Status</th>
                    <th className="text-right font-normal">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {recentOrders.data.items.map((o) => (
                    <tr className="border-t border-[color:var(--line)]" key={o.order_id}>
                      <td className="py-2.5 font-mono text-[11px]">
                        <Link className="underline underline-offset-2" href={`/admin/orders/${o.order_id}`}>
                          {o.order_number}
                        </Link>
                      </td>
                      <td className="truncate max-w-[200px]">
                        {o.customer_id ? "Registered" : (o.guest_email ?? "Guest")}
                      </td>
                      <td>
                        <span className="pill pill-soft text-[10px] capitalize">
                          {o.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="text-right tabular-nums">
                        {formatMoney(o.totals.total_amount, o.totals.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <p className="text-sm text-[color:var(--muted)]">Couldn’t load orders.</p>
          )}
        </div>

        <div className="space-y-5">
          <div className="card-solid p-5">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                AI controls
              </div>
              <Link className="text-xs underline underline-offset-2" href="/admin/ai">
                Open →
              </Link>
            </div>
            {aiSettings.kind === "ok" ? (
              <AiBudgetCompact
                analytics={aiAnalytics.kind === "ok" ? aiAnalytics.data : null}
                settings={aiSettings.data}
              />
            ) : (
              <div className="text-sm text-[color:var(--muted)]">Unavailable.</div>
            )}
          </div>

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Quick links
            </div>
            <ul className="space-y-1.5 text-[13px]">
              <li>
                <Link className="hover:underline" href="/admin/products?status=draft">
                  Drafts →
                </Link>
              </li>
              <li>
                <Link className="hover:underline" href="/admin/inventory?health=low">
                  Low stock variants →
                </Link>
              </li>
              <li>
                <Link className="hover:underline" href="/admin/orders?status=paid">
                  Orders awaiting fulfilment →
                </Link>
              </li>
              <li>
                <Link className="hover:underline" href="/admin/customers?sort=spend">
                  Top spenders →
                </Link>
              </li>
              <li>
                <Link className="hover:underline" href="/admin/audit">
                  Audit log →
                </Link>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <TopProductsCard overview={analyticsOverview} />
        <LowStockCard overview={analyticsOverview} />
      </div>
    </>
  );
}

function KpiRow({ m }: { m: AdminDashboardMetrics }) {
  const tiles: {
    label: string;
    value: string;
    foot: string;
    accent?: "warn" | "danger";
    href: string;
  }[] = [
    {
      label: "Revenue · 24h",
      value: formatMoney(m.revenue_today_amount, m.currency),
      foot: `${formatMoney(m.revenue_week_amount, m.currency)} this week`,
      href: "/admin/orders",
    },
    {
      label: "Orders · 24h",
      value: String(m.orders_today_count),
      foot: `${m.orders_week_count} in 7d · ${m.orders_pending_payment} pending pay`,
      href: "/admin/orders",
    },
    {
      label: "To fulfil",
      value: String(m.orders_pending_fulfillment),
      foot: m.refunds_pending_count
        ? `${m.refunds_pending_count} return req.`
        : "Paid + packed",
      accent: m.orders_pending_fulfillment > 0 ? "warn" : undefined,
      href: "/admin/orders?status=paid",
    },
    {
      label: "Low stock",
      value: String(m.low_stock_variant_count),
      foot: m.out_of_stock_variant_count
        ? `${m.out_of_stock_variant_count} out of stock`
        : "All variants healthy",
      accent:
        m.out_of_stock_variant_count > 0
          ? "danger"
          : m.low_stock_variant_count > 0
            ? "warn"
            : undefined,
      href: "/admin/inventory?health=low",
    },
    {
      label: "Live SKUs",
      value: String(m.active_products_count),
      foot: `${m.draft_products_count} draft`,
      href: "/admin/products?status=published",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {tiles.map((t) => (
        <Link
          className={
            "card-solid p-4 block hover:border-[color:var(--ink)] transition-colors " +
            (t.accent === "danger"
              ? "border-[#f0c2c2]"
              : t.accent === "warn"
                ? "border-[#f0d8a0]"
                : "")
          }
          href={t.href}
          key={t.label}
        >
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
            {t.label}
          </div>
          <div className="font-display text-[28px] leading-none mt-2 tabular-nums">
            {t.value}
          </div>
          <div className="text-[11px] text-[color:var(--muted)] mt-1.5">{t.foot}</div>
        </Link>
      ))}
    </div>
  );
}

function SparklineCard({
  data,
  currency,
  weekTotal,
}: {
  data: number[];
  currency: string;
  weekTotal: number;
}) {
  const max = Math.max(...data, 1);
  const w = 600;
  const h = 80;
  const pad = 4;
  const step = (w - pad * 2) / Math.max(data.length - 1, 1);
  const pts = data.map((v, i) => {
    const x = pad + i * step;
    const y = h - pad - (v / max) * (h - pad * 2);
    return `${x},${y}`;
  });
  const path = `M ${pts.join(" L ")}`;
  const area = `M ${pad},${h - pad} L ${pts.join(" L ")} L ${w - pad},${h - pad} Z`;
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(today.getDate() - data.length + 1);
  return (
    <div className="card-solid p-5">
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Revenue · 14 days
          </div>
          <div className="font-display text-2xl tabular-nums mt-1">
            {formatMoney(weekTotal, currency)}{" "}
            <span className="text-[color:var(--muted)] text-sm">last 7d</span>
          </div>
        </div>
        <div className="text-[11px] text-[color:var(--muted)] tabular-nums">
          {startDate.toLocaleDateString()} → {today.toLocaleDateString()}
        </div>
      </div>
      <svg
        aria-hidden
        className="w-full h-[80px]"
        preserveAspectRatio="none"
        viewBox={`0 0 ${w} ${h}`}
      >
        <path d={area} fill="rgba(0,0,0,0.04)" />
        <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        {data.map((v, i) => {
          const x = pad + i * step;
          const y = h - pad - (v / max) * (h - pad * 2);
          return (
            <circle
              cx={x}
              cy={y}
              fill={v > 0 ? "var(--ink)" : "var(--line)"}
              key={i}
              r="2"
            />
          );
        })}
      </svg>
    </div>
  );
}

function TopProductsCard({
  overview,
}: {
  overview:
    | { kind: "ok"; data: AdminAnalyticsOverview }
    | { kind: "unauth" }
    | { kind: "error"; status: number; message: string };
}) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        Best sellers
      </div>
      <h2 className="font-display text-xl mt-0.5 mb-3">Top products</h2>
      {overview.kind !== "ok" ? (
        <p className="text-sm text-[color:var(--muted)]">Couldn’t load.</p>
      ) : overview.data.top_products.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)] py-6 text-center">
          No sales yet. Top sellers appear once orders confirm.
        </p>
      ) : (
        <table className="w-full text-[13px]">
          <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            <tr className="text-left">
              <th className="pb-2 font-normal">Product</th>
              <th className="font-normal text-right">Sold</th>
              <th className="font-normal text-right">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {overview.data.top_products.slice(0, 6).map((p) => (
              <tr className="border-t border-[color:var(--line)]" key={p.product_id}>
                <td className="py-2.5">
                  <Link
                    className="hover:underline truncate block max-w-[260px]"
                    href={`/admin/products/${p.product_id}`}
                  >
                    {p.title}
                  </Link>
                </td>
                <td className="text-right tabular-nums">{p.quantity_sold}</td>
                <td className="text-right tabular-nums whitespace-nowrap">
                  {formatMoney(p.revenue_amount, overview.data.revenue_currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function LowStockCard({
  overview,
}: {
  overview:
    | { kind: "ok"; data: AdminAnalyticsOverview }
    | { kind: "unauth" }
    | { kind: "error"; status: number; message: string };
}) {
  return (
    <div className="card-solid p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Inventory health
          </div>
          <h2 className="font-display text-xl mt-0.5">Needs restocking</h2>
        </div>
        <Link className="text-xs underline underline-offset-2" href="/admin/inventory?health=low">
          View all →
        </Link>
      </div>
      {overview.kind !== "ok" ? (
        <p className="text-sm text-[color:var(--muted)]">Couldn’t load.</p>
      ) : overview.data.low_stock_variants.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)] py-6 text-center">
          🎉 All variants are healthy.
        </p>
      ) : (
        <table className="w-full text-[13px]">
          <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            <tr className="text-left">
              <th className="pb-2 font-normal">SKU</th>
              <th className="font-normal">Variant</th>
              <th className="font-normal text-right">Stock / Threshold</th>
            </tr>
          </thead>
          <tbody>
            {overview.data.low_stock_variants.slice(0, 6).map((v) => (
              <tr className="border-t border-[color:var(--line)]" key={v.variant_id}>
                <td className="py-2.5 font-mono text-[11px]">{v.sku}</td>
                <td>
                  <Link
                    className="hover:underline"
                    href={`/admin/products/${v.product_id}`}
                  >
                    {v.color} · {v.size}
                  </Link>
                </td>
                <td className="text-right tabular-nums">
                  <span
                    className={
                      v.available_for_sale === 0
                        ? "text-[#8d1717]"
                        : "text-[#8a5a00]"
                    }
                  >
                    {v.available_for_sale}
                  </span>{" "}
                  <span className="text-[color:var(--muted)]">
                    / {v.low_stock_threshold}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AiBudgetCompact({
  settings,
  analytics,
}: {
  settings: AdminAISettings;
  analytics: AdminAIAnalytics | null;
}) {
  const used = analytics?.today_spend_amount ?? 0;
  const ceiling = settings.daily_spend_ceiling_amount;
  const pct = ceiling > 0 ? Math.min(100, Math.round((used / ceiling) * 100)) : 0;
  return (
    <>
      <div className="flex items-baseline justify-between">
        <div className="font-display text-2xl tabular-nums">
          {formatMoney(used, settings.currency)}
        </div>
        <div className="text-[11px] text-[color:var(--muted)] tabular-nums">
          / {formatMoney(ceiling, settings.currency)}
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-[color:var(--ivory)] mt-2 overflow-hidden">
        <div
          className="h-full transition-all"
          style={{
            width: `${pct}%`,
            background: pct >= 90 ? "#8d1717" : "var(--ink)",
          }}
        />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <div className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Switch
          </div>
          <div>{settings.kill_switch_enabled ? "ON" : "Off"}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Anon/d
          </div>
          <div className="tabular-nums">{settings.anonymous_daily_limit}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Memb/wk
          </div>
          <div className="tabular-nums">{settings.registered_weekly_limit}</div>
        </div>
      </div>
    </>
  );
}
