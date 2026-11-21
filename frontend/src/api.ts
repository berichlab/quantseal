import type {
  AuditResponse,
  AuthStatus,
  CampaignDetail,
  CampaignSummaryItem,
  MCPHubResponse,
  MCPServerItem,
  OverviewResponse,
  RuntimeSettingsResponse,
  ShadowStrategyDetail,
  ShadowStrategyItem,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = String(body.detail);
    } catch {
      // ignore non-json error body
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  login: (password: string) =>
    request<{ ok: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  overview: () => request<OverviewResponse>("/api/overview"),
  listCampaigns: () =>
    request<{ campaigns: CampaignSummaryItem[]; cost_presets: Record<string, unknown> }>(
      "/api/campaigns"
    ),
  getCampaign: (id: string) => request<CampaignDetail>(`/api/campaigns/${encodeURIComponent(id)}`),
  createCampaign: (payload: Record<string, unknown>) =>
    request<CampaignDetail>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validateCampaignOnce: (id: string) =>
    request<CampaignDetail>(`/api/campaigns/${encodeURIComponent(id)}/validate-once`, {
      method: "POST",
    }),
  enrollSpec: (campaignId: string, specId: string) =>
    request<{ strategy_key: string; state: string }>(
      `/api/campaigns/${encodeURIComponent(campaignId)}/enroll/${encodeURIComponent(specId)}`,
      { method: "POST" }
    ),
  listShadow: () =>
    request<{ policy: Record<string, number>; strategies: ShadowStrategyItem[] }>("/api/shadow"),
  getShadow: (key: string) =>
    request<ShadowStrategyDetail>(`/api/shadow/${encodeURIComponent(key)}`),
  addObservation: (
    key: string,
    payload: {
      obs_date: string;
      strategy_return_pct: number;
      benchmark_return_pct: number;
      note: string;
    }
  ) =>
    request<{ strategy_key: string; state: string }>(
      `/api/shadow/${encodeURIComponent(key)}/observations`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  auditTrades: (payload: Record<string, unknown>) =>
    request<AuditResponse>("/api/audit/trades", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getSettings: () => request<RuntimeSettingsResponse>("/api/settings"),
  updateSettings: (payload: Record<string, unknown>) =>
    request<RuntimeSettingsResponse>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testNotification: () =>
    request<{ status: string; sent: string[]; errors: Record<string, string> }>(
      "/api/notifications/test",
      { method: "POST" }
    ),
  runShadowReconcile: () =>
    request<{ checked: number; transitions: number }>("/api/scheduler/run-shadow", {
      method: "POST",
    }),
  listMcpServers: () => request<MCPHubResponse>("/api/mcp/servers"),
  createMcpServer: (payload: Record<string, unknown>) =>
    request<MCPServerItem>("/api/mcp/servers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMcpServer: (id: string, payload: Record<string, unknown>) =>
    request<MCPServerItem>(`/api/mcp/servers/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteMcpServer: (id: string) =>
    request<{ deleted: string }>(`/api/mcp/servers/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  discoverMcpServer: (id: string) =>
    request<{ server: MCPServerItem; discovery: Record<string, unknown> }>(
      `/api/mcp/servers/${encodeURIComponent(id)}/discover`,
      { method: "POST" }
    ),
  callMcpTool: (id: string, toolName: string, args: Record<string, unknown>) =>
    request<{ tool_name: string; is_error: boolean; text: string; latency_ms: number }>(
      `/api/mcp/servers/${encodeURIComponent(id)}/call`,
      { method: "POST", body: JSON.stringify({ tool_name: toolName, arguments: args }) }
    ),
};
