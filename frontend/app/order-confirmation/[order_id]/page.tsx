import Image from "next/image";
import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { CustomerOrderActions } from "@/components/customer-order-actions";
import { TrackingCard } from "@/components/tracking-card";
import { formatMoney } from "@/lib/api";
import { serverApi } from "@/lib/server-api";
import type { OrderPublic, ProductDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OrderConfirmationPage({
  params,
  searchParams,
}: {
  params: Promise<{ order_id: string }>;
  searchParams: Promise<{ token?: string }>;
}) {
  const { order_id } = await params;
  const { token } = await searchParams;

  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  let order: OrderPublic | undefined;
  let authBlocked = false;
  try {
    order = await serverApi.getOrder(order_id, {
      token,
      cookie: cookieHeader,
    });
  } catch (err) {
    const status = (err as { status?: number } | null)?.status;
    if (status === 401 || status === 403) {
      authBlocked = true;
    } else {
      notFound();
    }
  }

  if (authBlocked) {
    return <AuthBlockedView orderId={order_id} />;
  }
  if (!order) notFound();

  // Pull product images for each catalog line and AI-render image URLs
  // for each custom-design line. All requests fan out in parallel so the
  // items list can render with real thumbnails in one server round-trip.
  // Both fetches are best-effort — anything that 404s just renders blank.
  const uniqueProductIds = Array.from(
    new Set(
      order.lines
        .map((l) => l.product_id)
        .filter((id): id is string => typeof id === "string" && id.length > 0),
    ),
  );
  const uniqueDesignIds = Array.from(
    new Set(
      order.lines
        .filter((l) => l.kind === "custom_design")
        .map((l) => l.design_session_id)
        .filter((id): id is string => typeof id === "string" && id.length > 0),
    ),
  );
  const [productResults, designResults] = await Promise.all([
    Promise.allSettled(
      uniqueProductIds.map((pid) => serverApi.getProduct(pid)),
    ),
    Promise.allSettled(
      uniqueDesignIds.map((did) => serverApi.getDesignSession(did)),
    ),
  ]);
  const productById: Record<string, ProductDetail> = {};
  productResults.forEach((r, i) => {
    if (r.status === "fulfilled") {
      productById[uniqueProductIds[i]] = r.value;
    }
  });
  const designImageById: Record<string, string> = {};
  designResults.forEach((r, i) => {
    if (r.status === "fulfilled" && r.value?.image_url) {
      designImageById[uniqueDesignIds[i]] = r.value.image_url;
    }
  });

  const firstName =
    (order.shipping_address.name ?? "").split(" ")[0] || "there";
  const currency = order.totals.currency;
  const isShipped =
    order.status === "shipped" || order.status === "delivered";

  return (
    <section className="max-w-[960px] mx-auto px-5 py-10 sm:py-14 space-y-6">
      {/* Celebratory header */}
      <header className="card-solid p-7 sm:p-9 text-center">
        <div
          aria-hidden
          className="mx-auto mb-4 inline-flex items-center justify-center h-14 w-14 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)]"
        >
          <svg fill="none" height="26" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" width="26">
            <path d="M5 12.5 10 17 20 7" />
          </svg>
        </div>
        <h1 className="font-display text-3xl sm:text-4xl tracking-tight">
          Thank you, {firstName}.
        </h1>
        <p className="text-[color:var(--muted)] mt-2 text-[14px]">
          Order{" "}
          <span className="font-medium text-[color:var(--ink)]">
            {order.order_number}
          </span>{" "}
          ·{" "}
          {order.guest_email ? (
            <>
              confirmation sent to{" "}
              <a
                className="text-[color:var(--ink-soft)] hover:underline break-all"
                href={`mailto:${order.guest_email}`}
              >
                {order.guest_email}
              </a>
            </>
          ) : (
            <>your receipt is in your account</>
          )}
        </p>

        {/* Three-step "what's next" rail */}
        <ol className="mt-7 grid grid-cols-3 gap-2 text-left max-w-xl mx-auto">
          <NextStep
            done
            label="Order placed"
            sub={new Date(order.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          />
          <NextStep
            done={isShipped}
            current={order.status === "paid" || order.status === "packed"}
            label="On its way"
            sub={isShipped ? "Tracked" : "Within 1–3 business days"}
          />
          <NextStep
            done={order.status === "delivered"}
            current={order.status === "shipped"}
            label="Delivered"
            sub={
              order.status === "delivered"
                ? "Enjoy!"
                : "Updates by email"
            }
          />
        </ol>
      </header>

      {/* Items + summary */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
        <div className="card-solid p-5 sm:p-6">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
            What you bought · {order.lines.length}{" "}
            {order.lines.length === 1 ? "item" : "items"}
          </div>
          <ul className="divide-y divide-[color:var(--line)]">
            {order.lines.map((line, i) => {
              const isCustom = line.kind === "custom_design";
              const product = line.product_id
                ? productById[line.product_id]
                : undefined;
              const imageUrl =
                (isCustom && line.design_session_id
                  ? designImageById[line.design_session_id]
                  : null) ??
                product?.primary_image_url ??
                product?.media_urls?.[0] ??
                null;
              return (
                <li
                  className="py-3 first:pt-0 last:pb-0 flex gap-4 items-stretch"
                  key={line.line_id ?? `${line.variant_id ?? "x"}-${i}`}
                >
                  <div className="relative h-20 w-16 sm:h-24 sm:w-[72px] rounded-md overflow-hidden bg-[color:var(--ivory)] border border-[color:var(--line)] shrink-0">
                    {imageUrl ? (
                      <Image
                        alt={line.title_snapshot}
                        className="object-cover"
                        fill
                        sizes="80px"
                        src={imageUrl}
                      />
                    ) : null}
                  </div>
                  <div className="flex-1 min-w-0 flex flex-col">
                    {isCustom ? (
                      <div className="font-display text-[15px] sm:text-base">
                        {line.title_snapshot}
                      </div>
                    ) : (
                      <Link
                        className="font-display text-[15px] sm:text-base hover:underline"
                        href={`/product/${product?.slug ?? line.product_id}`}
                      >
                        {line.title_snapshot}
                      </Link>
                    )}
                    <div className="text-[12px] text-[color:var(--muted)] mt-0.5">
                      {isCustom
                        ? `Made-to-order · × ${line.quantity}`
                        : [line.size, line.color, `× ${line.quantity}`]
                            .filter(Boolean)
                            .join(" · ")}
                    </div>
                  </div>
                  <div className="text-right shrink-0 tabular-nums">
                    <div className="text-[14px]">
                      {formatMoney(line.line_total_amount, currency)}
                    </div>
                    {line.quantity > 1 ? (
                      <div className="text-[11px] text-[color:var(--muted)]">
                        {formatMoney(line.unit_price_amount, currency)} ea
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="mt-5 pt-5 border-t border-[color:var(--line)] space-y-1.5 text-[13px] tabular-nums">
            <Row
              label="Subtotal"
              value={formatMoney(order.totals.subtotal_amount, currency)}
            />
            <Row
              label="Shipping"
              value={formatMoney(order.totals.shipping_amount, currency)}
            />
            <Row
              label="Tax"
              value={formatMoney(order.totals.tax_amount, currency)}
            />
            {order.totals.discount_amount > 0 ? (
              <Row
                label="Discount"
                value={`−${formatMoney(order.totals.discount_amount, currency)}`}
              />
            ) : null}
            <div className="flex justify-between text-[15px] font-medium pt-2 mt-1 border-t border-[color:var(--line)]">
              <span>Total</span>
              <span>{formatMoney(order.totals.total_amount, currency)}</span>
            </div>
          </div>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Delivering to
            </div>
            <div className="text-[13px] leading-relaxed">
              <div className="font-medium">{order.shipping_address.name}</div>
              <div className="text-[color:var(--ink-soft)]">
                {order.shipping_address.line1}
                {order.shipping_address.line2
                  ? `, ${order.shipping_address.line2}`
                  : ""}
              </div>
              <div className="text-[color:var(--ink-soft)]">
                {[
                  order.shipping_address.city,
                  order.shipping_address.region,
                  order.shipping_address.postal_code,
                ]
                  .filter(Boolean)
                  .join(", ")}
              </div>
              <div className="text-[color:var(--ink-soft)]">
                {order.shipping_address.country}
              </div>
            </div>
          </div>

          <TrackingCard order={order} />

          {/* Cancel / Return — only renders when actionable */}
          <CustomerOrderActions order={order} />

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Payment
            </div>
            <div className="text-[13px]">
              <div className="capitalize">
                {order.payment.payment_status.replace(/_/g, " ")} via Stripe
              </div>
              {order.payment.paid_at ? (
                <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                  {new Date(order.payment.paid_at).toLocaleString()}
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      </div>

      {/* Guest-only: claim banner */}
      {!order.customer_id && token ? (
        <div className="card-solid p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
              Save this order
            </div>
            <div className="font-display text-xl sm:text-2xl mb-1">
              Create an account to keep this on file.
            </div>
            <p className="text-[13px] text-[color:var(--muted)] max-w-md leading-relaxed">
              Sign up with the same email to track this order, save your
              Fitting Room, and skip checkout next time. The link is valid
              for 7 days.
            </p>
          </div>
          <Link
            className="btn-primary shrink-0 inline-flex items-center"
            href={`/auth/signup?claim=${encodeURIComponent(token)}&order=${order.order_id}`}
          >
            Claim this order
          </Link>
        </div>
      ) : null}

      {/* Footer CTAs */}
      <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
        <Link
          className="btn-secondary text-sm inline-flex"
          href="/catalog"
        >
          Keep shopping
        </Link>
        <Link className="btn-ghost text-sm underline underline-offset-4" href="/try-on">
          Try on another look
        </Link>
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-[color:var(--ink-soft)]">
      <span className="text-[color:var(--muted)]">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function NextStep({
  label,
  sub,
  done,
  current,
}: {
  label: string;
  sub: string;
  done?: boolean;
  current?: boolean;
}) {
  return (
    <li className="flex gap-2 items-start min-w-0">
      <span
        aria-hidden
        className={
          "inline-flex items-center justify-center h-5 w-5 rounded-full text-[10px] shrink-0 mt-0.5 " +
          (done
            ? "bg-[color:var(--ink)] text-[color:var(--paper)]"
            : current
              ? "bg-white text-[color:var(--ink)] border border-[color:var(--ink)]"
              : "bg-[color:var(--ivory)] text-[color:var(--muted)] border border-[color:var(--line)]")
        }
      >
        {done ? "✓" : current ? "•" : ""}
      </span>
      <div className="min-w-0">
        <div
          className={
            "text-[12px] " +
            (current || done
              ? "font-medium text-[color:var(--ink)]"
              : "text-[color:var(--muted)]")
          }
        >
          {label}
        </div>
        <div className="text-[11px] text-[color:var(--muted)] truncate">{sub}</div>
      </div>
    </li>
  );
}

function AuthBlockedView({ orderId }: { orderId: string }) {
  return (
    <section className="max-w-[640px] mx-auto px-5 py-16">
      <div className="card-solid p-8">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          Confirmation
        </div>
        <h1 className="font-display text-3xl mb-2">
          Open your order from the email link.
        </h1>
        <p className="text-[color:var(--muted)] text-sm mb-5 leading-relaxed">
          Your purchase is safe — we just need to verify it&apos;s yours
          before showing the details. The confirmation email we sent
          contains a one-click link that signs you in to this order.
        </p>
        <p className="text-[color:var(--muted)] text-[12px] mb-6">
          Order reference: <span className="font-mono break-all">{orderId}</span>
        </p>
        <div className="space-y-3">
          <Link
            className="btn-primary w-full inline-flex justify-center"
            href="/auth/login"
          >
            Sign in to your account
          </Link>
          <Link
            className="btn-secondary w-full inline-flex justify-center"
            href="/"
          >
            Back to Try-On
          </Link>
        </div>
        <p className="text-[11px] text-[color:var(--muted)] mt-6 leading-relaxed">
          Can&apos;t find the email? Check your spam folder, or contact
          support with the order reference above.
        </p>
      </div>
    </section>
  );
}
