import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  FlaskConical,
  Globe,
  LayoutDashboard,
  LogOut,
  Plug,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { ApiError, api } from "./api";
import { CampaignsView } from "./components/CampaignsView";
import { GateAuditorView } from "./components/GateAuditorView";
import { LoginModal } from "./components/LoginModal";
import { McpHubView } from "./components/McpHubView";
import { NewCampaignModal } from "./components/NewCampaignModal";
import { OverviewView } from "./components/OverviewView";
import { SettingsView } from "./components/SettingsView";
import { ShadowLadderView } from "./components/ShadowLadderView";
import { useI18n } from "./i18n";
import type {
  AuthStatus,
  CampaignSummaryItem,
  OverviewResponse,
  ShadowStrategyItem,
} from "./types";

type TabKey = "overview" | "campaigns" | "shadow" | "auditor" | "mcp" | "settings";

export const App: React.FC = () => {
  const { locale, setLocale, t } = useI18n();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignSummaryItem[]>([]);
  const [shadows, setShadows] = useState<ShadowStrategyItem[]>([]);
  const [showNewModal, setShowNewModal] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [ov, cp, sh] = await Promise.all([
        api.overview(),
        api.listCampaigns(),
        api.listShadow(),
      ]);
      setOverview(ov);
      setCampaigns(cp.campaigns);
      setShadows(sh.strategies);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuth((prev) => (prev ? { ...prev, authenticated: false } : null));
      }
    }
  }, []);

  useEffect(() => {
    api.authStatus().then((st) => {
      setAuth(st);
      if (st.authenticated) {
        loadAll();
      }
    });
  }, [loadAll]);

  if (!auth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050507] font-mono text-sm text-zinc-400">
        {t("app.initializing")}
      </div>
    );
  }

  if (auth.auth_enabled && !auth.authenticated) {
    return (
      <LoginModal
        onSuccess={() => {
          setAuth({ ...auth, authenticated: true });
          loadAll();
        }}
      />
    );
  }

  const navItems: Array<{ key: TabKey; label: string; icon: React.ReactNode }> = [
    { key: "overview", label: t("nav.overview"), icon: <LayoutDashboard className="h-4 w-4" strokeWidth={1.75} /> },
    { key: "campaigns", label: t("nav.campaigns"), icon: <FlaskConical className="h-4 w-4" strokeWidth={1.75} /> },
    { key: "shadow", label: t("nav.shadow"), icon: <Activity className="h-4 w-4" strokeWidth={1.75} /> },
    { key: "auditor", label: t("nav.auditor"), icon: <SlidersHorizontal className="h-4 w-4" strokeWidth={1.75} /> },
    { key: "mcp", label: t("nav.mcp"), icon: <Plug className="h-4 w-4" strokeWidth={1.75} /> },
    { key: "settings", label: t("nav.settings"), icon: <Settings className="h-4 w-4" strokeWidth={1.75} /> },
  ];

  return (
    <div className="flex min-h-screen bg-[#050507] text-zinc-100">
      {/* Tier-1 Sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-zinc-800 bg-[#0e0e12] md:flex">
        <div className="flex items-center gap-3 border-b border-zinc-800 px-5 py-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-700 bg-[#09090b]">
            <ShieldCheck className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm font-bold tracking-tight text-zinc-100">QuantSeal</span>
              <span className="font-mono text-[10px] text-zinc-500">v{auth.version}</span>
            </div>
            <a
              href="https://berich.cc/quantseal"
              target="_blank"
              rel="noreferrer"
              className="block truncate font-mono text-[10px] text-zinc-400 transition hover:text-zinc-200"
            >
              by berichlab · Apache-2.0
            </a>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {navItems.map((item) => {
            const active = tab === item.key;
            return (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-[#22222c] text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:bg-[#16161d] hover:text-zinc-200"
                }`}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="space-y-2 border-t border-zinc-800 p-3">
          <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-[#09090b] p-1">
            <span className="flex items-center gap-1.5 pl-2 text-[11px] text-zinc-500">
              <Globe className="h-3.5 w-3.5" strokeWidth={1.75} />
            </span>
            <div className="grid flex-1 grid-cols-2 gap-1 pl-1.5">
              <button
                type="button"
                onClick={() => setLocale("en")}
                className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                  locale === "en"
                    ? "bg-[#22222c] text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => setLocale("zh-TW")}
                className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                  locale === "zh-TW"
                    ? "bg-[#22222c] text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                繁中
              </button>
            </div>
          </div>

          {auth.auth_enabled && (
            <button
              onClick={async () => {
                await api.logout();
                setAuth({ ...auth, authenticated: false });
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-zinc-400 hover:bg-[#16161d] hover:text-zinc-200"
            >
              <LogOut className="h-3.5 w-3.5" />
              {t("nav.lock")}
            </button>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex flex-1 flex-col">
        {/* Mobile top nav */}
        <header className="flex items-center justify-between gap-2 border-b border-zinc-800 bg-[#0e0e12] px-4 py-3 md:hidden">
          <div className="flex shrink-0 items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-bold">QuantSeal</span>
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto">
            {navItems.map((item) => (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={`rounded px-2.5 py-1 text-xs whitespace-nowrap ${
                  tab === item.key ? "bg-[#22222c] text-zinc-100" : "text-zinc-400"
                }`}
              >
                {item.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setLocale(locale === "en" ? "zh-TW" : "en")}
              className="rounded border border-zinc-700 bg-[#09090b] px-2 py-1 font-mono text-[11px] text-zinc-300 whitespace-nowrap"
            >
              {locale === "en" ? "繁中" : "EN"}
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 p-5 sm:p-8">
          {tab === "overview" && overview && (
            <OverviewView
              data={overview}
              onNavigate={(tKey) => setTab(tKey)}
              onNewCampaign={() => setShowNewModal(true)}
            />
          )}
          {tab === "campaigns" && (
            <CampaignsView
              campaigns={campaigns}
              onRefresh={loadAll}
              onNewCampaign={() => setShowNewModal(true)}
              onNavigateShadow={() => setTab("shadow")}
            />
          )}
          {tab === "shadow" && (
            <ShadowLadderView strategies={shadows} onRefresh={loadAll} />
          )}
          {tab === "auditor" && <GateAuditorView />}
          {tab === "mcp" && <McpHubView />}
          {tab === "settings" && <SettingsView onSaved={loadAll} />}
        </main>
      </div>

      {showNewModal && (
        <NewCampaignModal
          existingCampaigns={campaigns}
          llmConfigured={overview?.llm_configured ?? false}
          onClose={() => setShowNewModal(false)}
          onCreated={async () => {
            await loadAll();
            setTab("campaigns");
          }}
        />
      )}
    </div>
  );
};

export default App;
