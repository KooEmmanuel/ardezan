// Customer activity hub.
//
// "Fitting Room" is the marketing name; under the hood it now bundles
// three feeds — Custom Designs, Try-On sessions, and Recent Orders —
// because the customer expects everything they've done with the brand
// to live behind one click on the avatar.
//
// We fetch all four reads (me + designs + try-ons + orders) in
// parallel server-side so the page renders in one round-trip.

import { cookies } from "next/headers";
import Image from "next/image";
import Link from "next/link";

import { formatMoney } from "@/lib/api";
import { serverApi } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type FittingRoomItem = {
  try_on_session_id: string;
  source: string;
  status: string;
  created_at: string;
  result_card_count: number;
  representative_image_url: string | null;
  representative_outfit_name: string | null;
};

type FittingRoomList = {
  items: FittingRoomItem[];
  total: number;
  limit: number;
  offset: number;
};

async function fetchFittingRoom(
  cookieHeader: string,
): Promise<
  FittingRoomList | { unauthenticated: true } | { unavailable: true }
> {
  // SSR runs in Vercel's Node runtime — Node's fetch needs an absolute
  // URL. ``NEXT_PUBLIC_API_BASE_URL`` is empty in prod (browser uses
  // relative URLs through the Vercel rewrite), so we go straight to
  // Railway via ``BACKEND_PROXY_URL``. See ``lib/server-api.ts`` for
  // the same fallback shape.
  const base =
    process.env.BACKEND_PROXY_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://localhost:8000";
  try {
    const r = await fetch(`${base}/api/v1/account/fitting-room?limit=24`, {
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
      cache: "no-store",
    });
    if (r.status === 401) return { unauthenticated: true };
    if (!r.ok) return { unavailable: true };
    return (await r.json()) as FittingRoomList;
  } catch {
    return { unavailable: true };
  }
}

export default async function FittingRoomPage() {
  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  // Parallelise — none of these depend on each other.
  const [tryOnResult, designsResult, ordersResult, meResult] = await Promise.all([
    fetchFittingRoom(cookieHeader),
    serverApi.listMyDesigns(cookieHeader, { limit: 12 }).catch(() => null),
    serverApi.listMyOrders(cookieHeader, { limit: 6 }).catch(() => null),
    serverApi.getMe(cookieHeader).catch(() => null),
  ]);

  if ("unavailable" in tryOnResult) {
    return (
      <section className="max-w-[600px] mx-auto px-5 py-12">
        <div className="card-solid p-6 text-center">
          <div className="font-display text-2xl mb-2">
            Your activity is taking a nap.
          </div>
          <p className="text-[color:var(--muted)] mb-4">
            The server may be restarting — try again in a moment.
          </p>
          <Link className="btn-primary" href="/account/fitting-room">
            Retry
          </Link>
        </div>
      </section>
    );
  }

  if ("unauthenticated" in tryOnResult) {
    return (
      <section className="ai-canvas">
        <div className="max-w-[640px] mx-auto px-5 py-16 text-center">
          <div className="glass-strong p-8">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-2">
              Your account
            </div>
            <h1 className="font-display text-4xl mb-3">
              Sign in to see your activity.
            </h1>
            <p className="text-[color:var(--muted)] mb-5">
              Every try-on session, custom design, and order lives here.
            </p>
            <Link className="btn-primary" href="/auth/login">
              Sign in
            </Link>
            <Link className="btn-secondary ml-2" href="/auth/signup">
              Create account
            </Link>
          </div>
        </div>
      </section>
    );
  }

  const tryOns = tryOnResult.items;
  const designs = designsResult?.items ?? [];
  const orders = ordersResult?.items ?? [];

  const firstName =
    (meResult?.name ?? "").split(" ")[0] || meResult?.email?.split("@")[0] || null;

  return (
    <section className="ai-canvas">
      <div className="max-w-[1280px] mx-auto px-5 py-10">
        {/* Header + quick stats */}
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-1">
            Your account
          </div>
          <h1 className="font-display text-4xl">
            {firstName ? `Welcome back, ${firstName}.` : "Your activity"}
          </h1>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-8">
          <StatCard
            label="Custom designs"
            value={designsResult?.total ?? 0}
            href="#designs"
          />
          <StatCard
            label="Try-On sessions"
            value={tryOnResult.total}
            href="#tryons"
          />
          <StatCard
            label="Orders"
            value={ordersResult?.total ?? 0}
            href="/account/orders"
          />
        </div>

        {/* ── Custom designs ───────────────────────────────────── */}
        <Section
          actionHref="/try-on/design"
          actionLabel="Design something custom"
          eyebrow="Made for you"
          id="designs"
          subtitle={
            designs.length > 0
              ? `${designsResult?.total ?? designs.length} total`
              : null
          }
          title="Custom designs"
        >
          {designs.length === 0 ? (
            <EmptyTile
              cta="Try Design Me"
              ctaHref="/try-on/design"
              hint="Pick a fabric, describe the piece, get a render in seconds."
              title="No custom designs yet."
            />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {designs.map((d) => (
                <div
                  className="glass-strong overflow-hidden product-card"
                  key={d.design_session_id}
                >
                  <div className="ratio-45 relative bg-[color:var(--ivory)]">
                    {d.image_url ? (
                      <Image
                        alt={d.title}
                        className="object-cover"
                        fill
                        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
                        src={d.image_url}
                      />
                    ) : null}
                    <span className="absolute top-2 left-2 pill pill-ai">
                      Design Me
                    </span>
                    {d.status === "failed" ? (
                      <span className="absolute top-2 right-2 pill bg-[#fdecec] text-[#8d1717]">
                        Failed
                      </span>
                    ) : null}
                  </div>
                  <div className="p-3 bg-white/85 backdrop-blur-md">
                    <div className="font-display text-base leading-tight truncate">
                      {d.title}
                    </div>
                    <div className="text-[11px] text-[color:var(--muted)] mt-0.5 truncate">
                      {d.fabric_name} ·{" "}
                      {new Date(d.created_at).toLocaleDateString()}
                    </div>
                    <div className="text-[13px] font-medium mt-1.5">
                      {formatMoney(d.total_amount, d.currency)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ── Try-On sessions ──────────────────────────────────── */}
        <Section
          actionHref="/try-on"
          actionLabel="Start a new try-on"
          eyebrow="See it on you"
          id="tryons"
          subtitle={tryOns.length > 0 ? `${tryOnResult.total} total` : null}
          title="Try-On sessions"
        >
          {tryOns.length === 0 ? (
            <EmptyTile
              cta="Try it on"
              ctaHref="/try-on"
              hint="Upload one photo and we'll style ten looks on you."
              title="No try-ons yet."
            />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {tryOns.map((item) => (
                <Link
                  className="glass-strong overflow-hidden block product-card"
                  href={`/account/fitting-room/${item.try_on_session_id}`}
                  key={item.try_on_session_id}
                >
                  <div className="ratio-45 relative">
                    {item.representative_image_url ? (
                      <Image
                        alt={item.representative_outfit_name ?? "Try-on"}
                        className="object-cover"
                        fill
                        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
                        src={item.representative_image_url}
                      />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center text-[color:var(--muted)] text-xs shimmer" />
                    )}
                    <span className="absolute top-2 left-2 pill pill-ai">
                      AI preview
                    </span>
                  </div>
                  <div className="p-3 bg-white/85 backdrop-blur-md">
                    <div className="font-display text-base leading-tight truncate">
                      {item.representative_outfit_name ?? "Untitled session"}
                    </div>
                    <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                      {item.result_card_count} looks ·{" "}
                      {new Date(item.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Section>

        {/* ── Recent orders ────────────────────────────────────── */}
        <Section
          actionHref="/account/orders"
          actionLabel={
            orders.length > 0 ? "See all orders →" : "Browse the catalog"
          }
          eyebrow="What you bought"
          id="orders"
          subtitle={null}
          title="Recent orders"
        >
          {orders.length === 0 ? (
            <EmptyTile
              cta="Browse the catalog"
              ctaHref="/catalog"
              hint="When you check out, your orders show up here."
              title="No orders yet."
            />
          ) : (
            <div className="card-solid overflow-hidden">
              <ul className="divide-y divide-[color:var(--line)]">
                {orders.map((o) => (
                  <li className="px-4 py-3" key={o.order_id}>
                    <Link
                      className="flex items-center justify-between gap-4 hover:bg-[color:var(--ivory)] -mx-4 px-4 py-1 transition"
                      href={`/account/orders/${o.order_id}`}
                    >
                      <div className="min-w-0">
                        <div className="font-mono text-[12px] text-[color:var(--ink-soft)]">
                          {o.order_number}
                        </div>
                        <div className="text-[12px] text-[color:var(--muted)]">
                          {new Date(o.created_at).toLocaleDateString()} ·{" "}
                          {o.lines.length}{" "}
                          {o.lines.length === 1 ? "item" : "items"}
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-[10px] uppercase tracking-[0.08em] px-2 py-0.5 rounded-full border border-[color:var(--line)] text-[color:var(--ink-soft)]">
                          {o.status.replace(/_/g, " ")}
                        </span>
                        <span className="tabular-nums text-[14px]">
                          {formatMoney(
                            o.totals.total_amount,
                            o.totals.currency,
                          )}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      </div>
    </section>
  );
}

function StatCard({
  label,
  value,
  href,
}: {
  label: string;
  value: number;
  href: string;
}) {
  return (
    <Link
      className="card-solid p-4 hover:bg-[color:var(--ivory)] transition block"
      href={href}
    >
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        {label}
      </div>
      <div className="font-display text-3xl mt-1 tabular-nums">{value}</div>
    </Link>
  );
}

function Section({
  id,
  eyebrow,
  title,
  subtitle,
  actionLabel,
  actionHref,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  subtitle: string | null;
  actionLabel: string;
  actionHref: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-10 scroll-mt-24" id={id}>
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            {eyebrow}
          </div>
          <h2 className="font-display text-2xl leading-tight">{title}</h2>
          {subtitle ? (
            <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
              {subtitle}
            </div>
          ) : null}
        </div>
        <Link
          className="btn-ghost underline underline-offset-4 text-sm"
          href={actionHref}
        >
          {actionLabel}
        </Link>
      </div>
      {children}
    </section>
  );
}

function EmptyTile({
  title,
  hint,
  cta,
  ctaHref,
}: {
  title: string;
  hint: string;
  cta: string;
  ctaHref: string;
}) {
  return (
    <div className="card-solid p-6 text-center">
      <div className="font-display text-xl mb-1">{title}</div>
      <p className="text-[color:var(--muted)] text-sm mb-3">{hint}</p>
      <Link className="btn-primary" href={ctaHref}>
        {cta}
      </Link>
    </div>
  );
}
