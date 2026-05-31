import type { InputHTMLAttributes, SelectHTMLAttributes, ReactNode } from "react";

/**
 * Slim form primitives used across the admin shell. They share a single
 * height (h-8 → 32px), shared border, and consistent paddings so filter
 * rows look like one component instead of stitched-together inputs.
 *
 * `SearchField`  — text input with a leading magnifier glyph.
 * `SelectField`  — native select with a trailing chevron glyph.
 * `LabeledField` — small uppercase eyebrow above any field; used inside modals.
 */

type SearchFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
  dim?: "sm" | "md";
};

export function SearchField({
  className = "",
  dim = "sm",
  ...rest
}: SearchFieldProps) {
  const h = dim === "md" ? "h-9" : "h-8";
  return (
    <div className={"relative " + className}>
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-[color:var(--muted)]"
      >
        <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </span>
      <input
        className={
          "w-full pl-8 pr-3 text-[13px] rounded-md bg-white border border-[color:var(--line)] " +
          "focus:outline-none focus:border-[color:var(--ink)] " +
          h
        }
        type="search"
        {...rest}
      />
    </div>
  );
}

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> & {
  dim?: "sm" | "md";
};

export function SelectField({
  className = "",
  dim = "sm",
  children,
  ...rest
}: SelectFieldProps) {
  const h = dim === "md" ? "h-9" : "h-8";
  return (
    <div className={"relative " + className}>
      <select
        className={
          "appearance-none w-full pl-3 pr-7 text-[13px] rounded-md bg-white border border-[color:var(--line)] " +
          "focus:outline-none focus:border-[color:var(--ink)] " +
          h
        }
        {...rest}
      >
        {children}
      </select>
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-[color:var(--muted)]"
      >
        <svg fill="none" height="12" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="12">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </div>
  );
}

export function LabeledField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-1">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="block text-[11px] text-[color:var(--muted)] mt-1">{hint}</span>
      ) : null}
    </label>
  );
}
