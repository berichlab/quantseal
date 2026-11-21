import React from "react";
import {
  Activity,
  ArrowUpRight,
  Clock,
  FlaskConical,
  Lock,
  ShieldCheck,
} from "lucide-react";
import { useI18n } from "../i18n";
import type { OverviewResponse } from "../types";
import { EValueChart } from "./EValueChart";

interface Props {
  data: OverviewResponse;
  onNavigate: (tab: "campaigns" | "shadow" | "auditor" | "mcp" | "settings") => void;
  onNewCampaign: () => void;
}

const stateDot = (state: string) => {
  if (state === "paper" || state === "live_candidate" || state === "live") return "bg-emerald-400";
  if (state === "shadow") return "bg-sky-400";
  return "bg-rose-400";
};

export const OverviewView: React.FC<Props> = ({ data, onNavigate, onNewCampaign }) => {
  const { t } = useI18n();
  const { kpis, featured_shadow, recent_events, scheduler } = data;

  return (
    <div className="space-y-6">
      {/* Header row (Max 3 top-level actions) */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
            {t("overview.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("overview.subtitle")}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <button
            onClick={() => onNavigate("auditor")}
            className="rounded-lg border border-zinc-700 bg-[#1a1a22] px-3.5 py-2 text-sm font-medium text-zinc-100 transition hover:bg-[#24242f] whitespace-nowrap"
          >
            {t("overview.auditCta")}
          </button>
          <button
            onClick={onNewCampaign}
            className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 shadow-sm transition hover:bg-white whitespace-nowrap"
          >
            {t("overview.newCampaign")}
          </button>
        </div>
      </div>

      {/* Security reminder if no admin password set */}
      {!data.auth_enabled && (
        <div className="flex items-center justify-between rounded-lg border border-zinc-700/80 bg-[#16161d] px-4 py-3 text-sm text-zinc-300">
          <div className="flex items-center gap-2.5">
            <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400" />
            <span>
              {t("overview.openAuthPrefix")}{" "}
              <code className="rounded bg-[#09090b] px-1.5 py-0.5 font-mono text-xs text-zinc-100">
                QUANTSEAL_ADMIN_PASSWORD
              </code>{" "}
              {t("overview.openAuthSuffix")}
            </span>
          </div>
        </div>
      )}

      {/* 4-column KPI Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span>{t("overview.kpi.sealed")}</span>
            <Lock className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
          </div>
          <div className="mt-3 flex items-baseline gap-2 tabular-nums">
            <span className="text-3xl font-bold text-zinc-100">{kpis.sealed_campaigns}</span>
            <span className="text-xs text-zinc-400">
              / {kpis.total_campaigns} {t("overview.kpi.total")}
            </span>
          </div>
          <p className="mt-2 text-xs text-zinc-400">
            {kpis.pending_validation} {t("overview.kpi.awaitingSeal")}
          </p>
        </div>

        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span>{t("overview.kpi.peakE")}</span>
            <Activity className="h-4 w-4 text-sky-400" strokeWidth={1.75} />
          </div>
          <div className="mt-3 flex items-baseline gap-2 tabular-nums">
            <span className="text-3xl font-bold text-zinc-100">
              {kpis.highest_peak_evalue.toFixed(1)}x
            </span>
            <span className="text-xs text-zinc-400">{t("overview.kpi.martingale")}</span>
          </div>
          <p className="mt-2 text-xs text-zinc-400">{t("overview.kpi.gatesNote")}</p>
        </div>

        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span>{t("overview.kpi.ladder")}</span>
            <ShieldCheck className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
          </div>
          <div className="mt-3 flex items-baseline gap-2 tabular-nums">
            <span className="text-3xl font-bold text-zinc-100">{kpis.active_shadow_strategies}</span>
            <span className="text-xs text-zinc-400">{t("overview.kpi.active")}</span>
          </div>
          <p className="mt-2 text-xs text-zinc-400">
            {kpis.promoted_strategies} {t("overview.kpi.promoted")} · {kpis.retired_strategies}{" "}
            {t("overview.kpi.retired")}
          </p>
        </div>

        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span>{t("overview.kpi.integrity")}</span>
            <FlaskConical className="h-4 w-4 text-zinc-300" strokeWidth={1.75} />
          </div>
          <div className="mt-3 font-mono text-lg font-semibold text-zinc-100">
            {data.engine_code_hash}
          </div>
          <p className="mt-2 text-xs text-zinc-400">
            LLM:{" "}
            {data.llm_configured ? (
              <span className="text-emerald-400">
                {data.llm_provider} ({data.llm_model})
              </span>
            ) : (
              <span>{t("overview.kpi.byokUnset")}</span>
            )}
          </p>
        </div>
      </div>

      {/* Main 12-col split: Featured E-value curve + Governance Event Ledger */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg lg:col-span-8">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    featured_shadow ? stateDot(featured_shadow.state) : "bg-zinc-600"
                  }`}
                />
                <h3 className="truncate text-lg font-bold text-zinc-100">
                  {featured_shadow ? featured_shadow.title : t("overview.featuredFallback")}
                </h3>
              </div>
              {featured_shadow && (
                <p className="mt-0.5 font-mono text-xs text-zinc-400">
                  {featured_shadow.strategy_key} · {t("campaigns.status")}{" "}
                  {featured_shadow.state.toUpperCase()} · {featured_shadow.observations_count}{" "}
                  {t("overview.obs")} · {t("shadow.excess")}{" "}
                  {featured_shadow.cumulative_excess_pct >= 0 ? "+" : ""}
                  {featured_shadow.cumulative_excess_pct.toFixed(2)}%
                </p>
              )}
            </div>
            <button
              onClick={() => onNavigate("shadow")}
              className="flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 bg-[#1a1a22] px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-[#24242f] whitespace-nowrap"
            >
              {t("overview.ladderBtn")} <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <EValueChart
            series={featured_shadow?.series || []}
            shadowThreshold={featured_shadow?.shadow_threshold || 20}
            liveThreshold={featured_shadow?.live_threshold || 100}
          />
        </div>

        <div className="flex flex-col rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg lg:col-span-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="text-lg font-bold text-zinc-100">{t("overview.ledgerTitle")}</h3>
            <span className="flex shrink-0 items-center gap-1.5 font-mono text-xs text-zinc-400 whitespace-nowrap">
              <Clock className="h-3.5 w-3.5" />
              {scheduler.running ? t("overview.schedActive") : t("overview.schedManual")}
            </span>
          </div>

          <div className="max-h-[340px] flex-1 space-y-2.5 overflow-y-auto pr-1">
            {recent_events.length === 0 ? (
              <p className="text-sm text-zinc-500">{t("overview.noEvents")}</p>
            ) : (
              recent_events.map((ev) => (
                <div
                  key={ev.id}
                  className="rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-xs"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-mono uppercase text-zinc-400">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          ev.level === "error"
                            ? "bg-rose-400"
                            : ev.level === "warning"
                            ? "bg-amber-400"
                            : "bg-emerald-400"
                        }`}
                      />
                      {ev.category}
                    </span>
                    <span className="font-mono text-[11px] text-zinc-500">
                      {ev.created_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </div>
                  <p className="leading-relaxed text-zinc-200">{ev.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
