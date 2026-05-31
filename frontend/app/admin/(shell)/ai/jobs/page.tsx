import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { SearchField } from "@/components/form-fields";
import { formatMoney } from "@/lib/api";
import { adminApi, type AdminAIJobListItem } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type SearchParams = { status?: string; q?: string };

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "completed_partial", label: "Partial" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "expired", label: "Expired" },
];

function statusStyle(status: string): string {
  switch (status) {
    case "completed":
      return "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]";
    case "completed_partial":
      return "bg-[#eaf1fb] text-[#1f4b8d] border-[#c2d6ef]";
    case "running":
    case "pending":
    case "queued":
      return "bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]";
    case "failed":
    case "cancelled":
    case "expired":
      return "bg-[#fdecec] text-[#8d1717] border-[#f0c2c2]";
    default:
      return "bg-[color:var(--ivory)] text-[color:var(--ink-soft)] border-[color:var(--line)]";
  }
}

function actorLabel(j: AdminAIJobListItem): string {
  if (j.customer_id) return j.customer_id;
  if (j.anonymous_session_id) return j.anonymous_session_id.slice(0, 12) + "…";
  return "—";
}

function actorKind(j: AdminAIJobListItem): string {
  if (j.customer_id) return "Member";
  if (j.anonymous_session_id) return "Anon";
  return "Unknown";
}

function durationLabel(j: AdminAIJobListItem): string {
  if (!j.completed_at) return "—";
  const ms = new Date(j.completed_at).getTime() - new Date(j.created_at).getTime();
  if (ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export default async function AdminAIJobsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { status, q } = await searchParams;
  const result = await adminApi.listAIJobs({
    status: status || undefined,
    customer_id: q && q.startsWith("cust_") ? q : undefined,
    anonymous_session_id: q && q.startsWith("anon_") ? q : undefined,
    limit: 100,
  });

  if (result.kind === "unauth") return null;
  const data = result.kind === "ok" ? result.data : null;

  return (
    <>
      <PageHeader
        eyebrow="Intelligence"
        title="Try-on jobs"
        subtitle={
          data
            ? `${data.total} job${data.total === 1 ? "" : "s"}${status ? ` · ${status.replace(/_/g, " ")}` : ""}${q ? ` · matching ${q}` : ""}`
            : "Couldn’t reach AI jobs."
        }
      />

      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1">
          {STATUS_TABS.map((tab) => {
            const active = (status || "") === tab.value;
            const params = new URLSearchParams();
            if (tab.value) params.set("status", tab.value);
            if (q) params.set("q", q);
            const href = `/admin/ai/jobs${params.toString() ? `?${params.toString()}` : ""}`;
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={
                  "px-3 h-8 inline-flex items-center rounded-md text-[12px] border transition-colors " +
                  (active
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "bg-white text-[color:var(--ink-soft)] border-[color:var(--line)] hover:bg-[color:var(--ivory)]")
                }
                href={href}
                key={tab.value || "all"}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>

        <form className="flex items-center gap-2" method="get">
          {status ? <input name="status" type="hidden" value={status} /> : null}
          <SearchField
            aria-label="Filter by customer_id or anon session_id"
            className="w-72"
            defaultValue={q}
            name="q"
            placeholder="cust_… or anon_… id"
          />
        </form>
      </div>

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn’t load jobs: {result.message}
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="card-solid p-10 text-center text-sm text-[color:var(--muted)]">
          No jobs match these filters.
        </div>
      ) : data ? (
        <JobsTable items={data.items} />
      ) : null}
    </>
  );
}

function JobsTable({ items }: { items: AdminAIJobListItem[] }) {
  return (
    <div className="card-solid overflow-x-auto">
      <table className="w-full text-[13px] min-w-[960px]">
        <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          <tr>
            <th className="py-2.5 px-4 font-normal text-left">Job</th>
            <th className="py-2.5 px-3 font-normal text-left">Created</th>
            <th className="py-2.5 px-3 font-normal text-center">Status</th>
            <th className="py-2.5 px-3 font-normal text-left">Stage</th>
            <th className="py-2.5 px-3 font-normal text-left">Actor</th>
            <th className="py-2.5 px-3 font-normal text-right">Duration</th>
            <th className="py-2.5 px-4 font-normal text-right">Est. cost</th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr className="border-t border-[color:var(--line)] align-top" key={j.job_id}>
              <td className="py-3 px-4">
                <Link
                  className="font-mono text-[11px] hover:underline"
                  href={`/admin/ai/jobs/${j.job_id}`}
                >
                  {j.job_id}
                </Link>
                {j.failure_reason ? (
                  <div className="text-[11px] text-[#8d1717] truncate max-w-[260px] mt-0.5">
                    {j.failure_reason}
                  </div>
                ) : null}
              </td>
              <td className="py-3 px-3 text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                {new Date(j.created_at).toLocaleString()}
              </td>
              <td className="py-3 px-3 text-center">
                <span
                  className={
                    "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border " +
                    statusStyle(j.status)
                  }
                >
                  {j.status.replace(/_/g, " ")}
                </span>
              </td>
              <td className="py-3 px-3 text-[12px]">
                {j.current_stage?.replace(/_/g, " ") ?? "—"}
              </td>
              <td className="py-3 px-3 text-[12px]">
                <div className="font-mono text-[11px] truncate max-w-[180px]">
                  {actorLabel(j)}
                </div>
                <div className="text-[10px] text-[color:var(--muted)] uppercase tracking-[0.06em]">
                  {actorKind(j)}
                </div>
              </td>
              <td className="py-3 px-3 text-right tabular-nums">{durationLabel(j)}</td>
              <td className="py-3 px-4 text-right tabular-nums whitespace-nowrap">
                {j.estimated_cost_amount != null
                  ? formatMoney(j.estimated_cost_amount, "USD")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
