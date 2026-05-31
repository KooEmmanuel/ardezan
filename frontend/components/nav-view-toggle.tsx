"use client";

import { usePathname, useRouter } from "next/navigation";

export function NavViewToggle() {
  const pathname = usePathname();
  const router = useRouter();
  const onCatalog = pathname?.startsWith("/catalog") || pathname?.startsWith("/product");

  return (
    <div className="toggle" role="tablist" aria-label="Browsing mode">
      <button
        aria-pressed={!onCatalog}
        className={!onCatalog ? "on" : ""}
        onClick={() => router.push("/")}
        type="button"
      >
        Try-On
      </button>
      <button
        aria-pressed={Boolean(onCatalog)}
        className={onCatalog ? "on" : ""}
        onClick={() => router.push("/catalog")}
        type="button"
      >
        Catalog
      </button>
    </div>
  );
}
