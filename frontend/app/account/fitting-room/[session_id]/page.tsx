import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";

import { TryOnResultGrid } from "@/components/try-on-result-grid";
import { serverApi } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function FittingRoomDetailPage({
  params,
}: {
  params: Promise<{ session_id: string }>;
}) {
  const { session_id } = await params;
  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  let session;
  try {
    session = await serverApi.getTryOnSession(session_id, cookieHeader);
  } catch {
    notFound();
  }

  return (
    <section className="ai-canvas">
      <div className="max-w-[1280px] mx-auto px-5 py-10">
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4 mb-6">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-1">
              Saved try-on
            </div>
            <h1 className="font-display text-4xl sm:text-5xl leading-[1.02]">
              {session.result_cards.length} looks, on you.
            </h1>
            <div className="text-[color:var(--ink-soft)] text-sm mt-1">
              {new Date(session.created_at).toLocaleString()}
            </div>
          </div>
          <Link className="sm:ml-auto btn-ghost underline underline-offset-4 text-sm" href="/account/fitting-room">
            ← Fitting Room
          </Link>
        </div>

        <TryOnResultGrid
          cards={session.result_cards}
          loading={false}
          sessionId={session.try_on_session_id}
        />

        <div className="text-xs text-[color:var(--ink-soft)] mt-6 text-center max-w-xl mx-auto">
          AI preview — generated images approximate fit, drape, and color. Actual garment may vary.
        </div>
      </div>
    </section>
  );
}
