"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { api } from "@/lib/api";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}

function VerifyEmailInner() {
  const search = useSearchParams();
  const token = search.get("token");
  const [status, setStatus] = useState<"verifying" | "ok" | "failed">("verifying");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("failed");
      setMessage("Missing token. Open the link from your inbox.");
      return;
    }
    api.confirmEmailVerification(token)
      .then(() => setStatus("ok"))
      .catch((err) => {
        setStatus("failed");
        setMessage(err instanceof Error ? err.message : "Couldn't verify.");
      });
  }, [token]);

  return (
    <AuthShell
      eyebrow="Email verification"
      title={
        status === "ok"
          ? "Email confirmed."
          : status === "failed"
            ? "Verification failed."
            : "One moment…"
      }
      subtitle={
        status === "ok"
          ? "Your account is fully active."
          : status === "failed"
            ? (message ?? "Link is invalid or expired.")
            : "Validating your link…"
      }
    >
      {status === "ok" ? (
        <Link className="btn-primary w-full inline-flex justify-center" href="/account/me">
          Go to my account
        </Link>
      ) : status === "failed" ? (
        <div className="flex flex-col gap-2">
          <Link className="btn-primary w-full inline-flex justify-center" href="/auth/login">
            Sign in to request a new link
          </Link>
        </div>
      ) : (
        <div className="text-center py-4">
          <svg className="animate-spin mx-auto" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
        </div>
      )}
    </AuthShell>
  );
}
