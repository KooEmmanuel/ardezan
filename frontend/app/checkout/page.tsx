"use client";

import { Elements } from "@stripe/react-stripe-js";
import { loadStripe, type Stripe } from "@stripe/stripe-js";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { CheckoutPaymentForm } from "@/components/checkout-payment-form";
import { useToast } from "@/components/toast";
import { VerifyEmailBanner } from "@/components/verify-email-banner";
import { api, formatMoney, isEmailNotVerified } from "@/lib/api";
import { readCart, writeCart } from "@/lib/cart";
import type {
  Address,
  CartLineInput,
  CheckoutSessionPublic,
  RevalidateResponse,
} from "@/lib/types";

const COUNTRIES: { code: string; label: string }[] = [
  { code: "US", label: "United States" },
  { code: "GB", label: "United Kingdom" },
  { code: "CA", label: "Canada" },
  { code: "AU", label: "Australia" },
  { code: "FR", label: "France" },
  { code: "DE", label: "Germany" },
];

export default function CheckoutPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [lines, setLines] = useState<CartLineInput[]>([]);
  const [validated, setValidated] = useState<RevalidateResponse | null>(null);
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState<Address>({
    name: "",
    line1: "",
    line2: "",
    city: "",
    region: "",
    postal_code: "",
    country: "US",
  });
  const [shippingMethod, setShippingMethod] = useState<"standard" | "express">("standard");
  const [session, setSession] = useState<CheckoutSessionPublic | null>(null);
  const [creating, setCreating] = useState(false);
  // Set when a logged-in customer must verify their email before checkout.
  const [verifyEmail, setVerifyEmail] = useState<string | null>(null);

  useEffect(() => {
    const cart = readCart();
    if (cart.length === 0) {
      router.replace("/cart");
      return;
    }
    // The cart page may have stashed a filter so this checkout charges
    // only a selected outfit. Anything not in the filter is held back
    // in the cart for a later checkout.
    let scoped: CartLineInput[] = cart;
    try {
      const raw = window.sessionStorage.getItem("ardezan.checkout.line_ids");
      if (raw) {
        const ids = JSON.parse(raw) as string[];
        if (Array.isArray(ids) && ids.length > 0) {
          const set = new Set(ids);
          scoped = cart.filter((l) => set.has(l.line_id));
        }
      }
    } catch {
      // sessionStorage unavailable — fall back to full cart
    }
    if (scoped.length === 0) {
      router.replace("/cart");
      return;
    }
    setLines(scoped);
    api
      .revalidateCart(scoped)
      .then(setValidated)
      .catch((err) =>
        toast({
          title: "Couldn't load your cart.",
          description: err instanceof Error ? err.message : undefined,
          kind: "error",
        }),
      );
  }, [router, toast]);

  const stripePromise = useMemo<Promise<Stripe | null> | null>(() => {
    if (!session?.stripe_publishable_key) return null;
    return loadStripe(session.stripe_publishable_key);
  }, [session?.stripe_publishable_key]);

  const subtotal = validated?.totals.subtotal_amount ?? 0;
  const currency = validated?.totals.currency ?? "USD";

  const canStartPayment =
    !!email &&
    !!address.name &&
    !!address.line1 &&
    !!address.city &&
    !!address.postal_code &&
    !!address.country &&
    !!validated &&
    !validated.blocks_checkout &&
    lines.length > 0;

  async function startPayment() {
    if (!canStartPayment) return;
    setCreating(true);
    try {
      const s = await api.createCheckoutSession({
        lines,
        guest_email: email,
        shipping_address: address,
        shipping_method: shippingMethod,
      });
      setSession(s);
      setVerifyEmail(null);
    } catch (err) {
      if (isEmailNotVerified(err)) {
        // Logged-in customer with an unverified email — show the inline
        // verify banner instead of a dead-end toast.
        const detailEmail =
          typeof err.details.email === "string" ? err.details.email : null;
        setVerifyEmail(detailEmail ?? email);
      } else {
        toast({
          title: "Couldn't start checkout.",
          description: err instanceof Error ? err.message : undefined,
          kind: "error",
        });
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="max-w-[1100px] mx-auto px-5 py-10">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-4xl">Checkout</h1>
        <Link className="btn-ghost underline underline-offset-4 text-sm" href="/cart">
          ← Back to bag
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-8">
        <div className="space-y-6">
          <div className="card-solid p-5">
            <div className="font-display text-xl mb-3">Contact</div>
            <input
              className="input"
              disabled={!!session}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email address"
              type="email"
              value={email}
            />
          </div>

          <div className="card-solid p-5">
            <div className="font-display text-xl mb-3">Shipping address</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                className="input sm:col-span-2"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, name: e.target.value })}
                placeholder="Full name"
                value={address.name}
              />
              <input
                className="input sm:col-span-2"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, line1: e.target.value })}
                placeholder="Address line 1"
                value={address.line1}
              />
              <input
                className="input sm:col-span-2"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, line2: e.target.value })}
                placeholder="Address line 2 (optional)"
                value={address.line2 ?? ""}
              />
              <input
                className="input"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, city: e.target.value })}
                placeholder="City"
                value={address.city}
              />
              <input
                className="input"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, region: e.target.value })}
                placeholder="Region / state"
                value={address.region ?? ""}
              />
              <input
                className="input"
                disabled={!!session}
                onChange={(e) =>
                  setAddress({ ...address, postal_code: e.target.value })
                }
                placeholder="Postal code"
                value={address.postal_code}
              />
              <select
                className="input"
                disabled={!!session}
                onChange={(e) => setAddress({ ...address, country: e.target.value })}
                value={address.country}
              >
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>{c.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="card-solid p-5">
            <div className="font-display text-xl mb-3">Delivery</div>
            <label
              className="flex items-center justify-between p-3 rounded-lg border mb-2 cursor-pointer transition"
              style={{
                borderColor: shippingMethod === "standard" ? "var(--ink)" : "var(--line)",
                background: shippingMethod === "standard" ? "var(--ivory)" : undefined,
              }}
            >
              <span className="flex items-center gap-3">
                <input
                  checked={shippingMethod === "standard"}
                  disabled={!!session}
                  name="ship"
                  onChange={() => setShippingMethod("standard")}
                  type="radio"
                />
                <span>
                  <span className="block text-sm font-medium">Standard</span>
                  <span className="block text-xs text-[color:var(--muted)]">3–5 working days</span>
                </span>
              </span>
              <span className="text-sm">{formatMoney(800, currency)}</span>
            </label>
            <label
              className="flex items-center justify-between p-3 rounded-lg border cursor-pointer transition"
              style={{
                borderColor: shippingMethod === "express" ? "var(--ink)" : "var(--line)",
                background: shippingMethod === "express" ? "var(--ivory)" : undefined,
              }}
            >
              <span className="flex items-center gap-3">
                <input
                  checked={shippingMethod === "express"}
                  disabled={!!session}
                  name="ship"
                  onChange={() => setShippingMethod("express")}
                  type="radio"
                />
                <span>
                  <span className="block text-sm font-medium">Express</span>
                  <span className="block text-xs text-[color:var(--muted)]">1–2 working days</span>
                </span>
              </span>
              <span className="text-sm">{formatMoney(1800, currency)}</span>
            </label>
          </div>

          <div className="card-solid p-5">
            <div className="font-display text-xl mb-3">Payment</div>
            {!session ? (
              <>
                {verifyEmail ? (
                  <div className="mb-4">
                    <VerifyEmailBanner
                      email={verifyEmail}
                      onRetry={startPayment}
                      retryLabel="I've verified — continue to payment"
                    />
                  </div>
                ) : null}
                <p className="text-sm text-[color:var(--muted)] mb-4">
                  We&apos;ll calculate tax and shipping on the next step, then accept payment.
                </p>
                <button
                  className="btn-primary w-full sm:w-auto"
                  disabled={!canStartPayment || creating}
                  onClick={startPayment}
                  type="button"
                >
                  {creating ? "Preparing payment…" : "Continue to payment"}
                </button>
              </>
            ) : session.stripe_client_secret && stripePromise ? (
              <Elements
                options={{
                  clientSecret: session.stripe_client_secret,
                  appearance: {
                    theme: "stripe",
                    variables: {
                      colorPrimary: "#050505",
                      colorBackground: "#ffffff",
                      colorText: "#050505",
                      colorDanger: "#8d1717",
                      borderRadius: "6px",
                    },
                  },
                }}
                stripe={stripePromise}
              >
                <CheckoutPaymentForm
                  onSucceeded={() => {
                    // Only drop the lines we charged for; anything the
                    // customer held back stays in the bag for next time.
                    const paid = new Set(lines.map((l) => l.line_id));
                    const remaining = readCart().filter(
                      (l) => !paid.has(l.line_id),
                    );
                    writeCart(remaining);
                    try {
                      window.sessionStorage.removeItem(
                        "ardezan.checkout.line_ids",
                      );
                    } catch {
                      // ignore
                    }
                  }}
                />
              </Elements>
            ) : (
              <p className="text-sm" style={{ color: "#8d1717" }}>
                Stripe is not configured on the backend. Add STRIPE_SECRET_KEY +
                STRIPE_PUBLISHABLE_KEY in .env.
              </p>
            )}
          </div>
        </div>

        <aside className="card-solid p-5 h-fit lg:sticky lg:top-24 space-y-3">
          <div className="font-display text-xl">Your order</div>
          <div className="space-y-3 text-sm max-h-72 overflow-auto scrollbar-thin pr-1">
            {(validated?.lines ?? []).map((line) => (
              <div className="flex gap-3" key={line.line_id}>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{line.product_title}</div>
                  <div className="text-[12px] text-[color:var(--muted)]">
                    {[line.size, line.color, `× ${line.quantity}`].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="shrink-0">
                  {formatMoney(line.line_subtotal_amount, currency)}
                </div>
              </div>
            ))}
          </div>

          <div className="text-sm space-y-1.5 border-t border-[color:var(--line)] pt-3">
            <div className="flex justify-between">
              <span className="text-[color:var(--muted)]">Subtotal</span>
              <span>{formatMoney(subtotal, currency)}</span>
            </div>
            {session ? (
              <>
                <div className="flex justify-between">
                  <span className="text-[color:var(--muted)]">Shipping</span>
                  <span>{formatMoney(session.totals.shipping_amount, currency)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[color:var(--muted)]">Tax</span>
                  <span>{formatMoney(session.totals.tax_amount, currency)}</span>
                </div>
              </>
            ) : (
              <div className="flex justify-between text-[color:var(--muted)]">
                <span>Shipping + tax</span>
                <span>Calculated at next step</span>
              </div>
            )}
          </div>

          <div className="flex justify-between text-base font-medium pt-3 border-t border-[color:var(--line)]">
            <span>Total</span>
            <span>
              {formatMoney(
                session ? session.totals.total_amount : subtotal,
                currency,
              )}
            </span>
          </div>
        </aside>
      </div>
    </section>
  );
}
