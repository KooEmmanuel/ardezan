import { AdminAIControlsForm } from "@/components/admin-ai-controls";
import { PageHeader } from "@/components/admin-page-header";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminAIPage() {
  const [settings, analytics] = await Promise.all([
    adminApi.getAISettings(),
    adminApi.getAIAnalytics(),
  ]);

  if (settings.kind === "unauth") return null;
  if (settings.kind === "error") {
    return (
      <>
        <PageHeader eyebrow="Intelligence" title="AI controls" />
        <div className="card-solid p-6 text-sm">
          Couldn’t load AI controls: {settings.message}
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Intelligence"
        title="AI controls"
        subtitle="Disable generation as a break-glass; cap daily spend; tune per-identity quotas. Catalog + checkout continue regardless."
      />
      <AdminAIControlsForm
        analytics={analytics.kind === "ok" ? analytics.data : null}
        initial={settings.data}
      />
    </>
  );
}
