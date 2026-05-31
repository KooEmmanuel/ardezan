"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { api } from "@/lib/api";

export default function ResetPasswordConfirmPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordConfirmInner />
    </Suspense>
  );
}

function ResetPasswordConfirmInner() {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.confirmPasswordReset({ token, new_password: password });
      setDone(true);
      setTimeout(() => router.push("/auth/login"), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthShell
        eyebrow="Password reset"
        title="Missing token"
        subtitle="Open the reset link from your email."
        footer={
          <Link className="underline text-[color:var(--ink)]" href="/auth/reset-password">
            Request a new link
          </Link>
        }
      >
        <div />
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell
        eyebrow="Password reset"
        title="Password updated."
        subtitle="Redirecting you to sign in…"
      >
        <Link className="btn-primary w-full inline-flex justify-center" href="/auth/login">
          Sign in
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell eyebrow="Password reset" title="Choose a new password.">
      <form className="space-y-3" onSubmit={onSubmit}>
        <div>
          <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1" htmlFor="pw">
            New password
          </label>
          <input
            autoComplete="new-password"
            className="input"
            id="pw"
            minLength={8}
            onChange={(e) => setPassword(e.target.value)}
            required
            type="password"
            value={password}
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] block mb-1" htmlFor="pw2">
            Confirm
          </label>
          <input
            autoComplete="new-password"
            className="input"
            id="pw2"
            minLength={8}
            onChange={(e) => setConfirm(e.target.value)}
            required
            type="password"
            value={confirm}
          />
        </div>
        {error ? (
          <p className="text-[12px]" role="alert" style={{ color: "#8d1717" }}>
            {error}
          </p>
        ) : null}
        <button className="btn-primary w-full" disabled={submitting} type="submit">
          {submitting ? "Updating…" : "Update password"}
        </button>
      </form>
    </AuthShell>
  );
}
