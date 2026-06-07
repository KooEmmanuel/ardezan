"use client";

import { PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { useState } from "react";

import { DEMO_MODE, STRIPE_TEST_CARD } from "@/lib/demo";

type BillingDetails = {
  name?: string;
  email?: string;
  address?: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;
    postal_code?: string;
    country?: string;
  };
};

export function CheckoutPaymentForm({
  onSucceeded,
  defaultBilling,
}: {
  onSucceeded?: () => void;
  // Prefilled into the Payment Element's billing fields so only the card
  // number is left to enter. (Stripe forbids prefilling the card itself.)
  defaultBilling?: BillingDetails;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!stripe || !elements) return;
    setSubmitting(true);
    setError(null);

    const { error: confirmError, paymentIntent } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/order-confirmation/pending`,
      },
      redirect: "if_required",
    });

    if (confirmError) {
      setError(confirmError.message ?? "Payment failed.");
      setSubmitting(false);
      return;
    }

    // Card flows often finish without redirecting (Stripe doesn't need to
    // bounce through a 3DS page). In that case we have the paymentIntent
    // right here — forward to the pending page which polls until the
    // webhook materializes the order.
    onSucceeded?.();
    if (paymentIntent) {
      window.location.assign(
        `/order-confirmation/pending?payment_intent=${encodeURIComponent(
          paymentIntent.id,
        )}&redirect_status=${paymentIntent.status}`,
      );
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      {DEMO_MODE ? <TestCardHint /> : null}
      <PaymentElement
        options={defaultBilling ? { defaultValues: { billingDetails: defaultBilling } } : undefined}
      />
      {error ? (
        <p className="text-sm" style={{ color: "#8d1717" }}>
          {error}
        </p>
      ) : null}
      <button
        className="btn-primary w-full"
        disabled={!stripe || submitting}
        type="submit"
      >
        {submitting ? "Processing…" : "Pay now"}
      </button>
      <p className="text-[11px] text-[color:var(--muted)] flex items-center gap-1.5">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        Payment is handled by Stripe. Card details never touch our server.
      </p>
    </form>
  );
}

// Compact reminder sitting right above the card field: the one thing a visitor
// needs to complete the demo. One click copies the number.
function TestCardHint() {
  const [copied, setCopied] = useState(false);
  async function copyCard() {
    try {
      await navigator.clipboard.writeText(STRIPE_TEST_CARD.replace(/\s/g, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked — the number is visible to type manually
    }
  }
  return (
    <div className="rounded-lg border border-dashed border-[color:var(--line)] bg-black/[0.02] px-3 py-2.5 text-[12px] leading-relaxed">
      <div className="flex items-center gap-1.5 font-medium mb-1">
        <span aria-hidden>🧪</span> Test mode — use this card, you won&apos;t be charged
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[color:var(--muted)]">
        <button
          type="button"
          onClick={copyCard}
          title="Copy test card number"
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-black text-white font-mono tracking-wide hover:bg-[color:var(--ink-soft)] transition"
        >
          {STRIPE_TEST_CARD}
          {copied ? (
            <span className="text-[11px]">✓ copied</span>
          ) : (
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <rect x="9" y="9" width="11" height="11" rx="2" />
              <path d="M5 15V5a2 2 0 0 1 2-2h10" />
            </svg>
          )}
        </button>
        <span>any future expiry · any CVC · any ZIP</span>
      </div>
    </div>
  );
}
