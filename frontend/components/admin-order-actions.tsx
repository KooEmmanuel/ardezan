"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { LabeledField, SelectField } from "@/components/form-fields";
import { Modal } from "@/components/modal";
import { useToast } from "@/components/toast";
import { API_BASE_URL, formatMoney } from "@/lib/api";
import type { OrderPublic } from "@/lib/types";

const CARRIERS = ["USPS", "FedEx", "UPS", "DHL", "Royal Mail", "Other"] as const;
const REFUND_REASONS = [
  { value: "requested_by_customer", label: "Requested by customer" },
  { value: "duplicate", label: "Duplicate" },
  { value: "fraudulent", label: "Fraudulent" },
] as const;

// All admin-side actions on a single order. Decides the right next step
// from the current status so the operator sees one obvious button to
// push, not three competing cards.

export function AdminOrderActions({ order }: { order: OrderPublic }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(order.status);

  const [carrier, setCarrier] = useState<string>(
    (order.fulfillment as { carrier?: string })?.carrier ?? "USPS",
  );
  const [trackingNumber, setTrackingNumber] = useState<string>(
    order.fulfillment.tracking_number ?? "",
  );

  const [refundOpen, setRefundOpen] = useState(false);
  const [refundAmount, setRefundAmount] = useState(order.totals.total_amount);
  const [refundReason, setRefundReason] = useState<typeof REFUND_REASONS[number]["value"]>(
    "requested_by_customer",
  );

  const [cancelOpen, setCancelOpen] = useState(false);

  const [receiveOpen, setReceiveOpen] = useState(false);
  const [receiveRefund, setReceiveRefund] = useState(order.totals.total_amount);
  const [receiveRestock, setReceiveRestock] = useState(true);
  const [receiveNote, setReceiveNote] = useState("");

  async function patchStatus(next: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/orders/${encodeURIComponent(order.order_id)}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ status: next, ...extra }),
        },
      );
      if (!r.ok) {
        let msg = `${r.status}`;
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        toast({ title: "Couldn't update status.", description: msg, kind: "error" });
        return;
      }
      setStatus(next as OrderPublic["status"]);
      toast({ title: `Order marked ${next.replace(/_/g, " ")}.`, kind: "success" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function markShipped() {
    if (!trackingNumber.trim()) {
      toast({ title: "Tracking number is required.", kind: "warning" });
      return;
    }
    await patchStatus("shipped", {
      carrier,
      tracking_number: trackingNumber.trim(),
    });
  }

  async function receiveReturn() {
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/orders/${encodeURIComponent(order.order_id)}/returns/receive`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": `return_${order.order_id}_${Date.now()}`,
          },
          credentials: "include",
          body: JSON.stringify({
            refund_amount: receiveRefund > 0 ? receiveRefund : null,
            refund_reason: "requested_by_customer",
            restock: receiveRestock,
            note: receiveNote.trim() || null,
          }),
        },
      );
      if (!r.ok) {
        let msg = `${r.status}`;
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        toast({ title: "Couldn't process the return.", description: msg, kind: "error" });
        return;
      }
      toast({
        title: "Return received.",
        description: receiveRefund > 0 ? "Refund issued." : "Marked returned.",
        kind: "success",
      });
      setReceiveOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function issueRefund() {
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/admin/orders/${encodeURIComponent(order.order_id)}/refunds`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": `refund_${order.order_id}_${refundAmount}_${Date.now()}`,
          },
          credentials: "include",
          body: JSON.stringify({ amount: refundAmount, reason: refundReason }),
        },
      );
      if (!r.ok) {
        let msg = `${r.status}`;
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        toast({ title: "Refund failed.", description: msg, kind: "error" });
        return;
      }
      toast({ title: "Refund issued.", kind: "success" });
      setRefundOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const currency = order.totals.currency;

  // Which kind of fulfillment panel to show
  // - paid     → "Mark as packed"
  // - packed   → carrier + tracking + "Save & mark shipped"
  // - shipped  → "Mark as delivered" + read-only tracking display
  // - delivered/cancelled/refunded → done; no transition card

  const canCancel = status === "paid" || status === "packed";
  const showRefund =
    status === "paid" ||
    status === "packed" ||
    status === "shipped" ||
    status === "delivered";

  return (
    <>
      <div className="space-y-4">
        {/* Next action — the single most important panel on the page */}
        {status === "paid" ? (
          <NextActionCard
            description="Pack the order, then mark it ready to ship."
            label="Next: pack the order"
          >
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => void patchStatus("packed")}
              type="button"
            >
              Mark as packed
            </button>
          </NextActionCard>
        ) : null}

        {status === "packed" ? (
          <NextActionCard
            description="Drop the package with the carrier, type their tracking number here, and we'll email the customer with the link."
            label="Next: ship + add tracking"
          >
            <div className="grid grid-cols-1 sm:grid-cols-[160px_1fr_auto] gap-2 items-end">
              <LabeledField label="Carrier">
                <SelectField
                  dim="md"
                  onChange={(e) => setCarrier(e.target.value)}
                  value={carrier}
                >
                  {CARRIERS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </SelectField>
              </LabeledField>
              <LabeledField label="Tracking number">
                <input
                  className="input h-9 text-[13px]"
                  onChange={(e) => setTrackingNumber(e.target.value)}
                  placeholder="e.g. 9400111899560000000000"
                  value={trackingNumber}
                />
              </LabeledField>
              <button
                className="btn-primary h-9 px-4 text-[13px]"
                disabled={busy || !trackingNumber.trim()}
                onClick={() => void markShipped()}
                type="button"
              >
                Save &amp; ship
              </button>
            </div>
          </NextActionCard>
        ) : null}

        {status === "shipped" ? (
          <NextActionCard
            description="Once the carrier confirms delivery, mark the order delivered. Customer gets a final email."
            label="Next: confirm delivery"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="text-[12px] text-[color:var(--muted)]">
                Shipped via{" "}
                <span className="font-medium text-[color:var(--ink)]">
                  {(order.fulfillment as { carrier?: string }).carrier ?? "carrier"}
                </span>{" "}
                · tracking{" "}
                <span className="font-mono">
                  {order.fulfillment.tracking_number}
                </span>
              </div>
              <button
                className="btn-primary"
                disabled={busy}
                onClick={() => void patchStatus("delivered")}
                type="button"
              >
                Mark as delivered
              </button>
            </div>
          </NextActionCard>
        ) : null}

        {status === "return_requested" ? (
          <NextActionCard
            description={
              order.return_request?.reason
                ? `Customer reason: "${order.return_request.reason}". Once the parcel arrives, mark received — that restocks the variants and issues the refund in one step.`
                : "Customer has asked for a return. Mark it received once the parcel lands; that restocks the variants and issues the refund in one step."
            }
            label="Next: process the return"
          >
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => setReceiveOpen(true)}
              type="button"
            >
              Mark received & refund…
            </button>
          </NextActionCard>
        ) : null}

        {status === "returned" ? (
          <NextActionCard
            description="Goods are back in the warehouse. Issue a refund if you haven't already."
            label="Next: issue refund (if needed)"
          >
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => setRefundOpen(true)}
              type="button"
            >
              Issue refund…
            </button>
          </NextActionCard>
        ) : null}

        {status === "delivered" ||
        status === "cancelled" ||
        status === "refunded" ||
        status === "partially_refunded" ? (
          <NextActionCard
            description={
              status === "delivered"
                ? "Customer has the goods. Issue a refund below if needed."
                : status === "cancelled"
                  ? "This order is cancelled. Inventory has been restocked."
                  : "Refunds have been issued for this order. No fulfillment actions remain."
            }
            label="No fulfillment action needed"
          />
        ) : null}

        {/* Secondary actions row */}
        {(canCancel || showRefund) ? (
          <div className="card-solid p-4 flex flex-wrap items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mr-1">
              Other actions
            </span>
            {showRefund ? (
              <button
                className="btn-secondary text-[12px] h-8"
                disabled={busy}
                onClick={() => setRefundOpen(true)}
                type="button"
              >
                Issue refund…
              </button>
            ) : null}
            {canCancel ? (
              <button
                className="btn-secondary text-[12px] h-8 ml-auto"
                disabled={busy}
                onClick={() => setCancelOpen(true)}
                type="button"
                style={{ color: "#8d1717", borderColor: "#f0c2c2" }}
              >
                Cancel order…
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Refund modal */}
      <Modal
        description={`Order ${order.order_number} · max ${formatMoney(order.totals.total_amount, currency)}`}
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={busy}
              onClick={() => setRefundOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={
                busy ||
                refundAmount <= 0 ||
                refundAmount > order.totals.total_amount
              }
              onClick={() => void issueRefund()}
              type="button"
            >
              {busy ? "Refunding…" : `Refund ${formatMoney(refundAmount, currency)}`}
            </button>
          </>
        }
        onClose={() => setRefundOpen(false)}
        open={refundOpen}
        size="sm"
        title="Issue refund"
      >
        <div className="space-y-3">
          <LabeledField
            hint={`In cents. Full order = ${order.totals.total_amount}.`}
            label="Amount"
          >
            <input
              className="input h-9 text-[13px] tabular-nums"
              max={order.totals.total_amount}
              min={1}
              onChange={(e) =>
                setRefundAmount(parseInt(e.target.value || "0", 10))
              }
              type="number"
              value={refundAmount}
            />
          </LabeledField>
          <LabeledField label="Reason">
            <SelectField
              dim="md"
              onChange={(e) =>
                setRefundReason(
                  e.target.value as typeof REFUND_REASONS[number]["value"],
                )
              }
              value={refundReason}
            >
              {REFUND_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </SelectField>
          </LabeledField>
          <p className="text-[11px] text-[color:var(--muted)] leading-relaxed">
            The refund hits the original card via Stripe. Inventory is not
            restocked by a refund alone — cancel the order if you also want
            the units returned to stock.
          </p>
        </div>
      </Modal>

      {/* Receive-return modal */}
      <Modal
        description={`Order ${order.order_number} · the parcel is back in your hands`}
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={busy}
              onClick={() => setReceiveOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={busy}
              onClick={() => void receiveReturn()}
              type="button"
            >
              {busy ? "Processing…" : "Mark received"}
            </button>
          </>
        }
        onClose={() => setReceiveOpen(false)}
        open={receiveOpen}
        size="md"
        title="Process return"
      >
        <div className="space-y-4">
          <LabeledField
            hint={`Order total ${formatMoney(order.totals.total_amount, currency)}. Set to 0 to skip the refund and just mark returned.`}
            label="Refund amount (cents)"
          >
            <input
              className="input h-9 text-[13px] tabular-nums"
              max={order.totals.total_amount}
              min={0}
              onChange={(e) =>
                setReceiveRefund(parseInt(e.target.value || "0", 10))
              }
              type="number"
              value={receiveRefund}
            />
          </LabeledField>

          <label className="flex items-start gap-2 text-[13px] cursor-pointer">
            <input
              checked={receiveRestock}
              className="mt-0.5 h-4 w-4 accent-[color:var(--ink)]"
              onChange={(e) => setReceiveRestock(e.target.checked)}
              type="checkbox"
            />
            <span>
              Restock returned items
              <span className="block text-[11px] text-[color:var(--muted)]">
                Increments stock_on_hand for the variants on this order and
                records inventory movements.
              </span>
            </span>
          </label>

          <LabeledField label="Internal note (optional)">
            <textarea
              className="input min-h-[60px] text-[13px]"
              maxLength={400}
              onChange={(e) => setReceiveNote(e.target.value)}
              placeholder="e.g. 'arrived clean, returned to inventory'"
              value={receiveNote}
            />
          </LabeledField>

          <p className="text-[11px] text-[color:var(--muted)] leading-relaxed">
            Refunds hit the original card via Stripe. Customer gets a
            confirmation email automatically.
          </p>
        </div>
      </Modal>

      {/* Cancel modal */}
      <Modal
        description={`Order ${order.order_number} will be cancelled. Items are restocked, customer gets a notification.`}
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={busy}
              onClick={() => setCancelOpen(false)}
              type="button"
            >
              Keep order
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={busy}
              onClick={async () => {
                await patchStatus("cancelled");
                setCancelOpen(false);
              }}
              style={{ background: "#8d1717" }}
              type="button"
            >
              {busy ? "Cancelling…" : "Cancel order"}
            </button>
          </>
        }
        onClose={() => setCancelOpen(false)}
        open={cancelOpen}
        size="sm"
        title="Cancel this order?"
      >
        <p className="text-[13px] leading-relaxed">
          This will set the order to <strong>cancelled</strong>, release any
          inventory holds, and send the customer a cancellation email. The
          payment is not refunded automatically — issue a refund separately
          if you also want to return the money.
        </p>
      </Modal>
    </>
  );
}

function NextActionCard({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="card-solid p-5 border-[color:var(--ink)]/20">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        {label}
      </div>
      <p className="text-[13px] text-[color:var(--muted)] mb-3 max-w-prose">
        {description}
      </p>
      {children}
    </div>
  );
}
