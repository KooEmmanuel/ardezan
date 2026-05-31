"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Minimal accessible modal. Renders into document.body via portal so it
 * escapes the nearest stacking context (sidebar, sticky headers).
 *
 * - ESC closes
 * - Backdrop click closes
 * - Body scroll locks while open
 * - Focus moves into the dialog on open
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  size = "md",
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  size?: "sm" | "md" | "lg";
  footer?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    dialogRef.current?.focus();
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  const widthClass =
    size === "sm" ? "max-w-[420px]" : size === "lg" ? "max-w-[820px]" : "max-w-[640px]";

  return createPortal(
    <div
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-start sm:items-center justify-center"
      role="dialog"
    >
      <button
        aria-label="Close"
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        tabIndex={-1}
        type="button"
      />
      <div
        className={
          "relative w-full mx-3 my-6 sm:my-0 bg-white rounded-xl shadow-2xl border border-[color:var(--line)] overflow-hidden " +
          widthClass
        }
        ref={dialogRef}
        tabIndex={-1}
      >
        <header className="flex items-start justify-between gap-4 px-5 py-4 border-b border-[color:var(--line)]">
          <div className="min-w-0">
            <h2 className="font-display text-lg leading-tight truncate">{title}</h2>
            {description ? (
              <p className="text-[12px] text-[color:var(--muted)] mt-0.5">
                {description}
              </p>
            ) : null}
          </div>
          <button
            aria-label="Close dialog"
            className="shrink-0 inline-flex items-center justify-center h-7 w-7 rounded-md text-[color:var(--ink-soft)] hover:bg-[color:var(--ivory)]"
            onClick={onClose}
            type="button"
          >
            <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="px-5 py-4 max-h-[70vh] overflow-y-auto">{children}</div>
        {footer ? (
          <footer className="px-5 py-3 border-t border-[color:var(--line)] bg-[color:var(--ivory)] flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
