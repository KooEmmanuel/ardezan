import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminInspirationsPage() {
  const result = await adminApi.listInspirations();
  if (result.kind === "unauth") return null;

  return (
    <>
      <PageHeader
        eyebrow="Design Me"
        title="Inspirations"
        subtitle={
          result.kind === "ok"
            ? `${result.data.items.length} tiles in the Bespoke gallery`
            : "Couldn't reach inspirations."
        }
      />

      <div className="flex justify-end mb-3">
        <Link className="btn-primary text-sm" href="/admin/inspirations/new">
          + New inspiration
        </Link>
      </div>

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn&apos;t load inspirations: {result.message}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {result.data.items.length === 0 ? (
            <div className="col-span-full card-solid p-10 text-center text-sm text-[color:var(--muted)]">
              No inspirations yet.
            </div>
          ) : (
            result.data.items.map((ins) => (
              <Link
                className="card-solid overflow-hidden block product-card"
                href={`/admin/inspirations/${ins.inspiration_id}`}
                key={ins.inspiration_id}
              >
                <div
                  className="ratio-45 relative"
                  style={{ background: ins.gradient ?? "var(--ivory)" }}
                >
                  {ins.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      alt={ins.title}
                      className="absolute inset-0 w-full h-full object-cover"
                      src={ins.image_url}
                    />
                  ) : null}
                  {!ins.active ? (
                    <span className="absolute top-2 left-2 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-[0.08em] bg-black/60 text-white">
                      Hidden
                    </span>
                  ) : null}
                </div>
                <div className="p-3">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                    {ins.piece_type} · {ins.complexity}
                  </div>
                  <div className="font-display text-base leading-tight mt-0.5">
                    {ins.title}
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
      )}
    </>
  );
}
