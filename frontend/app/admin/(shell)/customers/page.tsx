import Link from "next/link";

import { PageHeader } from "@/components/admin-page-header";
import { SearchField, SelectField } from "@/components/form-fields";
import { formatMoney } from "@/lib/api";
import { adminApi, type AdminCustomerListItem } from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type Verified = "any" | "yes" | "no";
type Marketing = "any" | "yes" | "no";
type Sort = "recent" | "spend" | "orders";

type SearchParams = {
  q?: string;
  verified?: Verified;
  marketing?: Marketing;
  sort?: Sort;
};

const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: "recent", label: "Newest first" },
  { value: "spend", label: "Top spenders" },
  { value: "orders", label: "Most orders" },
];

export default async function AdminCustomersPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { q, verified, marketing, sort } = await searchParams;
  const result = await adminApi.listCustomers({
    q: q || undefined,
    verified: verified && verified !== "any" ? verified : undefined,
    marketing: marketing && marketing !== "any" ? marketing : undefined,
    sort: sort ?? "recent",
    limit: 100,
  });

  if (result.kind === "unauth") return null;

  const data = result.kind === "ok" ? result.data : null;

  return (
    <>
      <PageHeader
        eyebrow="Sell"
        title="Customers"
        subtitle={
          data ? (
            <span>
              {data.total} registered customer{data.total === 1 ? "" : "s"}
              {q ? <> · matching “{q}”</> : null}
            </span>
          ) : (
            "Couldn’t reach customers."
          )
        }
      />

      <FilterBar
        currentMarketing={marketing ?? "any"}
        currentSort={sort ?? "recent"}
        currentVerified={verified ?? "any"}
        q={q ?? ""}
      />

      {result.kind === "error" ? (
        <div className="card-solid p-6 text-sm">
          Couldn’t load customers: {result.message}
        </div>
      ) : data && data.items.length === 0 ? (
        <EmptyState filtered={Boolean(q || (verified && verified !== "any") || (marketing && marketing !== "any"))} />
      ) : data ? (
        <CustomersTable items={data.items} currency={data.currency} />
      ) : null}
    </>
  );
}

function FilterBar({
  q,
  currentVerified,
  currentMarketing,
  currentSort,
}: {
  q: string;
  currentVerified: Verified;
  currentMarketing: Marketing;
  currentSort: Sort;
}) {
  const isFiltered =
    q ||
    currentVerified !== "any" ||
    currentMarketing !== "any" ||
    currentSort !== "recent";
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      method="get"
    >
      <SearchField
        aria-label="Search customers"
        className="w-56"
        defaultValue={q}
        name="q"
        placeholder="Email or name…"
      />
      <SelectField
        aria-label="Email verified"
        className="w-36"
        defaultValue={currentVerified}
        name="verified"
      >
        <option value="any">Verified: any</option>
        <option value="yes">Verified: yes</option>
        <option value="no">Verified: no</option>
      </SelectField>
      <SelectField
        aria-label="Marketing opt-in"
        className="w-44"
        defaultValue={currentMarketing}
        name="marketing"
      >
        <option value="any">Marketing: any</option>
        <option value="yes">Marketing: opted in</option>
        <option value="no">Marketing: opted out</option>
      </SelectField>
      <SelectField
        aria-label="Sort"
        className="w-40"
        defaultValue={currentSort}
        name="sort"
      >
        {SORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            Sort: {opt.label}
          </option>
        ))}
      </SelectField>
      {isFiltered ? (
        <Link
          className="text-[12px] text-[color:var(--muted)] hover:underline ml-1"
          href="/admin/customers"
        >
          Clear
        </Link>
      ) : null}
    </form>
  );
}

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="card-solid p-10 text-center">
      <div className="font-display text-xl mb-2">
        {filtered ? "No customers match these filters" : "No registered customers yet"}
      </div>
      <p className="text-sm text-[color:var(--muted)] max-w-md mx-auto">
        {filtered
          ? "Try clearing the search or relaxing the filters."
          : "Guest orders show up under Orders even before checkout creates an account. Registered customers will appear here as soon as someone signs up."}
      </p>
      {!filtered ? (
        <Link
          className="btn-secondary inline-flex text-sm mt-4"
          href="/admin/orders"
        >
          View orders →
        </Link>
      ) : null}
    </div>
  );
}

function CustomersTable({
  items,
  currency,
}: {
  items: AdminCustomerListItem[];
  currency: string;
}) {
  return (
    <div className="card-solid overflow-x-auto">
      <table className="w-full text-[13px] min-w-[960px]">
        <thead className="bg-[color:var(--ivory)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          <tr>
            <th className="py-2.5 px-4 font-normal text-left">Customer</th>
            <th className="py-2.5 px-3 font-normal text-left">Email</th>
            <th className="py-2.5 px-3 font-normal text-center">Verified</th>
            <th className="py-2.5 px-3 font-normal text-center">Marketing</th>
            <th className="py-2.5 px-3 font-normal text-right">Orders</th>
            <th className="py-2.5 px-3 font-normal text-right">Lifetime</th>
            <th className="py-2.5 px-3 font-normal text-left">Joined</th>
            <th className="py-2.5 px-4 font-normal text-left">Last order</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr className="border-t border-[color:var(--line)]" key={c.customer_id}>
              <td className="py-3 px-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex items-center justify-center h-9 w-9 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)] text-[12px] font-medium shrink-0">
                    {(c.name || c.email)[0]?.toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <Link
                      className="font-display text-[14px] hover:underline truncate block"
                      href={`/admin/customers/${c.customer_id}`}
                    >
                      {c.name || "—"}
                    </Link>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {c.has_saved_photo ? (
                        <span className="px-1.5 py-px text-[9px] uppercase tracking-[0.08em] rounded-sm bg-white border border-[color:var(--line)] text-[color:var(--muted)]">
                          Saved photo
                        </span>
                      ) : null}
                      {c.body_profile_opted_in ? (
                        <span className="px-1.5 py-px text-[9px] uppercase tracking-[0.08em] rounded-sm bg-white border border-[color:var(--line)] text-[color:var(--muted)]">
                          Body profile
                        </span>
                      ) : null}
                      {c.addresses_count > 0 ? (
                        <span className="px-1.5 py-px text-[9px] uppercase tracking-[0.08em] rounded-sm bg-white border border-[color:var(--line)] text-[color:var(--muted)]">
                          {c.addresses_count} address{c.addresses_count === 1 ? "" : "es"}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </td>
              <td className="py-3 px-3 text-[12px] truncate max-w-[260px]">{c.email}</td>
              <td className="py-3 px-3 text-center">
                {c.email_verified ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border bg-[#e8f3ec] text-[#1f6f3c] border-[#bee0c8]">
                    Yes
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase border bg-[#fff7e6] text-[#8a5a00] border-[#f0d8a0]">
                    Pending
                  </span>
                )}
              </td>
              <td className="py-3 px-3 text-center text-[12px]">
                {c.accepts_marketing ? "✓" : "—"}
              </td>
              <td className="py-3 px-3 text-right tabular-nums">{c.orders_count}</td>
              <td className="py-3 px-3 text-right tabular-nums whitespace-nowrap">
                {formatMoney(c.lifetime_spend_amount, currency)}
              </td>
              <td className="py-3 px-3 text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                {new Date(c.created_at).toLocaleDateString()}
              </td>
              <td className="py-3 px-4 text-[12px] text-[color:var(--muted)] whitespace-nowrap">
                {c.last_order_at
                  ? new Date(c.last_order_at).toLocaleDateString()
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
