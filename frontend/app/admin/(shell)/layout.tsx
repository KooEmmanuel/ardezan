import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AdminSidebar } from "@/components/admin-sidebar";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminShellLayout({ children }: { children: ReactNode }) {
  // Server-side auth gate. Unauthenticated requests bounce to /admin/login.
  const result = await adminApi.me();
  if (result.kind === "unauth") {
    redirect("/admin/login");
  }
  const me = result.kind === "ok" ? result.data : null;

  return (
    <div className="admin-shell min-h-screen bg-[color:var(--paper)]">
      <div className="flex flex-col lg:flex-row min-h-screen">
        <AdminSidebar me={me} />
        <main className="flex-1 min-w-0 px-5 sm:px-8 py-8">
          <div className="max-w-[1320px] mx-auto space-y-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
