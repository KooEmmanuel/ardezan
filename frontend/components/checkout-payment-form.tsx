"use client";

import { PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { useState } from "react";

export function CheckoutPaymentForm({
  onSucceeded,
}: {
  onSucceeded?: () => void;
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
      <PaymentElement />
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
