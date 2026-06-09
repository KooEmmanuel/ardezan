"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { readAnonId } from "@/lib/anon";
import { api } from "@/lib/api";
import { readCart } from "@/lib/cart";
import { safeNextPath } from "@/lib/navigation";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginInner />
    </Suspense>
  );
}

function LoginInner() {
  const router = useRouter();
  const search = useSearchParams();
  const next = safeNextPath(search.get("next"), "/account/me");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.login({
        email,
        password,
        // Re-key any anonymous design / try-on sessions made in this
        // browser onto the freshly-authenticated customer.
        anonymous_session_id: readAnonId() ?? undefined,
      });
      // Best-effort merge of the anonymous localStorage cart into the
      // newly-authenticated server cart. Failure here doesn't block the
      // login — the user just keeps their local cart.
      const localCart = readCart();
      if (localCart.length > 0) {
        try {
          await api.mergeAnonymousCart(localCart);
        } catch {
          // ignore — local cart still works
        }
      }
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Sign in"
      title="Welcome back."
      footer={
        <div className="flex flex-col gap-2">
          <span>
            New here?{" "}
            <Link className="underline text-[color:var(--ink)]" href={`/auth/signup?next=${encodeURIComponent(next)}`}>
              Create an account
            </Link>
          </span>
          <Link className="text-xs underline" href="/auth/reset-password">
            Forgot password?
          </Link>
        </div>
      }
    >
      <form className="space-y-3" onSubmit={onSubmit}>
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
            autoComplete="current-password"
            className="input"
            id="password"
            onChange={(e) => setPassword(e.target.value)}
            required
            type="password"
            value={password}
          />
        </div>

        {error ? (
          <p className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
            {error}
          </p>
        ) : null}

        <button className="btn-primary w-full" disabled={submitting} type="submit">
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthShell>
  );
}
