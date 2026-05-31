"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { LabeledField, SelectField } from "@/components/form-fields";
import { Modal } from "@/components/modal";
import { useToast } from "@/components/toast";
import { API_BASE_URL } from "@/lib/api";
import type { OrderPublic } from "@/lib/types";

// Customer-visible actions on their own order:
//   - Cancel (only paid/packed)
//   - Request a return (only shipped/delivered, and not already requested)
//
// All backend rejections are reflected in the UI by hiding the action so
// customers don't ask "why doesn't it work?"

const CANCELLABLE = new Set(["paid", "packed"]);
const RETURNABLE = new Set(["shipped", "delivered"]);

const RETURN_REASONS = [
  { value: "size_or_fit", label: "Doesn't fit" },
  { value: "not_as_described", label: "Not as described" },
  { value: "changed_my_mind", label: "Changed my mind" },
  { value: "arrived_damaged", label: "Arrived damaged" },
  { value: "wrong_item", label: "Wrong item received" },
  { value: "other", label: "Other" },
] as const;

export function CustomerOrderActions({ order }: { order: OrderPublic }) {
  const router = useRouter();
  const search = useSearchParams();
  const guestToken = search?.get("token") ?? null;
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  const [cancelOpen, setCancelOpen] = useState(false);

  const [returnOpen, setReturnOpen] = useState(false);
  const [returnReason, setReturnReason] =
    useState<typeof RETURN_REASONS[number]["value"]>("size_or_fit");
  const [returnDetail, setReturnDetail] = useState("");
  const [returnLines, setReturnLines] = useState<Set<string>>(
    () => new Set(order.lines.map((l) => l.line_id)),
  );

  const canCancel = CANCELLABLE.has(order.status);
  const canRequestReturn =
    RETURNABLE.has(order.status) && !order.return_request;
  const hasOpenReturn = !!order.return_request;

  // ── Cancel ──────────────────────────────────────────────────────
  async function doCancel() {
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE_URL}/api/v1/orders/${encodeURIComponent(order.order_id)}/cancel`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        },
      );
      if (!r.ok) {
        let msg = "Couldn't cancel.";
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        toast({ title: "Couldn't cancel.", description: msg, kind: "error" });
        return;
      }
      toast({
        title: "Order cancelled.",
        description: "Your refund is on its way.",
        kind: "success",
      });
      setCancelOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  // ── Request return ─────────────────────────────────────────────
  function toggleReturnLine(lineId: string) {
    setReturnLines((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  }

  async function submitReturn() {
    if (returnLines.size === 0) {
      toast({
        title: "Pick at least one item to return.",
        kind: "warning",
      });
      return;
    }
    const fullReason =
      returnReason +
      (returnDetail.trim() ? ` — ${returnDetail.trim()}` : "");
    setBusy(true);
    try {
      const url =
        `${API_BASE_URL}/api/v1/orders/${encodeURIComponent(order.order_id)}/return-request` +
        (guestToken ? `?token=${encodeURIComponent(guestToken)}` : "");
      const r = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: fullReason,
          line_ids: Array.from(returnLines),
        }),
      });
      if (!r.ok) {
        let msg = "Couldn't open the return.";
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        toast({ title: "Couldn't open the return.", description: msg, kind: "error" });
        return;
      }
      toast({
        title: "Return request opened.",
        description: "We'll email you next steps shortly.",
        kind: "success",
      });
      setReturnOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!canCancel && !canRequestReturn && !hasOpenReturn) return null;

  return (
    <>
      <div className="rounded-lg bg-[color:var(--ivory)] p-4 space-y-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
          Need to make a change?
        </div>

        {hasOpenReturn ? (
          <div className="text-[13px] leading-relaxed">
            <div className="font-medium">Return is being processed.</div>
            <div className="text-[12px] text-[color:var(--muted)] mt-0.5">
              Reason: {order.return_request?.reason}
            </div>
            <div className="text-[12px] text-[color:var(--muted)]">
              Status:{" "}
              <span className="capitalize">
                {order.return_request?.status.replace(/_/g, " ")}
              </span>
              {order.return_request?.received_at
                ? ` · received ${new Date(order.return_request.received_at).toLocaleDateString()}`
                : ""}
            </div>
            <p className="text-[12px] text-[color:var(--muted)] mt-2 leading-snug">
              We&apos;ll email you with the return label and next steps.
              Refunds land 5-10 business days after we receive the parcel.
            </p>
          </div>
        ) : null}

        {canCancel ? (
          <div>
            <p className="text-[12px] text-[color:var(--ink-soft)] mb-2 leading-snug">
              You can cancel while we&apos;re still preparing this order.
              Once it ships, use the returns flow instead.
            </p>
            <button
              className="btn-secondary text-xs"
              disabled={busy}
              onClick={() => setCancelOpen(true)}
              type="button"
            >
              Cancel order
            </button>
          </div>
        ) : null}

        {canRequestReturn ? (
          <div>
            <p className="text-[12px] text-[color:var(--ink-soft)] mb-2 leading-snug">
              Something not right? Open a return — we&apos;ll email you a
              prepaid label and process your refund once it arrives.
            </p>
            <button
              className="btn-primary text-xs"
              disabled={busy}
              onClick={() => setReturnOpen(true)}
              type="button"
            >
              Request a return
            </button>
          </div>
        ) : null}
      </div>

      {/* Cancel modal */}
      <Modal
        description={`Order ${order.order_number} will be cancelled and refunded to your original payment method.`}
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
              onClick={() => void doCancel()}
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
          Your card will be refunded for the full amount within a few
          business days. This can&apos;t be undone — you&apos;d need to
          re-order if you change your mind.
        </p>
      </Modal>

      {/* Return modal */}
      <Modal
        description={`Order ${order.order_number} · pick items + tell us why`}
        footer={
          <>
            <button
              className="btn-ghost text-[13px]"
              disabled={busy}
              onClick={() => setReturnOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="btn-primary text-[13px]"
              disabled={busy || returnLines.size === 0}
              onClick={() => void submitReturn()}
              type="button"
            >
              {busy ? "Opening…" : "Open return request"}
            </button>
          </>
        }
        onClose={() => setReturnOpen(false)}
        open={returnOpen}
        size="md"
        title="Request a return"
      >
        <div className="space-y-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-2">
              Which items?
            </div>
            <ul className="space-y-2">
              {order.lines.map((line) => {
                const checked = returnLines.has(line.line_id);
                return (
                  <li key={line.line_id}>
                    <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border border-[color:var(--line)] hover:bg-[color:var(--ivory)]">
                      <input
                        checked={checked}
                        className="mt-1 h-4 w-4 accent-[color:var(--ink)]"
                        onChange={() => toggleReturnLine(line.line_id)}
                        type="checkbox"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-[14px]">
                          {line.title_snapshot}
                        </div>
                        <div className="text-[11px] text-[color:var(--muted)]">
                          {[line.size, line.color, `× ${line.quantity}`]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>

          <LabeledField label="Reason">
            <SelectField
              dim="md"
              onChange={(e) =>
                setReturnReason(
                  e.target.value as typeof RETURN_REASONS[number]["value"],
                )
              }
              value={returnReason}
            >
              {RETURN_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </SelectField>
          </LabeledField>

          <LabeledField
            hint="Anything that would help us process the return faster."
            label="Tell us more (optional)"
          >
            <textarea
              className="input min-h-[80px] text-[13px]"
              maxLength={400}
              onChange={(e) => setReturnDetail(e.target.value)}
              value={returnDetail}
            />
          </LabeledField>

          <p className="text-[11px] text-[color:var(--muted)] leading-relaxed">
            We&apos;ll email you a prepaid return label within 24 hours.
            Refunds land 5-10 business days after the parcel arrives.
          </p>
        </div>
      </Modal>
    </>
  );
}
