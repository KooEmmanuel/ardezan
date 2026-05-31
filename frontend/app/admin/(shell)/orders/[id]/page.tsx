import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminOrderActions } from "@/components/admin-order-actions";
import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi, type AdminOrderTryOnLook } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

// The four stages every fulfilled order goes through. Cancelled / refunded
// orders short-circuit the timeline and render as a single "ended" pill.
const TIMELINE_STAGES = ["paid", "packed", "shipped", "delivered"] as const;
type TimelineStage = (typeof TIMELINE_STAGES)[number];

function statusPillClasses(status: string): string {
  switch (status) {
    case "paid":
    case "packed":
      return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
    case "shipped":
      return "bg-[#eaf1fb] text-[#1f4b8d] border-[#c2d6ef]";
    case "delivered":
      return "bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]";
    case "pending_payment":
      return "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]";
    case "cancelled":
    case "refunded":
    case "partially_refunded":
      return "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]";
    default:
      return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
  }
}

export default async function AdminOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [result, tryOnResult, customResult] = await Promise.all([
    adminApi.getOrder(id),
    adminApi.getOrderTryOns(id),
    adminApi.getOrderCustomDesigns(id),
  ]);
  if (result.kind === "unauth") return null;
  if (result.kind === "error") notFound();

  const order = result.data;
  const currency = order.totals.currency;
  const looks =
    tryOnResult.kind === "ok" ? tryOnResult.data.looks : [];
  const customDesigns =
    customResult.kind === "ok" ? customResult.data.items : [];

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)]">
        <Link className="underline underline-offset-2" href="/admin/orders">
          Orders
        </Link>
        <span aria-hidden>›</span>
        <span className="font-mono">{order.order_number}</span>
      </nav>

      <PageHeader
        eyebrow="Operations"
        title={order.order_number}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span
              className={
                "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border " +
                statusPillClasses(order.status)
              }
            >
              {order.status.replace(/_/g, " ")}
            </span>
            <span className="text-[color:var(--muted)]">·</span>
            <span>{new Date(order.created_at).toLocaleString()}</span>
          </span>
        }
        actions={
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
              Order total
            </div>
            <div className="font-display text-2xl tabular-nums">
              {formatMoney(order.totals.total_amount, currency)}
            </div>
          </div>
        }
      />

      <StatusTimeline status={order.status} />

      <AdminOrderActions order={order} />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-5">
        <div className="card-solid p-5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
            Items · {order.lines.length}
          </div>
          <ul className="divide-y divide-[color:var(--line)]">
            {order.lines.map((line, i) => {
              const isCustom = line.kind === "custom_design";
              return (
              <li
                className="py-3 first:pt-0 last:pb-0 flex items-start justify-between gap-4"
                key={line.line_id ?? `${line.variant_id ?? "x"}-${i}`}
              >
                <div className="flex-1 min-w-0">
                  {isCustom ? (
                    <div className="font-display text-[15px] flex items-center gap-2">
                      {line.title_snapshot}
                      <span className="inline-flex items-center px-1.5 py-0 rounded text-[9.5px] tracking-[0.06em] uppercase border bg-[#f3eff8] text-[#5a3c8d] border-[#d4c5ec]">
                        Custom
                      </span>
                    </div>
                  ) : (
                    <Link
                      className="font-display text-[15px] hover:underline"
                      href={`/admin/products/${line.product_id}`}
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
                <div className="text-right shrink-0">
                  <div className="text-[14px] tabular-nums">
                    {formatMoney(line.line_total_amount, currency)}
                  </div>
                  <div className="text-[11px] text-[color:var(--muted)] tabular-nums">
                    {formatMoney(line.unit_price_amount, currency)} ea
                  </div>
                </div>
              </li>
              );
            })}
          </ul>

          {/* Totals block sits with the items so they read together. */}
          <div className="mt-4 pt-4 border-t border-[color:var(--line)] space-y-1.5 text-[13px]">
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
            <div className="flex justify-between text-[15px] font-medium pt-2 mt-1 border-t border-[color:var(--line)] tabular-nums">
              <span>Total</span>
              <span>{formatMoney(order.totals.total_amount, currency)}</span>
            </div>
          </div>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Customer
            </div>
            {order.customer_id ? (
              <div className="text-[13px]">
                <div>Registered customer</div>
                <Link
                  className="text-[11px] font-mono text-[color:var(--muted)] hover:underline break-all"
                  href={`/admin/customers/${order.customer_id}`}
                >
                  {order.customer_id}
                </Link>
              </div>
            ) : (
              <div className="text-[13px]">
                <div className="text-[11px] uppercase tracking-[0.06em] text-[color:var(--muted)]">
                  Guest
                </div>
                <a
                  className="hover:underline break-all"
                  href={`mailto:${order.guest_email ?? ""}`}
                >
                  {order.guest_email ?? "no email"}
                </a>
              </div>
            )}
          </div>

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Shipping to
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

          {order.fulfillment.tracking_number ? (
            <div className="card-solid p-5">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
                Tracking
              </div>
              <div className="text-[13px]">
                <div>
                  <span className="text-[color:var(--muted)]">Carrier · </span>
                  {(order.fulfillment as { carrier?: string }).carrier ?? "—"}
                </div>
                <div className="font-mono text-[12px] mt-1 break-all">
                  {order.fulfillment.tracking_number}
                </div>
                {order.fulfillment.shipped_at ? (
                  <div className="text-[11px] text-[color:var(--muted)] mt-1">
                    Shipped{" "}
                    {new Date(order.fulfillment.shipped_at).toLocaleString()}
                  </div>
                ) : null}
                {order.fulfillment.delivered_at ? (
                  <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                    Delivered{" "}
                    {new Date(order.fulfillment.delivered_at).toLocaleString()}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="card-solid p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
              Payment
            </div>
            <div className="text-[13px]">
              <div className="capitalize">
                {order.payment.payment_status.replace(/_/g, " ")}
              </div>
              {order.payment.stripe_payment_intent_id ? (
                <div className="text-[10px] font-mono text-[color:var(--muted)] mt-1 break-all">
                  {order.payment.stripe_payment_intent_id}
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      </div>

      {customDesigns.length > 0 ? (
        <CustomDesigns designs={customDesigns} />
      ) : null}
      {looks.length > 0 ? <TryOnLooks looks={looks} currency={currency} /> : null}
    </>
  );
}

type CustomDesign = {
  line_id: string;
  design_session_id: string | null;
  status: string;
  title_snapshot: string | null;
  fabric?: {
    fabric_id: string;
    name: string;
    color_family: string;
    cost_per_yard_amount: number;
    weight: string;
    finish: string | null;
  };
  piece_type?: string;
  complexity?: string;
  brief?: string;
  fit_note?: string | null;
  estimate?: {
    yardage: number;
    material_amount: number;
    tailoring_amount: number;
    total_amount: number;
    currency: string;
  };
  image_url: string | null;
  unit_price_amount?: number;
};

function CustomDesigns({ designs }: { designs: CustomDesign[] }) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        Custom designs · {designs.length}
      </div>
      <h3 className="font-display text-xl mb-4">Tailor brief</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {designs.map((d) => (
          <div
            className="rounded-lg border p-3 flex gap-3"
            key={d.line_id}
            style={{ borderColor: "var(--line)" }}
          >
            <div className="relative w-28 h-36 sm:w-32 sm:h-40 rounded-md overflow-hidden bg-[color:var(--ivory)] border border-[color:var(--line)] shrink-0">
              {d.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  alt={d.title_snapshot ?? "Custom design"}
                  className="w-full h-full object-cover"
                  src={d.image_url}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-[10px] text-[color:var(--muted)] p-2 text-center">
                  Render unavailable
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-display text-base leading-tight">
                {d.title_snapshot ?? "Custom design"}
              </div>
              <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                {[
                  d.fabric?.name,
                  d.fabric?.weight,
                  d.fabric?.finish,
                  d.complexity,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              {d.brief ? (
                <p className="text-[12px] mt-2 leading-snug">
                  <span className="font-medium">Brief:</span> {d.brief}
                </p>
              ) : null}
              {d.fit_note ? (
                <p className="text-[12px] mt-1 leading-snug">
                  <span className="font-medium">Fit:</span> {d.fit_note}
                </p>
              ) : null}
              {d.estimate ? (
                <div className="mt-2 text-[11px] text-[color:var(--muted)] tabular-nums">
                  {d.estimate.yardage} yd ·{" "}
                  {formatMoney(d.estimate.material_amount, d.estimate.currency)}{" "}
                  fabric ·{" "}
                  {formatMoney(d.estimate.tailoring_amount, d.estimate.currency)}{" "}
                  tailoring
                </div>
              ) : null}
              {d.design_session_id ? (
                <div className="mt-1 text-[10px] text-[color:var(--muted)] font-mono">
                  {d.design_session_id}
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TryOnLooks({
  looks,
  currency,
}: {
  looks: AdminOrderTryOnLook[];
  currency: string;
}) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        AI try-on · {looks.length}
      </div>
      <p className="text-[12px] text-[color:var(--muted)] mb-4 max-w-prose">
        These lines were ordered from a try-on. Use the generated look to confirm
        you&apos;re packing the exact garments the customer saw.
      </p>
      <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {looks.map((look) => (
          <li
            className="rounded-lg border border-[color:var(--line)] overflow-hidden flex flex-col"
            key={look.line_id}
          >
            <div className="flex gap-2 p-2 bg-[color:var(--ivory)]">
              <LookImage
                alt={`Generated look for ${look.title_snapshot}`}
                emptyLabel={
                  look.images_available ? "no look image" : "expired"
                }
                src={look.generated_look_image_url}
                tall
              />
              <LookImage
                alt="Customer source photo"
                emptyLabel="no photo"
                src={look.source_photo_url}
              />
            </div>
            <div className="p-3 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-display text-[14px] truncate">
                    {look.outfit_name ?? look.title_snapshot}
                  </div>
                  <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                    {[look.size, look.color, `× ${look.quantity}`]
                      .filter(Boolean)
                      .join(" · ")}
                    {" · "}
                    <span className="font-mono">{look.sku}</span>
                  </div>
                </div>
                {!look.images_available ? (
                  <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]">
                    purged
                  </span>
                ) : null}
              </div>

              {look.rationale ? (
                <p className="text-[12px] text-[color:var(--ink-soft)] mt-2 leading-relaxed">
                  {look.rationale}
                </p>
              ) : null}

              {look.items.length > 0 ? (
                <ul className="mt-3 space-y-1.5 border-t border-[color:var(--line)] pt-2.5">
                  {look.items.map((item) => (
                    <li
                      className="flex items-center justify-between gap-2 text-[12px]"
                      key={item.variant_id}
                    >
                      <span className="min-w-0 truncate">
                        {item.product_title ?? item.product_id}
                        <span className="text-[color:var(--muted)]">
                          {item.color ? ` · ${item.color}` : ""}
                          {item.selected_size ? ` · ${item.selected_size}` : ""}
                        </span>
                      </span>
                      {item.price_amount != null ? (
                        <span className="shrink-0 tabular-nums text-[color:var(--ink-soft)]">
                          {formatMoney(item.price_amount, currency)}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="mt-3 text-[10px] text-[color:var(--muted)]">
                Session{" "}
                <span className="font-mono break-all">
                  {look.try_on_session_id}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LookImage({
  src,
  alt,
  emptyLabel,
  tall = false,
}: {
  src: string | null;
  alt: string;
  emptyLabel: string;
  tall?: boolean;
}) {
  return (
    <div
      className={
        "relative rounded bg-[color:var(--paper)] border border-[color:var(--line)] overflow-hidden " +
        (tall ? "flex-[2] aspect-[3/4]" : "flex-1 aspect-[3/4]")
      }
    >
      {src ? (
        <Image alt={alt} className="object-cover" fill sizes="220px" src={src} />
      ) : (
        <div className="flex items-center justify-center h-full w-full text-[10px] text-[color:var(--muted)] text-center px-1">
          {emptyLabel}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-[color:var(--ink-soft)] tabular-nums">
      <span className="text-[color:var(--muted)]">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function StatusTimeline({ status }: { status: string }) {
  // Terminal non-fulfilled state — render a single pill instead of the
  // 4-stage rail, since the rest of the timeline never happens.
  if (
    status === "cancelled" ||
    status === "refunded" ||
    status === "partially_refunded"
  ) {
    return (
      <div className="card-solid p-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1.5">
          Status
        </div>
        <div
          className={
            "inline-flex items-center px-2.5 py-1 rounded-full text-[11px] uppercase tracking-[0.06em] border " +
            statusPillClasses(status)
          }
        >
          {status.replace(/_/g, " ")}
        </div>
      </div>
    );
  }

  const currentIdx = TIMELINE_STAGES.indexOf(status as TimelineStage);

  return (
    <div className="card-solid p-4">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
        Fulfillment timeline
      </div>
      <ol className="flex items-center justify-between gap-2">
        {TIMELINE_STAGES.map((stage, i) => {
          const done = i <= currentIdx;
          const current = i === currentIdx;
          return (
            <li
              className="flex-1 flex items-center gap-2 min-w-0 last:flex-initial"
              key={stage}
            >
              <div className="flex flex-col items-start gap-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className={
                      "inline-flex items-center justify-center h-5 w-5 rounded-full text-[10px] tabular-nums shrink-0 " +
                      (done
                        ? "bg-[color:var(--ink)] text-[color:var(--paper)]"
                        : "bg-[color:var(--ivory)] text-[color:var(--muted)] border border-[color:var(--line)]")
                    }
                  >
                    {done ? "✓" : i + 1}
                  </span>
                  <span
                    className={
                      "text-[12px] capitalize " +
                      (current
                        ? "font-medium text-[color:var(--ink)]"
                        : done
                          ? "text-[color:var(--ink-soft)]"
                          : "text-[color:var(--muted)]")
                    }
                  >
                    {stage}
                  </span>
                </div>
              </div>
              {i < TIMELINE_STAGES.length - 1 ? (
                <span
                  aria-hidden
                  className={
                    "flex-1 h-px min-w-[16px] " +
                    (done ? "bg-[color:var(--ink)]" : "bg-[color:var(--line)]")
                  }
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
