import React, { useState } from "react";
import { CheckCircle2, ShieldAlert, Upload } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { AuditResponse } from "../types";
import { EValueChart } from "./EValueChart";

const SAMPLE_CSV = `entry_date,symbol,sector,gross,net
2026-04-01,SPY,Broad,1.40,1.22
2026-04-02,QQQ,Tech,2.10,1.92
2026-04-03,XLF,Financials,-0.80,-0.98
2026-04-06,XLE,Energy,1.95,1.77
2026-04-07,XLV,Healthcare,1.15,0.97
2026-04-08,IWM,SmallCap,-1.10,-1.28
2026-04-09,XLK,Tech,2.30,2.12
2026-04-10,XLI,Industrials,1.45,1.27
2026-04-13,XLP,Staples,0.95,0.77
2026-04-14,XLY,Discretionary,1.70,1.52
2026-04-15,GLD,Commodities,-0.55,-0.73
2026-04-16,TLT,Rates,1.25,1.07
2026-04-17,SPY,Broad,1.80,1.62
2026-04-20,QQQ,Tech,1.55,1.37
2026-04-21,XLE,Energy,-0.95,-1.13
2026-04-22,XLF,Financials,1.90,1.72
2026-04-23,XLV,Healthcare,1.35,1.17
2026-04-24,IWM,SmallCap,2.05,1.87
2026-04-27,XLK,Tech,-0.65,-0.83
2026-04-28,XLI,Industrials,1.60,1.42`;

export const GateAuditorView: React.FC = () => {
  const { t } = useI18n();
  const [csvText, setCsvText] = useState(SAMPLE_CSV);
  const [minTrades, setMinTrades] = useState("15");
  const [maxAssetPct, setMaxAssetPct] = useState("25");
  const [result, setResult] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAudit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.auditTrades({
        csv_text: csvText,
        min_trades: parseInt(minTrades, 10) || 15,
        max_single_asset_pct: parseFloat(maxAssetPct) || 25,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audit failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
            {t("auditor.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("auditor.subtitle")}
          </p>
        </div>
        <button
          onClick={handleAudit}
          disabled={loading}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50 whitespace-nowrap"
        >
          <Upload className="h-4 w-4" />
          {loading ? t("auditor.running") : t("auditor.run")}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Input CSV */}
        <div className="space-y-4 rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg lg:col-span-5">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {t("auditor.minTrades")}
              </label>
              <input
                type="number"
                value={minTrades}
                onChange={(e) => setMinTrades(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-1.5 font-mono text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {t("auditor.maxAsset")}
              </label>
              <input
                type="number"
                value={maxAssetPct}
                onChange={(e) => setMaxAssetPct(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-1.5 font-mono text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
              {t("auditor.csvLabel")}
            </label>
            <textarea
              rows={15}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-[#09090b] p-3 font-mono text-xs text-zinc-200 focus:border-zinc-300 focus:outline-none"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-xs text-rose-400">
              {error}
            </div>
          )}
        </div>

        {/* Right: Verdict Report */}
        <div className="space-y-4 lg:col-span-7">
          {!result ? (
            <div className="flex h-full min-h-[320px] items-center justify-center rounded-xl border border-zinc-700/80 bg-[#16161d] p-8 text-center text-sm text-zinc-400">
              {t("auditor.emptyPrompt")}
            </div>
          ) : (
            <>
              <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    {result.passed ? (
                      <CheckCircle2 className="h-6 w-6 text-emerald-400" strokeWidth={1.75} />
                    ) : (
                      <ShieldAlert className="h-6 w-6 text-rose-400" strokeWidth={1.75} />
                    )}
                    <div>
                      <h3 className="text-lg font-bold text-zinc-100">
                        {t("auditor.verdict")} {result.verdict}
                      </h3>
                      <p className="font-mono text-xs text-zinc-400">
                        n={result.summary.n_trades} · {t("auditor.avgNet")}{" "}
                        {result.summary.avg_net_return_pct >= 0 ? "+" : ""}
                        {result.summary.avg_net_return_pct.toFixed(3)}% · PF{" "}
                        {result.summary.profit_factor.toFixed(2)} · {t("auditor.win")}{" "}
                        {result.summary.win_rate_pct.toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>

                {result.rejection_reasons.length > 0 && (
                  <ul className="mt-4 space-y-1.5 rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-xs text-rose-300">
                    {result.rejection_reasons.map((r, i) => (
                      <li key={i}>· {r}</li>
                    ))}
                  </ul>
                )}

                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-xs">
                    <div className="text-zinc-500">{t("auditor.bootCi")}</div>
                    <div
                      className={`mt-1 font-mono text-sm font-bold ${
                        result.bootstrap_ci.passed ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      [{result.bootstrap_ci.ci_lower.toFixed(2)}%,{" "}
                      {result.bootstrap_ci.ci_upper.toFixed(2)}%]
                    </div>
                    <div className="mt-0.5 text-[11px] text-zinc-500">
                      {result.bootstrap_ci.n_clusters} {t("auditor.clusters")}
                    </div>
                  </div>

                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-xs">
                    <div className="text-zinc-500">{t("auditor.costStress")}</div>
                    <div className="mt-1 font-mono text-sm font-bold text-zinc-100">
                      {result.cost_stress["1.5x"]?.avg_net_return.toFixed(2)}% /{" "}
                      {result.cost_stress["2x"]?.avg_net_return.toFixed(2)}%
                    </div>
                    <div className="mt-0.5 text-[11px] text-zinc-500">
                      1.5x PF: {result.cost_stress["1.5x"]?.profit_factor.toFixed(2)}
                    </div>
                  </div>

                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-xs">
                    <div className="text-zinc-500">{t("auditor.topAsset")}</div>
                    <div
                      className={`mt-1 font-mono text-sm font-bold ${
                        result.concentration.passed ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {result.concentration.max_asset_pct.toFixed(1)}%
                    </div>
                    <div className="mt-0.5 text-[11px] text-zinc-500">
                      {t("auditor.top")} {result.concentration.top_asset || "—"}
                    </div>
                  </div>
                </div>
              </div>

              <EValueChart
                series={result.evalue.series || []}
                shadowThreshold={20}
                liveThreshold={result.evalue.threshold}
                height={200}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
};
