"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="max-w-[640px] mx-auto px-5 py-20">
      <div className="card-solid p-8 sm:p-10 text-center">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          Something went wrong
        </div>
        <h1 className="font-display text-3xl sm:text-4xl mb-3">
          A loose thread on our end.
        </h1>
        <p className="text-sm text-[color:var(--muted)] mb-6 leading-relaxed">
          Sorry about that — your bag and orders are safe. Try again, or head
          back to the home page.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2">
          <button className="btn-primary inline-flex" onClick={reset} type="button">
            Try again
          </button>
          <Link
            className="btn-ghost text-sm underline underline-offset-4"
            href="/"
          >
            Back to home
          </Link>
        </div>
        {error.digest ? (
          <p className="text-[11px] text-[color:var(--muted)] mt-6">
            Error reference: <span className="font-mono">{error.digest}</span>
          </p>
        ) : null}
      </div>
    </section>
  );
}
