"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type Item = { href: string; label: string; icon: ReactNode; match: "exact" | "prefix" };
type Section = { label: string; items: Item[] };

const ICON_CLASS = "h-[16px] w-[16px] shrink-0";

const Icon = {
  dashboard: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  ),
  orders: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 6h18l-2 12H5L3 6z" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  ),
  customers: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.6-3.5 3.3-5.5 6.5-5.5s5.9 2 6.5 5.5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M17 14c2.4 0 4.5 1.4 5 4" />
    </svg>
  ),
  products: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 7l9-4 9 4-9 4-9-4z" />
      <path d="M3 7v10l9 4 9-4V7" />
      <path d="M12 11v10" />
    </svg>
  ),
  inventory: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="4" width="18" height="6" rx="1" />
      <rect x="3" y="14" width="18" height="6" rx="1" />
      <path d="M7 7h.01M7 17h.01" />
    </svg>
  ),
  sizes: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="9" width="18" height="6" rx="1" />
      <path d="M7 9v3M11 9v3M15 9v3M19 9v3" />
    </svg>
  ),
  ai: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2" />
      <circle cx="12" cy="12" r="4.5" />
    </svg>
  ),
  audit: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 4h12l4 4v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
      <path d="M8 12h8M8 16h5M8 8h4" />
    </svg>
  ),
  jobs: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 9h18" />
      <path d="M8 13h3M8 16h6" />
    </svg>
  ),
  storefront: (
    <svg className={ICON_CLASS} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 9l1-5h16l1 5" />
      <path d="M3 9v11h18V9" />
      <path d="M3 9c0 1.7 1.3 3 3 3s3-1.3 3-3M9 9c0 1.7 1.3 3 3 3s3-1.3 3-3M15 9c0 1.7 1.3 3 3 3s3-1.3 3-3" />
    </svg>
  ),
};

const SECTIONS: Section[] = [
  {
    label: "Overview",
    items: [{ href: "/admin", label: "Dashboard", icon: Icon.dashboard, match: "exact" }],
  },
  {
    label: "Sell",
    items: [
      { href: "/admin/orders", label: "Orders", icon: Icon.orders, match: "prefix" },
      { href: "/admin/customers", label: "Customers", icon: Icon.customers, match: "prefix" },
    ],
  },
  {
    label: "Catalog",
    items: [
      { href: "/admin/products", label: "Products", icon: Icon.products, match: "prefix" },
      { href: "/admin/inventory", label: "Inventory", icon: Icon.inventory, match: "prefix" },
      { href: "/admin/fabrics", label: "Fabrics", icon: Icon.products, match: "prefix" },
      { href: "/admin/inspirations", label: "Inspirations", icon: Icon.products, match: "prefix" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/admin/ai", label: "AI controls", icon: Icon.ai, match: "exact" },
      { href: "/admin/ai/jobs", label: "Try-on jobs", icon: Icon.jobs, match: "prefix" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/admin/commerce", label: "Pricing & shipping", icon: Icon.audit, match: "prefix" },
      { href: "/admin/audit", label: "Audit log", icon: Icon.audit, match: "prefix" },
    ],
  },
];

export function AdminSidebar({
  me,
}: {
  me: { email: string; name: string; role: string } | null;
}) {
  const pathname = usePathname() ?? "/admin";

  function isActive(item: Item): boolean {
    if (item.match === "exact") return pathname === item.href;
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  return (
    <aside className="w-full lg:w-[240px] lg:shrink-0 lg:h-[calc(100vh-4rem)] lg:sticky lg:top-16 flex flex-col bg-white border-r border-[color:var(--line)]">
      <div className="px-5 pt-5 pb-3">
        <Link className="flex items-center gap-2" href="/admin">
          <span className="font-display text-lg leading-none">Ardezan</span>
          <span className="pill pill-soft text-[9px] tracking-[0.14em]">ADMIN</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-3 space-y-4">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="px-3 pb-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
              {section.label}
            </div>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active = isActive(item);
                return (
                  <li key={item.href}>
                    <Link
                      aria-current={active ? "page" : undefined}
                      className={
                        "flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors " +
                        (active
                          ? "bg-[color:var(--ink)] text-[color:var(--paper)]"
                          : "text-[color:var(--ink-soft)] hover:bg-[color:var(--ivory)]")
                      }
                      href={item.href}
                    >
                      <span
                        className={active ? "text-[color:var(--paper)]" : "text-[color:var(--muted)]"}
                      >
                        {item.icon}
                      </span>
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-[color:var(--line)] p-3 mt-auto">
        <Link
          className="flex items-center gap-2 px-3 py-2 rounded-md text-[12px] text-[color:var(--ink-soft)] hover:bg-[color:var(--ivory)]"
          href="/"
        >
          <span className="text-[color:var(--muted)]">{Icon.storefront}</span>
          View storefront
        </Link>
        {me ? (
          <div className="mt-2 px-3 py-2 rounded-md bg-[color:var(--ivory)]">
            <div className="flex items-center gap-2 min-w-0">
              <div className="flex items-center justify-center h-7 w-7 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)] text-[11px] font-medium shrink-0">
                {me.name?.[0]?.toUpperCase() ?? "A"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[12px] truncate">{me.name || "Admin"}</div>
                <div className="text-[10px] text-[color:var(--muted)] truncate">{me.email}</div>
              </div>
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] uppercase tracking-[0.14em]">
              <span className="text-[color:var(--muted)]">{me.role}</span>
              <Link className="underline underline-offset-2" href="/admin/login?action=logout">
                Sign out
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
