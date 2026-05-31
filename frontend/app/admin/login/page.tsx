"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";

export default function AdminLoginPage() {
  return (
    <Suspense fallback={null}>
      <AdminLoginInner />
    </Suspense>
  );
}

function AdminLoginInner() {
  const router = useRouter();
  const search = useSearchParams();
  const action = search.get("action");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loggedOut, setLoggedOut] = useState(false);

  // If we landed here from "Sign out", clear the cookie first.
  useEffect(() => {
    if (action !== "logout") return;
    fetch(`${API_BASE_URL}/api/v1/admin/auth/logout`, {
      method: "POST",
      credentials: "include",
    })
      .catch(() => undefined)
      .finally(() => setLoggedOut(true));
  }, [action]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/admin/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (!r.ok) {
        let msg = "Sign-in failed.";
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          msg = body.error?.message ?? msg;
        } catch {
          // ignore
        }
        setError(msg);
        setSubmitting(false);
        return;
      }
      router.push("/admin");
    } catch {
      setError("Couldn't reach the server.");
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-[440px] mx-auto px-5 py-16">
      <div className="card-solid p-8">
        <Link className="block mb-6 text-sm text-[color:var(--ink-soft)] underline underline-offset-4" href="/">
          ← Storefront
        </Link>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          Ardezan · Admin
        </div>
        <h1 className="font-display text-3xl mb-1">Sign in.</h1>
        <p className="text-[color:var(--muted)] text-sm mb-6">
          Owner / operator access only.
        </p>

        {loggedOut ? (
          <p className="text-[12px] mb-4" style={{ color: "#166534" }}>
            You&apos;ve been signed out.
          </p>
        ) : null}

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
      </div>
    </section>
  );
}
