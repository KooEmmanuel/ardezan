import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between border-b border-[color:var(--line)] pb-5">
      <div className="min-w-0">
        {eyebrow ? (
          <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--muted)] mb-1">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="font-display text-[28px] leading-tight tracking-tight truncate">
          {title}
        </h1>
        {subtitle ? (
          <div className="mt-1 text-[13px] text-[color:var(--muted)]">{subtitle}</div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>
      ) : null}
    </header>
  );
}
