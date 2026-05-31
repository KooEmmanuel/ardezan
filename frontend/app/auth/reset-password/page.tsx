"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { api } from "@/lib/api";

export default function ResetPasswordRequestPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.requestPasswordReset(email);
    } catch {
      // backend returns 204 regardless of whether the email exists, so any
      // error here is a real network/rate-limit issue. We still surface
      // 'sent' so we don't leak account enumeration.
    } finally {
      setSent(true);
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Password reset"
      title={sent ? "Check your inbox." : "Forgot your password?"}
      subtitle={
        sent
          ? "If that email is on file, we just sent a reset link. It's valid for one hour."
          : "Enter the email on your account and we'll send a reset link."
      }
      footer={
        <Link className="underline text-[color:var(--ink)]" href="/auth/login">
          ← Back to sign in
        </Link>
      }
    >
      {sent ? (
        <Link className="btn-primary w-full inline-flex justify-center" href="/auth/login">
          Back to sign in
        </Link>
      ) : (
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
          <button className="btn-primary w-full" disabled={submitting} type="submit">
            {submitting ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
