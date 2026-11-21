import React, { useEffect, useState } from "react";
import { Activity, PlusCircle, RefreshCw } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { ShadowStrategyDetail, ShadowStrategyItem } from "../types";
import { EValueChart } from "./EValueChart";

interface Props {
  strategies: ShadowStrategyItem[];
  onRefresh: () => Promise<void>;
}

const badgeColor = (state: string) => {
  if (state === "live" || state === "live_candidate") return "bg-emerald-400";
  if (state === "paper") return "bg-sky-400";
  if (state === "shadow") return "bg-amber-400";
  return "bg-rose-400";
};

export const ShadowLadderView: React.FC<Props> = ({ strategies, onRefresh }) => {
  const { t } = useI18n();
  const [selectedKey, setSelectedKey] = useState<string | null>(
    strategies[0]?.strategy_key || null
  );
  const [detail, setDetail] = useState<ShadowStrategyDetail | null>(null);
  const [obsDate, setObsDate] = useState(new Date().toISOString().slice(0, 10));
  const [stratRet, setStratRet] = useState("0.85");
  const [benchRet, setBenchRet] = useState("0.15");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedKey && strategies.length > 0) {
      setSelectedKey(strategies[0].strategy_key);
    }
  }, [strategies, selectedKey]);

  const loadDetail = async (key: string) => {
    const d = await api.getShadow(key);
    setDetail(d);
  };

  useEffect(() => {
    if (selectedKey) {
      loadDetail(selectedKey).catch(() => {});
    }
  }, [selectedKey]);

  const handleAddObservation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedKey) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.addObservation(selectedKey, {
        obs_date: obsDate,
        strategy_return_pct: parseFloat(stratRet),
        benchmark_return_pct: parseFloat(benchRet),
        note,
      });
      await loadDetail(selectedKey);
      await onRefresh();
      setNote("");
      setMsg(t("shadow.savedMsg"));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to save observation");
    } finally {
      setSaving(false);
    }
  };

  const handleReconcile = async () => {
    setReconciling(true);
    try {
      const r = await api.runShadowReconcile();
      await onRefresh();
      if (selectedKey) await loadDetail(selectedKey);
      setMsg(
        `${t("shadow.reconciled")} ${r.checked} ${t("shadow.strategies")} (${r.transitions} ${t("shadow.transitions")}).`
      );
    } finally {
      setReconciling(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
            {t("shadow.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("shadow.subtitle")}
          </p>
        </div>
        <button
          onClick={handleReconcile}
          disabled={reconciling}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-zinc-700 bg-[#1a1a22] px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-[#24242f] disabled:opacity-50 whitespace-nowrap"
        >
          <RefreshCw className={`h-4 w-4 ${reconciling ? "animate-spin" : ""}`} />
          {t("shadow.reconcile")}
        </button>
      </div>

      {msg && (
        <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-4 py-2.5 text-sm text-zinc-200">
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Ladder list */}
        <div className="space-y-3 lg:col-span-4">
          {strategies.map((s) => {
            const active = s.strategy_key === selectedKey;
            return (
              <button
                key={s.strategy_key}
                onClick={() => setSelectedKey(s.strategy_key)}
                className={`w-full rounded-xl p-4 text-left transition ${
                  active
                    ? "border-2 border-zinc-100 bg-[#22222c] shadow-2xl"
                    : "border border-zinc-700/80 bg-[#16161d] hover:bg-[#1c1c25]"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-bold text-zinc-100">{s.title}</span>
                  <span className="flex items-center gap-1.5 font-mono text-[11px] uppercase text-zinc-200 whitespace-nowrap">
                    <span className={`h-2 w-2 rounded-full ${badgeColor(s.state)}`} />
                    {s.state}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-xs tabular-nums text-zinc-300">
                  <div>
                    <div className="text-[10px] text-zinc-500">{t("shadow.peakE")}</div>
                    <div>{s.peak_evalue.toFixed(2)}x</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-zinc-500">{t("shadow.excess")}</div>
                    <div className={s.cumulative_excess_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                      {s.cumulative_excess_pct >= 0 ? "+" : ""}
                      {s.cumulative_excess_pct.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-zinc-500">{t("shadow.mdd")}</div>
                    <div>{s.max_drawdown_pct.toFixed(1)}%</div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right: E-value detail & forward tick entry */}
        <div className="space-y-5 lg:col-span-8">
          {!detail ? (
            <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-8 text-center text-sm text-zinc-400">
              {t("shadow.selectPrompt")}
            </div>
          ) : (
            <>
              <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Activity className="h-5 w-5 shrink-0 text-sky-400" strokeWidth={1.75} />
                      <h3 className="truncate text-lg font-bold text-zinc-100">{detail.title}</h3>
                    </div>
                    <p className="mt-1 font-mono text-xs text-zinc-400">
                      {detail.strategy_key} · {t("campaigns.status")}{" "}
                      {detail.state.toUpperCase()} · {detail.observations_count}{" "}
                      {t("shadow.forwardObs")}
                    </p>
                  </div>
                  <div className="shrink-0 text-right font-mono tabular-nums">
                    <div className="text-2xl font-bold text-zinc-100">
                      {detail.peak_evalue.toFixed(2)}x
                    </div>
                    <div className="text-[11px] text-zinc-400 whitespace-nowrap">
                      {t("shadow.peakLabel")}
                    </div>
                  </div>
                </div>

                <p className="mb-4 rounded-lg border border-zinc-800 bg-[#09090b] px-3 py-2 text-xs text-zinc-300">
                  {detail.last_reason}
                </p>

                <EValueChart
                  series={detail.series}
                  shadowThreshold={detail.shadow_threshold}
                  liveThreshold={detail.live_threshold}
                  height={240}
                />
              </div>

              {/* Append Forward OOS Observation */}
              <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
                <h4 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-zinc-200">
                  <PlusCircle className="h-4 w-4 text-zinc-300" />
                  {t("shadow.recordTitle")}
                </h4>
                <form
                  onSubmit={handleAddObservation}
                  className="grid grid-cols-1 gap-3 sm:grid-cols-12"
                >
                  <div className="sm:col-span-3">
                    <label className="mb-1 block text-[11px] text-zinc-400">{t("shadow.date")}</label>
                    <input
                      type="date"
                      required
                      value={obsDate}
                      onChange={(e) => setObsDate(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-2.5 py-1.5 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-[11px] text-zinc-400">{t("shadow.stratPct")}</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={stratRet}
                      onChange={(e) => setStratRet(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-2.5 py-1.5 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-[11px] text-zinc-400">{t("shadow.benchPct")}</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={benchRet}
                      onChange={(e) => setBenchRet(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-2.5 py-1.5 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                  <div className="sm:col-span-3">
                    <label className="mb-1 block text-[11px] text-zinc-400">{t("shadow.note")}</label>
                    <input
                      type="text"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={t("shadow.optional")}
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-2.5 py-1.5 text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                  <div className="flex items-end sm:col-span-2">
                    <button
                      type="submit"
                      disabled={saving}
                      className="w-full rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50 whitespace-nowrap"
                    >
                      {saving ? t("shadow.saving") : t("shadow.append")}
                    </button>
                  </div>
                </form>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
