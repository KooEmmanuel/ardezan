"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { readAnonId } from "@/lib/anon";
import { api } from "@/lib/api";
import { readCart } from "@/lib/cart";
import { safeNextPath } from "@/lib/navigation";

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupInner />
    </Suspense>
  );
}

function SignupInner() {
  const router = useRouter();
  const search = useSearchParams();
  const next = safeNextPath(search.get("next"), "/account/me");
  // Guest-order claim handoff from the confirmation page
  // (/auth/signup?claim=<token>&order=<order_id>).
  const claimToken = search.get("claim");
  const claimOrderId = search.get("order");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepts, setAccepts] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.signup({
        email,
        password,
        name,
        accepts_marketing: accepts,
        // Re-key any anonymous design / try-on sessions from this
        // browser onto the new account so the activity hub isn't empty.
        anonymous_session_id: readAnonId() ?? undefined,
      });
      const localCart = readCart();
      if (localCart.length > 0) {
        try {
          await api.mergeAnonymousCart(localCart);
        } catch {
          // ignore — local cart still works
        }
      }
      // Link the guest order to the new account. Best-effort — an
      // expired/used token shouldn't block account creation.
      if (claimToken && claimOrderId) {
        try {
          await api.claimGuestOrder(claimOrderId, claimToken);
          router.push(`/account/orders/${encodeURIComponent(claimOrderId)}`);
          return;
        } catch {
          // token invalid/expired — continue to the normal destination
        }
      }
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create your account.");
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Create account"
      title="Welcome to Ardezan."
      subtitle="Keep your try-ons, saved photo, and orders in one place."
      footer={
        <>
          Already have one?{" "}
          <Link className="underline text-[color:var(--ink)]" href={`/auth/login?next=${encodeURIComponent(next)}`}>
            Sign in
          </Link>
        </>
      }
    >
      <form className="space-y-3" onSubmit={onSubmit}>
        <div>
          <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1" htmlFor="name">
            Name
          </label>
          <input
            autoComplete="name"
            className="input"
            id="name"
            onChange={(e) => setName(e.target.value)}
            required
            value={name}
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1" htmlFor="email">
            Email
          </label>
          <input
            autoComplete="email"
            className="input"
            id="email"
            onChange={(e) => setEmail(e.target.value)}
            required
            type="email"
            value={email}
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1" htmlFor="password">
            Password
          </label>
          <input
            autoComplete="new-password"
            className="input"
            id="password"
            minLength={8}
            onChange={(e) => setPassword(e.target.value)}
            required
            type="password"
            value={password}
          />
          <p className="text-[11px] text-[color:var(--muted)] mt-1">
            At least 8 characters.
          </p>
        </div>
        <label className="flex items-start gap-2 pt-1">
          <input
            checked={accepts}
            className="mt-1"
            onChange={(e) => setAccepts(e.target.checked)}
            type="checkbox"
          />
          <span className="text-[11px] text-[color:var(--muted)] leading-snug">
            Send me occasional updates about new pieces and Try-On improvements.
          </span>
        </label>

        {error ? (
          <p className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
            {error}
          </p>
        ) : null}

        <button className="btn-primary w-full" disabled={submitting} type="submit">
          {submitting ? "Creating…" : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
