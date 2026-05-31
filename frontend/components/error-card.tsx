// Inline error card used for blocking error states (try-on failed, page
// couldn't load, etc). Keep one canonical visual treatment instead of
// hand-rolled red <p> tags scattered across pages.

import Link from "next/link";

import type { ReactNode } from "react";

export function ErrorCard({
  title,
  message,
  cta,
  technicalDetail,
}: {
  title: string;
  message?: ReactNode;
  cta?: { label: string; href: string };
  technicalDetail?: string | null;
}) {
  return (
    <div className="card-solid p-6 text-center max-w-xl mx-auto">
      <div className="mx-auto mb-3 w-12 h-12 rounded-full flex items-center justify-center" style={{ background: "rgba(141,23,23,0.08)" }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8d1717" strokeWidth="2" aria-hidden>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v5M12 16h.01" />
        </svg>
      </div>
      <div className="font-display text-2xl mb-1">{title}</div>
      {message ? (
        <div className="text-[color:var(--muted)] text-sm leading-snug max-w-md mx-auto">
          {message}
        </div>
      ) : null}
      {cta ? (
        <Link className="btn-primary mt-5 inline-flex" href={cta.href}>
          {cta.label}
        </Link>
      ) : null}
      {technicalDetail ? (
        <details className="mt-5 text-left">
          <summary className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] cursor-pointer">
            Technical detail
          </summary>
          <pre className="text-[10px] mt-2 p-2 rounded bg-[color:var(--ivory)] overflow-x-auto text-[color:var(--ink-soft)]">
            {technicalDetail}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
