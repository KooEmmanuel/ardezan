import Link from "next/link";
import type { ReactNode } from "react";

export function AuthShell({
  eyebrow,
  title,
  subtitle,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section className="max-w-[480px] mx-auto px-5 py-12 sm:py-20">
      <div className="card-solid p-8">
        <Link className="block mb-6 text-sm text-[color:var(--ink-soft)] underline underline-offset-4" href="/">
          ← Back to Ardezan
        </Link>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          {eyebrow}
        </div>
        <h1 className="font-display text-3xl sm:text-4xl mb-2">{title}</h1>
        {subtitle ? (
          <p className="text-[color:var(--muted)] text-sm mb-6">{subtitle}</p>
        ) : (
          <div className="mb-6" />
        )}
        {children}
        {footer ? (
          <div className="mt-6 pt-5 border-t border-[color:var(--line)] text-sm text-[color:var(--muted)]">
            {footer}
          </div>
        ) : null}
      </div>
    </section>
  );
}
