"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { readCart, writeCart } from "@/lib/cart";

// In redirect flows (3DS etc.) the checkout page never gets a chance to
// clear the charged lines — the browser navigates straight here. Drop the
// lines we charged for (recorded in sessionStorage before payment) once
// the order is confirmed.
function clearChargedLines() {
  try {
    const raw = window.sessionStorage.getItem("ardezan.checkout.line_ids");
    window.sessionStorage.removeItem("ardezan.checkout.line_ids");
    if (!raw) return;
    const charged = new Set(JSON.parse(raw) as string[]);
    if (charged.size === 0) return;
    writeCart(readCart().filter((l) => !charged.has(l.line_id)));
  } catch {
    // storage unavailable — cart will self-correct on next revalidate
  }
}

// After Stripe's PaymentElement confirms payment it redirects here with
// ``payment_intent`` (and a guest claim token if applicable). The webhook
// hasn't fired yet, so we poll the backend until the order document
// materializes — then we forward to the proper confirmation page.

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 30; // ~45s total

export default function OrderConfirmationPendingPage() {
  return (
    <Suspense fallback={null}>
      <OrderConfirmationPendingInner />
    </Suspense>
  );
}

function OrderConfirmationPendingInner() {
  const router = useRouter();
  const search = useSearchParams();
  const paymentIntent = search.get("payment_intent");
  const token = search.get("token") ?? undefined;
  const status = search.get("redirect_status") ?? search.get("status") ?? null;

  const [attempts, setAttempts] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!paymentIntent) {
      setError("Missing payment_intent in URL. If you just paid, give it a moment and refresh.");
      return;
    }
    if (status && status !== "succeeded") {
      setError(`Payment status: ${status}. If this is unexpected, contact us.`);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll(n: number) {
      if (cancelled) return;
      try {
        const params = new URLSearchParams();
        if (token) params.set("token", token);
        const r = await fetch(
          `${API_BASE_URL}/api/v1/orders/by-payment-intent/${encodeURIComponent(paymentIntent ?? "")}` +
            (params.toString() ? `?${params.toString()}` : ""),
          { credentials: "include", cache: "no-store" },
        );
        if (r.ok) {
          const data = (await r.json()) as {
            order_id: string;
            guest_token?: string | null;
          };
          // Prefer the URL-provided token; fall back to the freshly-issued
          // guest token returned by the materialize path so guest orders
          // can land straight on /order-confirmation/{id}?token=…
          const resolvedToken = token ?? data.guest_token ?? null;
          const dest = resolvedToken
            ? `/order-confirmation/${data.order_id}?token=${encodeURIComponent(resolvedToken)}`
            : `/order-confirmation/${data.order_id}`;
          clearChargedLines();
          router.replace(dest);
          return;
        }
      } catch {
        // network blip — retry
      }
      setAttempts(n + 1);
      if (n + 1 >= MAX_POLL_ATTEMPTS) {
        setError(
          "Your payment looks complete, but we haven't received the confirmation from Stripe yet. " +
            "Check your email for the receipt, or refresh this page in a minute.",
        );
        return;
      }
      timer = setTimeout(() => poll(n + 1), POLL_INTERVAL_MS);
    }

    poll(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [paymentIntent, token, status, router]);

  return (
    <section className="max-w-[640px] mx-auto px-5 py-16">
      <div className="card-solid p-8 text-center">
        {error ? (
          <>
            <h1 className="font-display text-3xl mb-2">One moment.</h1>
            <p className="text-[color:var(--muted)] mb-5">{error}</p>
            <Link className="btn-primary" href="/">Back to home</Link>
          </>
        ) : (
          <>
            <div className="mx-auto w-12 h-12 rounded-full flex items-center justify-center mb-4 bg-black/5">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="animate-spin"
                aria-hidden
              >
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
            </div>
            <h1 className="font-display text-3xl mb-2">Confirming your order…</h1>
            <p className="text-[color:var(--muted)] text-sm">
              Payment received. We&apos;re finalising your order. This usually takes a few seconds.
            </p>
            {attempts > 4 ? (
              <p className="text-[11px] text-[color:var(--muted)] mt-4">
                Still working — attempt {attempts}/{MAX_POLL_ATTEMPTS}.
              </p>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
