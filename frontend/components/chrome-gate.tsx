"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * Hides storefront chrome (header/footer) on routes that own their full layout.
 * The admin shell uses a sidebar + page padding that conflicts with the
 * sticky storefront header.
 */
export function ChromeGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  if (pathname.startsWith("/admin")) return null;
  return <>{children}</>;
}
