import type { ReactNode } from "react";

// Presentational wrapper for the static info / legal pages (Privacy, Terms,
// Sizing, Returns, Contact). Server-component safe — no hooks, no client code —
// so each page can stay a server component and export `metadata`.
export function ContentPage({
  eyebrow,
  title,
  intro,
  lastUpdated,
  children,
}: {
  eyebrow: string;
  title: string;
  intro?: ReactNode;
  lastUpdated?: string;
  children: ReactNode;
}) {
  return (
    <section className="max-w-[760px] mx-auto px-5 py-12">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        {eyebrow}
      </div>
      <h1 className="font-display text-4xl mb-3">{title}</h1>
      {intro ? (
        <p className="text-[color:var(--ink-soft)] text-[15px] leading-relaxed max-w-prose">
          {intro}
        </p>
      ) : null}
      {lastUpdated ? (
        <p className="text-xs text-[color:var(--muted)] mt-2">
          Last updated {lastUpdated}
        </p>
      ) : null}
      <div className="mt-8 space-y-7">{children}</div>
    </section>
  );
}

// One titled section within a content page.
export function ContentSection({
  heading,
  children,
}: {
  heading: string;
  children: ReactNode;
}) {
  return (
    <div>
      <h2 className="font-display text-xl mb-2">{heading}</h2>
      <div className="text-[14px] text-[color:var(--ink-soft)] leading-relaxed space-y-3 max-w-prose">
        {children}
      </div>
    </div>
  );
}
