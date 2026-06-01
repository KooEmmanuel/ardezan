import Image from "next/image";
import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { formatMoney } from "@/lib/api";
import { adminApi } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

export default async function AdminFabricsPage() {
  const result = await adminApi.listFabrics();
  if (result.kind === "unauth") return null;

  return (
    <>
      <PageHeader
        eyebrow="Design Me"
        title="Fabrics"
        subtitle={
          result.kind === "ok"
            ? `${result.data.items.length} fabrics`
            : "Couldn't reach fabrics."
        }
      />

      <div className="flex justify-end mb-3">
        <Link className="btn-primary text-sm" href="/admin/fabrics/new">
          + New fabric
        </Link>
      </div>

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn&apos;t load fabrics: {result.message}
        </div>
      ) : (
        <div className="card-solid overflow-hidden">
          <table className="w-full text-[13px] min-w-[820px]">
            <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
              <tr>
                <th className="py-2.5 px-3 font-normal text-left w-[80px]">Swatch</th>
                <th className="py-2.5 px-3 font-normal text-left">Name</th>
                <th className="py-2.5 px-3 font-normal text-left">Pieces</th>
                <th className="py-2.5 px-3 font-normal text-right whitespace-nowrap">Per yard</th>
                <th className="py-2.5 px-3 font-normal text-center">Weight</th>
                <th className="py-2.5 px-3 font-normal text-center">Active</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.length === 0 ? (
                <tr>
                  <td className="py-10 px-4 text-center text-[color:var(--muted)]" colSpan={6}>
                    No fabrics yet. Add your first one.
                  </td>
                </tr>
              ) : (
                result.data.items.map((f) => (
                  <tr className="border-t border-[color:var(--line)] hover:bg-[color:var(--ivory)]/40" key={f.fabric_id}>
                    <td className="py-2 px-3">
                      <div
                        className="w-12 h-12 rounded-md overflow-hidden border border-[color:var(--line)] relative"
                        style={{ background: f.swatch.gradient ?? "var(--ivory)" }}
                      >
                        {f.swatch.image_url ? (
                          <Image
                            alt={f.name}
                            className="object-cover"
                            fill
                            sizes="48px"
                            src={f.swatch.image_url}
                          />
                        ) : null}
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <Link
                        className="font-display text-[14px] hover:underline"
                        href={`/admin/fabrics/${f.fabric_id}`}
                      >
                        {f.name}
                      </Link>
                      <div className="text-[11px] text-[color:var(--muted)] truncate max-w-[260px]">
                        {f.description}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-[11.5px] text-[color:var(--muted)]">
                      {f.suitable_for.slice(0, 4).join(", ")}
                      {f.suitable_for.length > 4 ? " …" : null}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums whitespace-nowrap">
                      {formatMoney(f.cost_per_yard_amount, f.currency)}
                    </td>
                    <td className="py-2 px-3 text-center capitalize text-[12px]">{f.weight}</td>
                    <td className="py-2 px-3 text-center">
                      <span
                        className={
                          "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.06em] border " +
                          (f.active
                            ? "bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]"
                            : "bg-[color:var(--ivory)] text-[color:var(--muted)] border-[color:var(--line)]")
                        }
                      >
                        {f.active ? "Live" : "Hidden"}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
