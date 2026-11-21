import React, { useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { CampaignSummaryItem } from "../types";

interface Props {
  existingCampaigns: CampaignSummaryItem[];
  llmConfigured: boolean;
  onClose: () => void;
  onCreated: () => Promise<void>;
}

export const NewCampaignModal: React.FC<Props> = ({
  existingCampaigns,
  llmConfigured,
  onClose,
  onCreated,
}) => {
  const { t } = useI18n();
  const defaultId = `exp-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-${Math.floor(
    100 + Math.random() * 900
  )}`;
  const [campaignId, setCampaignId] = useState(defaultId);
  const [source, setSource] = useState("demo");
  const [costPreset, setCostPreset] = useState("us_equities");
  const [symbolsText, setSymbolsText] = useState("SPY,QQQ,IWM,XLK,XLF,XLE,XLV,GLD,TLT");
  const [priorId, setPriorId] = useState("");
  const [devOnly, setDevOnly] = useState(true);
  const [useLlm, setUseLlm] = useState(llmConfigured);
  const [useMcp, setUseMcp] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.createCampaign({
        campaign_id: campaignId.trim(),
        source,
        cost_preset: costPreset,
        symbols: symbolsText
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
        prior_campaign_id: priorId || null,
        development_only: devOnly,
        use_llm: useLlm,
        use_mcp: useMcp,
        max_ai_variants: useLlm ? 3 : 0,
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create campaign");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div className="w-full max-w-lg rounded-xl border border-zinc-700 bg-[#16161d] p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-zinc-100">{t("newCamp.title")}</h3>
            <p className="text-xs text-zinc-400">{t("newCamp.subtitle")}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
              {t("newCamp.id")}
            </label>
            <input
              type="text"
              required
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {t("newCamp.source")}
              </label>
              <select
                value={source}
                onChange={(e) => {
                  const v = e.target.value;
                  setSource(v);
                  if (v === "crypto") {
                    setCostPreset("crypto_spot");
                    setSymbolsText("BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,AVAXUSDT");
                  } else if (v === "yahoo") {
                    setCostPreset("us_equities");
                    setSymbolsText("SPY,QQQ,IWM,XLK,XLF,XLE,XLV,GLD,TLT");
                  }
                }}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              >
                <option value="demo">{t("newCamp.sourceDemo")}</option>
                <option value="yahoo">{t("newCamp.sourceYahoo")}</option>
                <option value="crypto">{t("newCamp.sourceCrypto")}</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {t("newCamp.costPreset")}
              </label>
              <select
                value={costPreset}
                onChange={(e) => setCostPreset(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              >
                <option value="us_equities">{t("newCamp.costUs")}</option>
                <option value="crypto_spot">{t("newCamp.costCrypto")}</option>
                <option value="tw_equities">{t("newCamp.costTw")}</option>
                <option value="custom">{t("newCamp.costCustom")}</option>
              </select>
            </div>
          </div>

          {source !== "demo" && (
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {t("newCamp.symbols")}
              </label>
              <input
                type="text"
                value={symbolsText}
                onChange={(e) => setSymbolsText(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
              {t("newCamp.prior")}
            </label>
            <select
              value={priorId}
              onChange={(e) => setPriorId(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
            >
              <option value="">{t("newCamp.priorNone")}</option>
              {existingCampaigns.map((c) => (
                <option key={c.campaign_id} value={c.campaign_id}>
                  {c.campaign_id} ({c.validation_evaluated_once ? t("campaigns.sealed") : t("campaigns.pending")})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2 rounded-lg border border-zinc-800 bg-[#09090b] p-3 text-sm">
            <label className="flex items-center gap-2.5 text-zinc-200">
              <input
                type="checkbox"
                checked={devOnly}
                onChange={(e) => setDevOnly(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900"
              />
              <span>{t("newCamp.devOnly")}</span>
            </label>
            <label className="flex items-center gap-2.5 text-zinc-200">
              <input
                type="checkbox"
                checked={useLlm}
                disabled={!llmConfigured}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 disabled:opacity-40"
              />
              <span className={!llmConfigured ? "text-zinc-500" : ""}>
                {t("newCamp.useLlm")} {!llmConfigured && t("newCamp.llmUnset")}
              </span>
            </label>
            <label className="flex items-center gap-2.5 text-zinc-200">
              <input
                type="checkbox"
                checked={useMcp}
                onChange={(e) => setUseMcp(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900"
              />
              <span>{t("newCamp.useMcp")}</span>
            </label>
          </div>

          {error && (
            <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-xs text-rose-400">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-700 bg-[#1a1a22] px-4 py-2 text-sm text-zinc-200 hover:bg-[#24242f]"
            >
              {t("newCamp.cancel")}
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
            >
              {loading ? t("newCamp.running") : t("newCamp.run")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
