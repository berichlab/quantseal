import React, { useEffect, useState } from "react";
import { Bell, Cpu, Save, Timer } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { RuntimeSettingsResponse } from "../types";

export const SettingsView: React.FC<{ onSaved: () => Promise<void> }> = ({ onSaved }) => {
  const { t } = useI18n();
  const [settings, setSettings] = useState<RuntimeSettingsResponse | null>(null);
  const [provider, setProvider] = useState("none");
  const [model, setModel] = useState("gpt-4o-mini");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  const [marketPreset, setMarketPreset] = useState("us_equities");
  const [symbolsText, setSymbolsText] = useState("");

  const [schedEnabled, setSchedEnabled] = useState(true);
  const [shadowCron, setShadowCron] = useState("0 22 * * 1-5");
  const [campaignCron, setCampaignCron] = useState("");

  const [tgToken, setTgToken] = useState("");
  const [tgChat, setTgChat] = useState("");
  const [discordUrl, setDiscordUrl] = useState("");

  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => {
      setSettings(s);
      setProvider(s.llm.provider);
      setModel(s.llm.model);
      setBaseUrl(s.llm.base_url);
      setMarketPreset(s.market.default_preset);
      setSymbolsText(s.market.default_symbols.join(","));
      setSchedEnabled(s.scheduler.enabled);
      setShadowCron(s.scheduler.shadow_cron);
      setCampaignCron(s.scheduler.campaign_cron);
      setTgChat(s.notifications.telegram_chat_id);
    });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);
    try {
      const updated = await api.updateSettings({
        llm: {
          provider,
          model,
          base_url: baseUrl,
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        },
        market: {
          default_preset: marketPreset,
          default_symbols: symbolsText
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        },
        scheduler: {
          enabled: schedEnabled,
          shadow_cron: shadowCron,
          campaign_cron: campaignCron,
        },
        notifications: {
          ...(tgToken.trim() ? { telegram_bot_token: tgToken.trim() } : {}),
          ...(tgChat.trim() ? { telegram_chat_id: tgChat.trim() } : {}),
          ...(discordUrl.trim() ? { discord_webhook_url: discordUrl.trim() } : {}),
        },
      });
      setSettings(updated);
      setApiKey("");
      setTgToken("");
      setDiscordUrl("");
      await onSaved();
      setStatusMsg(t("settings.savedMsg"));
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleTestNotif = async () => {
    setStatusMsg(null);
    const res = await api.testNotification();
    setStatusMsg(
      res.sent.length
        ? `${t("settings.testSent")} ${res.sent.join(", ")}`
        : `${t("settings.testNone")} (${res.status})`
    );
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
            {t("settings.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("settings.subtitle")}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <button
            type="button"
            onClick={handleTestNotif}
            className="rounded-lg border border-zinc-700 bg-[#1a1a22] px-3.5 py-2 text-sm text-zinc-200 hover:bg-[#24242f] whitespace-nowrap"
          >
            {t("settings.testAlert")}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50 whitespace-nowrap"
          >
            <Save className="h-4 w-4" />
            {saving ? t("settings.saving") : t("settings.save")}
          </button>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-4 py-2.5 text-sm text-zinc-200">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* BYOK LLM */}
        <div className="space-y-4 rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-sky-400" strokeWidth={1.75} />
            <h3 className="text-base font-bold text-zinc-100">{t("settings.llmTitle")}</h3>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.provider")}</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              >
                <option value="none">{t("settings.disabled")}</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
                <option value="gemini">Google Gemini</option>
                <option value="openai_compatible">{t("settings.openaiCompat")}</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.model")}</label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-zinc-400">
              {t("settings.apiKey")}{" "}
              {settings?.llm.api_key_configured && (
                <span className="font-mono text-emerald-400">
                  ({t("settings.stored")} {settings.llm.api_key_masked})
                </span>
              )}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={t("settings.apiKeyHint")}
              className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-sm text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-zinc-400">
              {t("settings.baseUrl")}
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://openrouter.ai/api/v1"
              className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
            />
          </div>
        </div>

        {/* 24/7 Scheduler */}
        <div className="space-y-4 rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="flex items-center gap-2">
            <Timer className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
            <h3 className="text-base font-bold text-zinc-100">{t("settings.schedTitle")}</h3>
          </div>

          <label className="flex items-center gap-2.5 text-sm text-zinc-200">
            <input
              type="checkbox"
              checked={schedEnabled}
              onChange={(e) => setSchedEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-600 bg-zinc-900"
            />
            <span>{t("settings.schedEnable")}</span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.shadowCron")}</label>
              <input
                type="text"
                value={shadowCron}
                onChange={(e) => setShadowCron(e.target.value)}
                placeholder="0 22 * * 1-5"
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.campaignCron")}</label>
              <input
                type="text"
                value={campaignCron}
                onChange={(e) => setCampaignCron(e.target.value)}
                placeholder="0 2 * * 6"
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.marketPreset")}</label>
              <select
                value={marketPreset}
                onChange={(e) => setMarketPreset(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
              >
                <option value="us_equities">us_equities</option>
                <option value="crypto_spot">crypto_spot</option>
                <option value="tw_equities">tw_equities</option>
                <option value="custom">custom</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.symbols")}</label>
              <input
                type="text"
                value={symbolsText}
                onChange={(e) => setSymbolsText(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="space-y-4 rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg lg:col-span-2">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-amber-400" strokeWidth={1.75} />
            <h3 className="text-base font-bold text-zinc-100">
              {t("settings.notifTitle")}
            </h3>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-400">
                {t("settings.tgToken")}{" "}
                {settings?.notifications.telegram_configured && (
                  <span className="text-emerald-400">{t("settings.configured")}</span>
                )}
              </label>
              <input
                type="password"
                value={tgToken}
                onChange={(e) => setTgToken(e.target.value)}
                placeholder="123456:ABC-DEF..."
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-400">{t("settings.tgChat")}</label>
              <input
                type="text"
                value={tgChat}
                onChange={(e) => setTgChat(e.target.value)}
                placeholder="-1001234567890"
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-400">
                {t("settings.discord")}{" "}
                {settings?.notifications.discord_configured && (
                  <span className="text-emerald-400">{t("settings.configured")}</span>
                )}
              </label>
              <input
                type="password"
                value={discordUrl}
                onChange={(e) => setDiscordUrl(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>
        </div>
      </div>
    </form>
  );
};
