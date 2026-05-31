"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AccountPrivacyControls } from "@/components/account-privacy-controls";
import { api } from "@/lib/api";
import type { CustomerPublic } from "@/lib/types";

export default function AccountMePage() {
  const router = useRouter();
  const [me, setMe] = useState<CustomerPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    api.getMe()
      .then(setMe)
      .catch(() => {
        router.replace(`/auth/login?next=${encodeURIComponent("/account/me")}`);
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function onResendVerification() {
    setResendStatus("Sending…");
    try {
      const r = await api.requestEmailVerification();
      setResendStatus(r.queued ? "Verification email sent." : "Already verified.");
    } catch (err) {
      setResendStatus(err instanceof Error ? err.message : "Couldn't send.");
    }
  }

  async function onLogout() {
    setSigningOut(true);
    try {
      await api.logout();
    } catch {
      // ignore — clear UI either way
    }
    router.push("/");
  }

  if (loading) {
    return (
      <section className="max-w-[760px] mx-auto px-5 py-12">
        <div className="card-solid p-6">Loading…</div>
      </section>
    );
  }
  if (error || !me) return null;

  return (
    <section className="max-w-[760px] mx-auto px-5 py-12">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        Your account
      </div>
      <h1 className="font-display text-3xl sm:text-4xl mb-1 break-words">{me.name || me.email}</h1>
      <div className="text-[color:var(--muted)] text-sm mb-8 break-all">{me.email}</div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
        <AccountTile
          eyebrow="Orders"
          href="/account/orders"
          title="Order history"
          subtitle="Track shipments, view receipts."
        />
        <AccountTile
          eyebrow="Fitting Room"
          href="/account/fitting-room"
          title="Saved try-ons"
          subtitle="Reopen any past session."
        />
      </div>

      <div className="card-solid p-5 mb-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
          Email verification
        </div>
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <div className="text-sm">
            {me.email_verified_at ? (
              <span style={{ color: "#166534" }}>
                Verified · {new Date(me.email_verified_at).toLocaleDateString()}
              </span>
            ) : (
              <span style={{ color: "#8d1717" }}>Not yet verified</span>
            )}
          </div>
          {!me.email_verified_at ? (
            <button
              className="btn-secondary text-xs"
              onClick={onResendVerification}
              type="button"
            >
              {resendStatus ?? "Resend verification"}
            </button>
          ) : null}
        </div>
      </div>

      <AccountPrivacyControls />

      <div className="card-solid p-5">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
          Session
        </div>
        <button
          className="btn-secondary"
          disabled={signingOut}
          onClick={onLogout}
          type="button"
        >
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </section>
  );
}

function AccountTile({
  eyebrow,
  title,
  subtitle,
  href,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  href: string;
}) {
  return (
    <Link className="card-solid p-5 product-card block" href={href}>
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        {eyebrow}
      </div>
      <div className="font-display text-xl mb-0.5">{title}</div>
      <div className="text-[color:var(--muted)] text-sm">{subtitle}</div>
    </Link>
  );
}
