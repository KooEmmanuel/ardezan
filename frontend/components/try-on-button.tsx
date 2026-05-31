"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ensureAnonId } from "@/lib/anon";
import { api } from "@/lib/api";
import { loadPhoto } from "@/lib/photo-cache";

// "Try-on" button used on every product card. Two paths:
//
//   1. Shopper has a cached photo from a previous try-on → POST a new
//      session with the cached photo + ``seeded_product_id`` and redirect
//      straight to the SSE job page.
//
//   2. No cached photo → bounce to /try-on?seed=<product_id> so they can
//      upload, and the seed flows through.

type Variant = "icon" | "pill" | "compact";

export function TryOnButton({
  productId,
  productSlug,
  variant = "pill",
  className = "",
  label = "Try on me",
}: {
  productId: string;
  productSlug: string;
  variant?: Variant;
  className?: string;
  label?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onClick(e: React.MouseEvent) {
    // Containers (cards) often wrap this button in an <a>. Stop the click
    // from also navigating to the product detail page.
    e.preventDefault();
    e.stopPropagation();

    if (busy) return;
    setBusy(true);
    try {
      const cached = await loadPhoto();
      if (!cached) {
        router.push(`/try-on?seed=${encodeURIComponent(productId)}`);
        return;
      }

      const anonId = ensureAnonId();
      const session = await api.createTryOnSession(cached, {
        age_confirmed: true,
        seeded_product_id: productId,
        anonymous_session_id: anonId,
        fit_preference: "regular",
      });
      router.push(
        `/try-on/jobs/${session.job_id}?session=${session.try_on_session_id}&seed=${encodeURIComponent(productSlug)}`,
      );
    } catch {
      // Fall back to the upload page if anything goes wrong (corrupt
      // cache, expired backend session, etc.).
      router.push(`/try-on?seed=${encodeURIComponent(productId)}`);
    } finally {
      setBusy(false);
    }
  }

  const baseProps = {
    onClick,
    type: "button" as const,
    disabled: busy,
    title: "See this on you",
  };

  if (variant === "icon") {
    return (
      <button
        {...baseProps}
        className={
          "absolute top-2 right-2 z-10 w-8 h-8 rounded-full bg-white/90 backdrop-blur-md " +
          "border border-white/80 shadow flex items-center justify-center hover:bg-white " +
          "transition-transform hover:scale-105 " +
          className
        }
        aria-label="Try on me"
      >
        {busy ? (
          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M12 2 L13.5 9 L20 10.5 L13.5 12 L12 19 L10.5 12 L4 10.5 L10.5 9 Z" />
          </svg>
        )}
      </button>
    );
  }

  if (variant === "compact") {
    return (
      <button
        {...baseProps}
        className={"pill pill-ai inline-flex items-center gap-1 " + className}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M12 2 L13.5 9 L20 10.5 L13.5 12 L12 19 L10.5 12 L4 10.5 L10.5 9 Z" />
        </svg>
        {busy ? "Starting…" : label}
      </button>
    );
  }

  return (
    <button {...baseProps} className={"btn-primary " + className}>
      <svg className="mr-1.5" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M12 2 L13.5 9 L20 10.5 L13.5 12 L12 19 L10.5 12 L4 10.5 L10.5 9 Z" />
      </svg>
      {busy ? "Starting…" : label}
    </button>
  );
}
