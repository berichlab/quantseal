import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Code2,
  Lock,
  Plus,
  ShieldAlert,
  Unlock,
} from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { CampaignDetail, CampaignSummaryItem, ExperimentItem } from "../types";

interface Props {
  campaigns: CampaignSummaryItem[];
  onRefresh: () => Promise<void>;
  onNewCampaign: () => void;
  onNavigateShadow: () => void;
}

const verdictDot = (status: string) => {
  if (status === "qualified_for_shadow" || status === "passed_development" || status === "passed_historical_validation") {
    return "bg-emerald-400";
  }
  if (status.includes("pending") || status.includes("inconclusive") || status === "control_reference") {
    return "bg-amber-400";
  }
  return "bg-rose-400";
};

export const CampaignsView: React.FC<Props> = ({
  campaigns,
  onRefresh,
  onNewCampaign,
  onNavigateShadow,
}) => {
  const { t } = useI18n();
  const [selectedId, setSelectedId] = useState<string | null>(campaigns[0]?.campaign_id || null);
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedSpec, setExpandedSpec] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId && campaigns.length > 0) {
      setSelectedId(campaigns[0].campaign_id);
    }
  }, [campaigns, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getCampaign(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load campaign");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleUnlockValidation = async () => {
    if (!detail) return;
    setBusyAction("validate");
    setError(null);
    try {
      const updated = await api.validateCampaignOnce(detail.campaign_id);
      setDetail(updated);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleEnroll = async (exp: ExperimentItem) => {
    if (!detail) return;
    setBusyAction(exp.spec_id);
    setError(null);
    try {
      await api.enrollSpec(detail.campaign_id, exp.spec_id);
      await onRefresh();
      onNavigateShadow();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrollment failed");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
            {t("campaigns.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("campaigns.subtitle")}
          </p>
        </div>
        <button
          onClick={onNewCampaign}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-white whitespace-nowrap"
        >
          <Plus className="h-4 w-4" /> {t("overview.newCampaign")}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-4 py-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left column: Campaign list */}
        <div className="space-y-3 lg:col-span-4">
          {campaigns.map((c) => {
            const active = c.campaign_id === selectedId;
            return (
              <button
                key={c.campaign_id}
                onClick={() => setSelectedId(c.campaign_id)}
                className={`w-full rounded-xl p-4 text-left transition ${
                  active
                    ? "border-2 border-zinc-100 bg-[#22222c] shadow-2xl"
                    : "border border-zinc-700/80 bg-[#16161d] hover:bg-[#1c1c25]"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-sm font-bold text-zinc-100">
                    {c.campaign_id}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-300 whitespace-nowrap">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        c.validation_contaminated
                          ? "bg-rose-400"
                          : c.validation_evaluated_once
                          ? "bg-emerald-400"
                          : "bg-amber-400"
                      }`}
                    />
                    {c.validation_contaminated
                      ? t("campaigns.contaminated")
                      : c.validation_evaluated_once
                      ? t("campaigns.sealed")
                      : t("campaigns.pending")}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3 font-mono text-[11px] text-zinc-400">
                  <span>{c.source}</span>
                  <span>·</span>
                  <span>{c.cost_preset}</span>
                  <span>·</span>
                  <span>
                    {c.dev_passed}/{c.total_candidates} {t("campaigns.devShort")}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2 font-mono text-[10px] text-zinc-500">
                  <span>data:{c.data_hash.slice(0, 8)}</span>
                  <span>cfg:{c.config_hash.slice(0, 8)}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right column: Selected Campaign Detail */}
        <div className="space-y-5 lg:col-span-8">
          {loading || !detail ? (
            <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-8 text-center text-sm text-zinc-400">
              {loading ? t("campaigns.loading") : t("campaigns.selectPrompt")}
            </div>
          ) : (
            <>
              {/* Seal Header Card */}
              <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2.5">
                      {detail.validation_evaluated_once ? (
                        <Lock className="h-5 w-5 text-emerald-400" strokeWidth={1.75} />
                      ) : (
                        <Unlock className="h-5 w-5 text-amber-400" strokeWidth={1.75} />
                      )}
                      <h3 className="font-mono text-xl font-bold text-zinc-100">
                        {detail.campaign_id}
                      </h3>
                    </div>
                    <p className="mt-1 text-xs text-zinc-400">
                      {t("campaigns.status")}{" "}
                      <span className="font-mono text-zinc-200">{detail.status}</span> ·{" "}
                      {detail.coverage_report.asset_count} {t("campaigns.assets")} ·{" "}
                      {detail.coverage_report.availability_convention}
                    </p>
                  </div>

                  {!detail.validation_evaluated_once && (
                    <button
                      onClick={handleUnlockValidation}
                      disabled={busyAction === "validate"}
                      className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-white disabled:opacity-50 whitespace-nowrap"
                    >
                      {busyAction === "validate"
                        ? t("campaigns.unlocking")
                        : t("campaigns.unlockBtn")}
                    </button>
                  )}
                </div>

                {detail.validation_holdout_contaminated && (
                  <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-zinc-700 bg-[#09090b] p-3 text-xs text-rose-300">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
                    <div>
                      <span className="font-semibold text-rose-400">
                        {t("campaigns.contamTitle")}
                      </span>{" "}
                      {t("campaigns.contamBody1")}{" "}
                      <code className="font-mono">{detail.prior_campaign_id}</code>{" "}
                      {t("campaigns.contamBody2")}{" "}
                      <code className="font-mono">{detail.contamination_label}</code>.
                    </div>
                  </div>
                )}

                {/* Cryptographic Seal Strip */}
                <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                      {t("campaigns.configHash")}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-zinc-200">{detail.config_hash}</div>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                      {t("campaigns.dataHash")}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-zinc-200">{detail.data_hash}</div>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                      {t("campaigns.codeHash")}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-zinc-200">{detail.code_hash}</div>
                  </div>
                </div>

                {/* Temporal Partitions */}
                <div className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <span className="text-zinc-500">{t("campaigns.discPart")}</span>
                    <div className="mt-0.5 font-mono text-zinc-200">
                      {detail.partitions.discovery_start} .. {detail.partitions.discovery_end}
                    </div>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <span className="text-zinc-500">{t("campaigns.valPart")}</span>
                    <div className="mt-0.5 font-mono text-zinc-200">
                      {detail.partitions.validation_start} .. {detail.partitions.validation_end}
                    </div>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2">
                    <span className="text-zinc-500">{t("campaigns.sealedPart")}</span>
                    <div className="mt-0.5 font-mono text-zinc-200">
                      {detail.partitions.sealed_start
                        ? `${detail.partitions.sealed_start} .. ${detail.partitions.sealed_end}`
                        : "—"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Experiments & 4-Arm Falsification Cards */}
              <div className="space-y-4">
                {detail.experiments.map((exp) => {
                  const devFull = exp.development.arms.full;
                  const valFull = exp.validation?.arms.full;
                  const isOpen = expandedSpec === exp.spec_id;
                  return (
                    <div
                      key={exp.spec_id}
                      className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${verdictDot(exp.outcome.final_status)}`} />
                            <h4 className="text-base font-bold text-zinc-100">{exp.title}</h4>
                            <span className="rounded border border-zinc-700 bg-[#09090b] px-1.5 py-0.5 font-mono text-[10px] uppercase text-zinc-300">
                              {exp.source}
                            </span>
                          </div>
                          <p className="mt-1 font-mono text-xs text-zinc-400">
                            {exp.spec_id} · ast:{exp.fingerprint} · {t("campaigns.verdictLabel")}{" "}
                            <span className="text-zinc-200">{exp.outcome.final_status}</span>
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setExpandedSpec(isOpen ? null : exp.spec_id)}
                            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-[#1a1a22] px-2.5 py-1.5 text-xs text-zinc-200 hover:bg-[#24242f] whitespace-nowrap"
                          >
                            <Code2 className="h-3.5 w-3.5" />
                            {isOpen ? t("campaigns.hideAst") : t("campaigns.jsonAst")}
                          </button>
                          {exp.source !== "control" && (
                            <button
                              onClick={() => handleEnroll(exp)}
                              disabled={busyAction === exp.spec_id}
                              className="rounded-lg border border-zinc-700 bg-[#1a1a22] px-3 py-1.5 text-xs font-medium text-zinc-100 hover:bg-[#24242f] disabled:opacity-50 whitespace-nowrap"
                            >
                              {busyAction === exp.spec_id
                                ? t("campaigns.enrolling")
                                : t("campaigns.trackShadow")}
                            </button>
                          )}
                        </div>
                      </div>

                      <p className="mt-2.5 text-sm text-zinc-300">{exp.outcome.reason}</p>

                      {/* 4-Arm Falsification Matrix */}
                      <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-800 bg-[#09090b]">
                        <table className="w-full text-left text-xs tabular-nums">
                          <thead className="border-b border-zinc-800 text-[11px] uppercase tracking-wider text-zinc-400">
                            <tr>
                              <th className="px-3 py-2">{t("campaigns.armHeader")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.trades")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.avgNet")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.cumPort")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.pf")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.stress15")}</th>
                              <th className="px-3 py-2 text-right">{t("campaigns.beatsRef")}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
                            {(["full", "baseline", "ablation", "reverse_control"] as const).map(
                              (arm) => {
                                const m = exp.development.arms[arm];
                                const cmp =
                                  arm === "full"
                                    ? null
                                    : exp.development.pairwise_comparisons[arm];
                                const stress15 = m?.cost_stress?.["1.5x"];
                                return (
                                  <tr key={arm} className={arm === "full" ? "bg-[#121217]" : ""}>
                                    <td className="px-3 py-2 font-mono font-semibold text-zinc-100">
                                      {arm}
                                    </td>
                                    <td className="px-3 py-2 text-right">{m?.n_trades ?? 0}</td>
                                    <td className="px-3 py-2 text-right">
                                      {m ? `${m.avg_net_return_pct >= 0 ? "+" : ""}${m.avg_net_return_pct.toFixed(2)}%` : "—"}
                                    </td>
                                    <td className="px-3 py-2 text-right">
                                      {m
                                        ? `${m.cumulative_portfolio_return_pct >= 0 ? "+" : ""}${m.cumulative_portfolio_return_pct.toFixed(2)}%`
                                        : "—"}
                                    </td>
                                    <td className="px-3 py-2 text-right">
                                      {m ? m.profit_factor.toFixed(2) : "—"}
                                    </td>
                                    <td className="px-3 py-2 text-right">
                                      {stress15 ? (
                                        <span className={stress15.passed ? "text-emerald-400" : "text-rose-400"}>
                                          {stress15.avg_net_return >= 0 ? "+" : ""}
                                          {stress15.avg_net_return.toFixed(2)}%
                                        </span>
                                      ) : (
                                        "—"
                                      )}
                                    </td>
                                    <td className="px-3 py-2 text-right">
                                      {arm === "full" ? (
                                        <span className="font-mono text-zinc-500">
                                          {t("campaigns.target")}
                                        </span>
                                      ) : cmp?.beat_reference ? (
                                        <span className="inline-flex items-center gap-1 text-emerald-400">
                                          <CheckCircle2 className="h-3.5 w-3.5" /> {t("campaigns.yes")}
                                        </span>
                                      ) : (
                                        <span className="inline-flex items-center gap-1 text-rose-400">
                                          <AlertTriangle className="h-3.5 w-3.5" /> {t("campaigns.no")}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                );
                              }
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* Frozen Validation Summary Strip (if evaluated) */}
                      {valFull && (
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2 text-xs">
                          <span className="font-mono text-zinc-400">
                            {t("campaigns.singleShotVal")}{" "}
                            <strong
                              className={
                                exp.validation?.verdict === "passed_historical_validation"
                                  ? "text-emerald-400"
                                  : "text-rose-400"
                              }
                            >
                              {exp.validation?.verdict}
                            </strong>
                          </span>
                          <span className="font-mono text-zinc-300 tabular-nums">
                            n={valFull.n_trades} · cum{" "}
                            {valFull.cumulative_portfolio_return_pct >= 0 ? "+" : ""}
                            {valFull.cumulative_portfolio_return_pct.toFixed(2)}% · PF{" "}
                            {valFull.profit_factor.toFixed(2)} · Boot CI [
                            {valFull.bootstrap_ci.ci_lower.toFixed(2)}%,{" "}
                            {valFull.bootstrap_ci.ci_upper.toFixed(2)}%]
                          </span>
                        </div>
                      )}

                      {/* Novelty & Discovery Footnote */}
                      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                        <span>
                          {t("campaigns.novelty")} {exp.novelty.explanation}
                        </span>
                        <span className="font-mono">
                          {t("campaigns.boundaryExcluded")} {devFull?.boundary_excluded_signals ?? 0}
                        </span>
                      </div>

                      {isOpen && (
                        <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-zinc-800 bg-[#09090b] p-3 font-mono text-xs text-zinc-300">
                          {JSON.stringify(exp.spec, null, 2)}
                        </pre>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
