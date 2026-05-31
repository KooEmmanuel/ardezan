"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { LabeledField } from "@/components/form-fields";
import { useToast } from "@/components/toast";
import { API_BASE_URL, formatMoney } from "@/lib/api";
import type { AdminAIAnalytics, AdminAISettings } from "@/lib/admin-api";

export function AdminAIControlsForm({
  initial,
  analytics,
}: {
  initial: AdminAISettings;
  analytics: AdminAIAnalytics | null;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [killSwitch, setKillSwitch] = useState(initial.kill_switch_enabled);
  const [ceiling, setCeiling] = useState(initial.daily_spend_ceiling_amount);
  const [anonLimit, setAnonLimit] = useState(initial.anonymous_daily_limit);
  const [memberLimit, setMemberLimit] = useState(initial.registered_weekly_limit);
  const [busy, setBusy] = useState(false);

  const used = analytics?.today_spend_amount ?? 0;
  const pct = ceiling > 0 ? Math.min(100, Math.round((used / ceiling) * 100)) : 0;
  const dirty =
    killSwitch !== initial.kill_switch_enabled ||
    ceiling !== initial.daily_spend_ceiling_amount ||
    anonLimit !== initial.anonymous_daily_limit ||
    memberLimit !== initial.registered_weekly_limit;

  async function save() {
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/admin/settings/ai`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          kill_switch_enabled: killSwitch,
          daily_spend_ceiling_amount: ceiling,
          anonymous_daily_limit: anonLimit,
          registered_weekly_limit: memberLimit,
        }),
      });
      if (!r.ok) {
        let detail = `${r.status}`;
        try {
          const body = (await r.json()) as { error?: { message?: string } };
          detail = body.error?.message ?? detail;
        } catch {
          // ignore
        }
        toast({ title: "Couldn’t save AI settings.", description: detail, kind: "error" });
        return;
      }
      toast({ title: "AI settings saved.", kind: "success" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Today's spend (read-only, sourced from analytics) */}
      <div className="card-solid p-5">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
              Today’s spend
            </div>
            <div className="font-display text-2xl tabular-nums mt-1">
              {formatMoney(used, initial.currency)}{" "}
              <span className="text-[color:var(--muted)] text-sm">
                / {formatMoney(ceiling, initial.currency)}
              </span>
            </div>
          </div>
          {analytics ? (
            <div className="text-[11px] text-[color:var(--muted)] text-right">
              <div>{analytics.try_on_completed_7d} completed · 7d</div>
              <div>{analytics.try_on_failed_7d} failed · 7d</div>
            </div>
          ) : null}
        </div>
        <div className="h-1.5 rounded-full bg-[color:var(--ivory)] overflow-hidden">
          <div
            className="h-full transition-all"
            style={{
              width: `${pct}%`,
              background: pct >= 90 ? "#8d1717" : "var(--ink)",
            }}
          />
        </div>
      </div>

      {/* Kill switch (toggle) */}
      <div className="card-solid p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
              Generation kill switch
            </div>
            <p className="text-[13px] text-[color:var(--ink-soft)] mt-1.5 max-w-prose">
              When on, all new try-on generations are blocked. Catalog, cart, and
              checkout stay live. Use as a break-glass when spend is runaway or a
              provider outage needs to be contained.
            </p>
          </div>
          <button
            aria-checked={killSwitch}
            aria-label="Toggle kill switch"
            className={
              "shrink-0 relative inline-flex h-6 w-11 items-center rounded-full transition-colors " +
              (killSwitch ? "bg-[#8d1717]" : "bg-[color:var(--ivory)] border border-[color:var(--line)]")
            }
            onClick={() => setKillSwitch((v) => !v)}
            role="switch"
            type="button"
          >
            <span
              className={
                "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform " +
                (killSwitch ? "translate-x-6" : "translate-x-1")
              }
            />
          </button>
        </div>
      </div>

      {/* Limits */}
      <div className="card-solid p-5 space-y-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
          Spend & quota limits
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <LabeledField
            hint={`In ${initial.currency} cents (e.g. 7500 = $75.00).`}
            label="Daily ceiling"
          >
            <input
              className="input h-9 text-[13px] tabular-nums"
              inputMode="numeric"
              min={0}
              onChange={(e) => setCeiling(parseInt(e.target.value || "0", 10))}
              type="number"
              value={ceiling}
            />
          </LabeledField>
          <LabeledField hint="Per anon session per day." label="Anonymous daily limit">
            <input
              className="input h-9 text-[13px] tabular-nums"
              inputMode="numeric"
              min={0}
              onChange={(e) => setAnonLimit(parseInt(e.target.value || "0", 10))}
              type="number"
              value={anonLimit}
            />
          </LabeledField>
          <LabeledField hint="Per logged-in customer per 7d." label="Member weekly limit">
            <input
              className="input h-9 text-[13px] tabular-nums"
              inputMode="numeric"
              min={0}
              onChange={(e) => setMemberLimit(parseInt(e.target.value || "0", 10))}
              type="number"
              value={memberLimit}
            />
          </LabeledField>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            className="btn-ghost text-[13px]"
            disabled={busy || !dirty}
            onClick={() => {
              setKillSwitch(initial.kill_switch_enabled);
              setCeiling(initial.daily_spend_ceiling_amount);
              setAnonLimit(initial.anonymous_daily_limit);
              setMemberLimit(initial.registered_weekly_limit);
            }}
            type="button"
          >
            Reset
          </button>
          <button
            className="btn-primary text-[13px]"
            disabled={busy || !dirty}
            onClick={save}
            type="button"
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
