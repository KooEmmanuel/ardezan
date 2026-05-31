import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi, type AdminAIJobDetail } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

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

function duration(createdAt: string, completedAt: string | null): string {
  if (!completedAt) return "in flight";
  const ms = new Date(completedAt).getTime() - new Date(createdAt).getTime();
  if (ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export default async function AdminAIJobDetailPage({
  params,
}: {
  params: Promise<{ job_id: string }>;
}) {
  const { job_id } = await params;
  const result = await adminApi.getAIJob(job_id);
  if (result.kind === "unauth") return null;
  if (result.kind === "error") notFound();

  const job = result.data;
  const actorLabel = job.customer_id ?? job.anonymous_session_id ?? "—";
  const actorKind = job.customer_id
    ? "Registered customer"
    : job.anonymous_session_id
      ? "Anonymous session"
      : "Unknown";

  return (
    <>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[12px] text-[color:var(--muted)]">
        <Link className="underline underline-offset-2" href="/admin/ai/jobs">
          Try-on jobs
        </Link>
        <span aria-hidden>›</span>
        <span className="font-mono">{job.job_id}</span>
      </nav>

      <PageHeader
        eyebrow="Intelligence"
        title="Try-on job"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] text-[color:var(--muted)]">
              {job.job_id}
            </span>
            <span
              className={
                "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border " +
                statusStyle(job.status)
              }
            >
              {job.status.replace(/_/g, " ")}
            </span>
            {job.current_stage ? (
              <span className="text-[color:var(--muted)]">
                · stage: {job.current_stage.replace(/_/g, " ")}
              </span>
            ) : null}
          </span>
        }
        actions={
          job.try_on_session_id ? (
            <Link
              className="btn-secondary text-sm inline-flex items-center gap-1.5"
              href={`/try-on/jobs/${job.job_id}?session=${job.try_on_session_id}`}
              target="_blank"
            >
              View session
              <svg aria-hidden fill="none" height="12" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="12">
                <path d="M14 3h7v7M21 3l-9 9M10 4H4v16h16v-6" />
              </svg>
            </Link>
          ) : null
        }
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Tile label="Duration" value={duration(job.created_at, job.completed_at)} />
        <Tile label="Actor" foot={actorKind} value={actorLabel} mono />
        <Tile
          foot={(job.cost?.currency as string) ?? "USD"}
          label="Est. cost"
          value={
            job.cost?.estimated_amount != null
              ? formatMoney(
                  job.cost.estimated_amount as number,
                  (job.cost.currency as string) ?? "USD",
                )
              : "—"
          }
        />
        <Tile
          foot={(job.cost?.currency as string) ?? "USD"}
          label="Actual cost"
          value={
            job.cost?.actual_amount != null
              ? formatMoney(
                  job.cost.actual_amount as number,
                  (job.cost.currency as string) ?? "USD",
                )
              : "—"
          }
        />
      </div>

      {job.failure ? <FailureCard failure={job.failure} /> : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ProgressTimeline events={job.progress_events ?? []} />
        <ProviderCalls calls={job.provider_calls ?? []} />
      </div>

      <InputCard input={job.input} session={job.try_on_session_id} />

      <TimeStamps job={job} />
    </>
  );
}

function Tile({
  label,
  value,
  foot,
  mono,
}: {
  label: string;
  value: string;
  foot?: string;
  mono?: boolean;
}) {
  return (
    <div className="card-solid p-4">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
        {label}
      </div>
      <div
        className={
          "leading-tight mt-2 truncate " +
          (mono ? "font-mono text-[12px]" : "font-display text-[20px] tabular-nums")
        }
      >
        {value}
      </div>
      {foot ? (
        <div className="text-[11px] text-[color:var(--muted)] mt-1.5">{foot}</div>
      ) : null}
    </div>
  );
}

function FailureCard({ failure }: { failure: NonNullable<AdminAIJobDetail["failure"]> }) {
  return (
    <div className="card-solid p-5 border-[#f0c2c2]">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-[#fdecec] text-[#8d1717]">
          <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
            <path d="M12 9v4M12 17h.01" />
            <circle cx="12" cy="12" r="10" />
          </svg>
        </span>
        <div className="font-display text-lg">Failure</div>
      </div>
      <div className="space-y-1.5 text-[13px]">
        {failure.failed_stage ? (
          <div>
            <span className="text-[color:var(--muted)] text-[11px] uppercase tracking-[0.1em] mr-2">
              Stage
            </span>
            {failure.failed_stage}
          </div>
        ) : null}
        {failure.reason ? (
          <div>
            <span className="text-[color:var(--muted)] text-[11px] uppercase tracking-[0.1em] mr-2">
              Reason
            </span>
            {failure.reason}
          </div>
        ) : null}
        {failure.technical_detail ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-[11px] uppercase tracking-[0.1em] text-[color:var(--muted)]">
              Technical detail
            </summary>
            <pre className="mt-2 p-3 bg-[color:var(--ivory)] rounded-md text-[11px] overflow-x-auto whitespace-pre-wrap font-mono">
              {failure.technical_detail}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function ProgressTimeline({
  events,
}: {
  events: AdminAIJobDetail["progress_events"];
}) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        Progress
      </div>
      <h2 className="font-display text-xl mt-0.5 mb-3">
        Event timeline · {events.length}
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)] py-6 text-center">
          No progress events recorded.
        </p>
      ) : (
        <ol className="space-y-2 max-h-[420px] overflow-y-auto pr-1 -mr-1">
          {events.map((ev, i) => (
            <li
              className="border border-[color:var(--line)] rounded-md px-3 py-2 text-[12px]"
              key={i}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px]">{ev.type ?? "event"}</span>
                <span className="text-[10px] text-[color:var(--muted)] tabular-nums">
                  {ev.created_at
                    ? new Date(ev.created_at).toLocaleTimeString()
                    : ""}
                </span>
              </div>
              {ev.message ? (
                <div className="text-[12px] mt-0.5">{ev.message}</div>
              ) : null}
              {ev.stage || ev.progress_percent != null ? (
                <div className="text-[10px] text-[color:var(--muted)] mt-0.5 flex items-center gap-2">
                  {ev.stage ? <span>stage: {ev.stage}</span> : null}
                  {ev.progress_percent != null ? (
                    <span>{ev.progress_percent}%</span>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ProviderCalls({
  calls,
}: {
  calls: AdminAIJobDetail["provider_calls"];
}) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        Generations
      </div>
      <h2 className="font-display text-xl mt-0.5 mb-3">
        Provider calls · {calls.length}
      </h2>
      {calls.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)] py-6 text-center">
          No upstream calls recorded.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
              <tr className="text-left">
                <th className="pb-2 font-normal">Op</th>
                <th className="font-normal">Model</th>
                <th className="font-normal text-right">ms</th>
                <th className="font-normal text-right">Cost</th>
                <th className="font-normal text-center">OK</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c, i) => (
                <tr className="border-t border-[color:var(--line)]" key={i}>
                  <td className="py-2">{c.operation ?? "—"}</td>
                  <td className="py-2 font-mono text-[11px] truncate max-w-[140px]">
                    {c.model ?? c.provider ?? "—"}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {c.duration_ms ?? "—"}
                  </td>
                  <td className="py-2 text-right tabular-nums whitespace-nowrap">
                    {c.cost_amount != null
                      ? formatMoney(c.cost_amount, "USD")
                      : "—"}
                  </td>
                  <td className="py-2 text-center">
                    {c.success === false ? (
                      <span className="text-[#8d1717]">✗</span>
                    ) : c.success === true ? (
                      <span className="text-[#1f6f3c]">✓</span>
                    ) : (
                      <span className="text-[color:var(--muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InputCard({
  input,
  session,
}: {
  input: Record<string, unknown>;
  session: string | null;
}) {
  return (
    <div className="card-solid p-5">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
            Request
          </div>
          <h2 className="font-display text-xl mt-0.5">Input</h2>
        </div>
        {session ? (
          <div className="text-[11px] text-[color:var(--muted)]">
            session: <span className="font-mono">{session}</span>
          </div>
        ) : null}
      </div>
      <pre className="bg-[color:var(--ivory)] rounded-md p-3 text-[11px] overflow-x-auto whitespace-pre-wrap font-mono">
        {JSON.stringify(input, null, 2)}
      </pre>
    </div>
  );
}

function TimeStamps({ job }: { job: AdminAIJobDetail }) {
  return (
    <div className="card-solid p-5">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-3">
        Timestamps
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
        <Stamp label="Created" value={job.created_at} />
        <Stamp label="Updated" value={job.updated_at} />
        <Stamp label="Completed" value={job.completed_at} />
        <Stamp label="Expires" value={job.expires_at} />
      </dl>
    </div>
  );
}

function Stamp({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
        {label}
      </dt>
      <dd className="mt-1 tabular-nums">
        {value ? new Date(value).toLocaleString() : "—"}
      </dd>
    </div>
  );
}
