"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// The desktop primary nav (Women / Men / Bespoke / …) is `hidden md:flex`, so
// on phones there's nothing to navigate with. This renders a `md:hidden`
// hamburger that opens an on-brand top sheet exposing the same links plus
// Account. Mirrors the header nav in `app/layout.tsx`.
const LINKS = [
  { href: "/catalog?cat=women", label: "Women" },
  { href: "/catalog?cat=men", label: "Men" },
  { href: "/catalog?cat=bespoke", label: "Bespoke" },
  { href: "/try-on/design", label: "Design Me" },
  { href: "/catalog?cat=new", label: "New" },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close whenever the route changes (a link was tapped).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Lock body scroll + close on Escape while the sheet is open.
  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        aria-expanded={open}
        aria-label="Open menu"
        className="md:hidden inline-flex items-center justify-center p-2 -ml-1 rounded-md hover:bg-black/5"
        onClick={() => setOpen(true)}
        type="button"
      >
        <svg
          aria-hidden
          fill="none"
          height="20"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
          width="20"
        >
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
      </button>

      {open ? (
        <div
          aria-label="Menu"
          aria-modal="true"
          className="md:hidden fixed inset-0 z-50"
          role="dialog"
        >
          <button
            aria-label="Close menu"
            className="absolute inset-0 bg-black/30"
            onClick={() => setOpen(false)}
            tabIndex={-1}
            type="button"
          />
          <nav
            aria-label="Mobile"
            className="absolute top-0 inset-x-0 bg-[color:var(--paper)] border-b border-[color:var(--line)] shadow-xl reveal"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--line)]">
              <span className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                Menu
              </span>
              <button
                aria-label="Close menu"
                className="p-2 -mr-1 rounded-md hover:bg-black/5"
                onClick={() => setOpen(false)}
                type="button"
              >
                <svg
                  aria-hidden
                  fill="none"
                  height="18"
                  stroke="currentColor"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  width="18"
                >
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </div>
            <div className="px-2 py-2">
              {LINKS.map((l) => (
                <Link
                  className="block px-3 py-3 rounded-md font-display text-xl hover:bg-[color:var(--ivory)]"
                  href={l.href}
                  key={l.href}
                  onClick={() => setOpen(false)}
                >
                  {l.label}
                </Link>
              ))}
              <Link
                className="block px-3 py-3 mt-1 pt-3 rounded-md text-sm text-[color:var(--ink-soft)] border-t border-[color:var(--line)] hover:bg-[color:var(--ivory)]"
                href="/account/me"
                onClick={() => setOpen(false)}
              >
                Account
              </Link>
            </div>
          </nav>
        </div>
      ) : null}
    </>
  );
}
