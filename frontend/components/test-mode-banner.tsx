"use client";

import { useState } from "react";

import { DEMO_MODE, STRIPE_TEST_CARD } from "@/lib/demo";

// Thin site-wide bar shown in demo mode so visitors know the store is safe to
// click through, and hands them the one non-obvious thing they need: the test
// card number (one click to copy). Renders nothing when demo mode is off.
export function TestModeBanner() {
  const [copied, setCopied] = useState(false);

  if (!DEMO_MODE) return null;

  async function copyCard() {
    try {
      await navigator.clipboard.writeText(STRIPE_TEST_CARD.replace(/\s/g, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked — the number is visible to type manually
    }
  }

  return (
    <div className="w-full bg-black text-white text-[12px] sm:text-[13px] leading-none">
      <div className="max-w-[1280px] mx-auto px-4 sm:px-5 py-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 text-center">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden>🧪</span>
          Demo store — Stripe <b className="font-semibold">test mode</b>. No real charges.
        </span>
        <span className="hidden sm:inline opacity-40">·</span>
        <span className="inline-flex items-center gap-1.5">
          Pay with
          <button
            type="button"
            onClick={copyCard}
            title="Copy test card number"
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-white/15 hover:bg-white/25 transition font-mono tracking-wide"
          >
            {STRIPE_TEST_CARD}
            {copied ? (
              <span className="text-[11px]">✓ copied</span>
            ) : (
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <rect x="9" y="9" width="11" height="11" rx="2" />
                <path d="M5 15V5a2 2 0 0 1 2-2h10" />
              </svg>
            )}
          </button>
          <span className="hidden sm:inline">· any future date · any CVC</span>
        </span>
      </div>
    </div>
  );
}
