import React, { useState } from "react";
import { Lock, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";

interface Props {
  onSuccess: () => void;
}

export const LoginModal: React.FC<Props> = ({ onSuccess }) => {
  const { locale, setLocale, t } = useI18n();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.login(password);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050507] p-6">
      <div className="w-full max-w-md rounded-xl border border-zinc-700/80 bg-[#16161d] p-8 shadow-2xl">
        <div className="mb-6 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-zinc-700 bg-[#09090b]">
              <ShieldCheck className="h-5 w-5 text-emerald-400" strokeWidth={1.75} />
            </div>
            <div>
              <div className="flex items-baseline gap-2">
                <h1 className="text-xl font-bold tracking-tight text-zinc-100">QuantSeal</h1>
                <span className="font-mono text-[11px] text-zinc-400">by BeRichLab</span>
              </div>
              <p className="text-xs text-zinc-400">{t("app.tagline")}</p>
            </div>
          </div>
          <div className="flex rounded-lg border border-zinc-800 bg-[#09090b] p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setLocale("en")}
              className={`rounded px-2 py-0.5 font-medium ${
                locale === "en" ? "bg-[#22222c] text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLocale("zh-TW")}
              className={`rounded px-2 py-0.5 font-medium ${
                locale === "zh-TW" ? "bg-[#22222c] text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              繁中
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-zinc-400">
              {t("login.label")}
            </label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
              <input
                type="password"
                required
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("login.placeholder")}
                className="w-full rounded-lg border border-zinc-700 bg-[#09090b] py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder-zinc-600 focus:border-zinc-300 focus:outline-none"
              />
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-xs text-rose-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-zinc-100 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-white disabled:opacity-50"
          >
            {loading ? t("login.verifying") : t("login.submit")}
          </button>
        </form>
      </div>
    </div>
  );
};
