import { PageHeader } from "@/components/admin-page-header";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminAuditPage({
  searchParams,
}: {
  searchParams: Promise<{ action?: string }>;
}) {
  const { action } = await searchParams;
  const result = await adminApi.listAuditLogs({ action, limit: 100 });
  if (result.kind === "unauth") return null;
  if (result.kind === "error") {
    return (
      <>
        <PageHeader eyebrow="System" title="Audit log" />
        <div className="card-solid p-6 text-sm">
          Couldn’t load audit log: {result.message}
        </div>
      </>
    );
  }

  const { items, total } = result.data;

  return (
    <>
      <PageHeader
        eyebrow="System"
        title="Audit log"
        subtitle={`${total} entries${action ? ` · filter “${action}”` : ""}`}
      />

      <div className="card-solid overflow-x-auto">
        <table className="w-full text-[13px] min-w-[760px]">
          <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            <tr>
              <th className="py-2.5 px-4 font-normal text-left">When</th>
              <th className="py-2.5 px-3 font-normal text-left">Actor</th>
              <th className="py-2.5 px-3 font-normal text-left">Action</th>
              <th className="py-2.5 px-4 font-normal text-left">Target</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td className="py-10 px-4 text-center text-[color:var(--muted)]" colSpan={4}>
                  No entries yet.
                </td>
              </tr>
            ) : (
              items.map((entry) => (
                <tr
                  className="border-t border-[color:var(--line)] align-top"
                  key={entry.audit_log_id}
                >
                  <td className="py-2.5 px-4 text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-2.5 px-3 text-[12px] font-mono">
                    {entry.actor_id ?? (
                      <span className="text-[color:var(--muted)]">system</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-[12px] font-mono">{entry.action}</td>
                  <td className="py-2.5 px-4 text-[12px]">
                    <div className="text-[color:var(--muted)]">
                      {entry.target_type ?? "—"}
                    </div>
                    {entry.target_id ? (
                      <div className="font-mono">{entry.target_id}</div>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
