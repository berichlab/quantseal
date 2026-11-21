import React, { useEffect, useState } from "react";
import {
  Check,
  Copy,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { MCPHubResponse, MCPServerItem } from "../types";

export const McpHubView: React.FC = () => {
  const { t } = useI18n();
  const [hub, setHub] = useState<MCPHubResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  // Add server form state
  const [serverId, setServerId] = useState("");
  const [name, setName] = useState("");
  const [transport, setTransport] = useState("http");
  const [url, setUrl] = useState("");
  const [authHeader, setAuthHeader] = useState("");
  const [command, setCommand] = useState("");
  const [includeDiscovery, setIncludeDiscovery] = useState(true);
  const [discTool, setDiscTool] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Live tool tester state
  const [selectedTool, setSelectedTool] = useState("");
  const [argsJson, setArgsJson] = useState("{}");
  const [calling, setCalling] = useState(false);
  const [callOutput, setCallOutput] = useState<{
    text: string;
    is_error: boolean;
    latency_ms: number;
  } | null>(null);

  const [discoveringId, setDiscoveringId] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadHub = async () => {
    const res = await api.listMcpServers();
    setHub(res);
    if (!selectedId && res.servers.length > 0) {
      setSelectedId(res.servers[0].server_id);
    }
  };

  useEffect(() => {
    loadHub().catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, []);

  const selectedServer: MCPServerItem | null =
    hub?.servers.find((s) => s.server_id === selectedId) || null;

  useEffect(() => {
    if (selectedServer && selectedServer.discovered_tools.length > 0) {
      setSelectedTool((prev) =>
        selectedServer.discovered_tools.some((tool) => tool.name === prev)
          ? prev
          : selectedServer.discovered_tools[0].name
      );
    } else {
      setSelectedTool("");
    }
    setCallOutput(null);
  }, [selectedId, selectedServer?.tool_count]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const headers: Record<string, string> = {};
      if (authHeader.trim()) headers["Authorization"] = authHeader.trim();
      const discoveryTools = discTool.trim()
        ? [{ tool_name: discTool.trim(), arguments: {} }]
        : [];
      const created = await api.createMcpServer({
        server_id: serverId.trim(),
        name: name.trim(),
        transport,
        url: url.trim(),
        headers,
        command: command.trim(),
        include_in_discovery: includeDiscovery,
        discovery_tools: discoveryTools,
      });
      await loadHub();
      setSelectedId(created.server_id);
      setShowAdd(false);
      setServerId("");
      setName("");
      setUrl("");
      setAuthHeader("");
      setCommand("");
      setDiscTool("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to register MCP server");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDiscover = async (id: string) => {
    setDiscoveringId(id);
    setError(null);
    try {
      await api.discoverMcpServer(id);
      await loadHub();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
      await loadHub();
    } finally {
      setDiscoveringId(null);
    }
  };

  const handleToggleDiscovery = async (srv: MCPServerItem) => {
    await api.updateMcpServer(srv.server_id, {
      include_in_discovery: !srv.include_in_discovery,
    });
    await loadHub();
  };

  const handleDelete = async (id: string) => {
    await api.deleteMcpServer(id);
    if (selectedId === id) setSelectedId(null);
    await loadHub();
  };

  const handleCallTool = async () => {
    if (!selectedServer || !selectedTool) return;
    setCalling(true);
    setError(null);
    try {
      const parsed = JSON.parse(argsJson || "{}");
      const res = await api.callMcpTool(selectedServer.server_id, selectedTool, parsed);
      setCallOutput(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tool call failed");
    } finally {
      setCalling(false);
    }
  };

  const copyText = (key: string, value: string) => {
    navigator.clipboard?.writeText(value).catch(() => {});
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const cursorSnippet = hub
    ? JSON.stringify(
        {
          mcpServers: {
            quantseal: {
              url: hub.quantseal_mcp_server.http_endpoint,
              headers: { Authorization: "Bearer YOUR_ADMIN_PASSWORD" },
            },
          },
        },
        null,
        2
      )
    : "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">{t("mcp.title")}</h2>
          <p className="mt-1 text-sm text-zinc-400">{t("mcp.subtitle")}</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-white whitespace-nowrap"
        >
          <Plus className="h-4 w-4" />
          {t("mcp.addBtn")}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-zinc-700 bg-[#09090b] px-4 py-2.5 text-sm text-rose-400">
          {error}
        </div>
      )}

      {/* Section 1: Outbound External MCP Connectors */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-3 lg:col-span-5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <Plug className="h-3.5 w-3.5 text-sky-400" />
            <span>{t("mcp.externalTitle")}</span>
          </div>

          {!hub || hub.servers.length === 0 ? (
            <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-6 text-sm text-zinc-400">
              {t("mcp.empty")}
            </div>
          ) : (
            hub.servers.map((srv) => {
              const active = srv.server_id === selectedId;
              return (
                <div
                  key={srv.server_id}
                  onClick={() => setSelectedId(srv.server_id)}
                  className={`cursor-pointer rounded-xl p-4 transition ${
                    active
                      ? "border-2 border-zinc-100 bg-[#22222c] shadow-2xl"
                      : "border border-zinc-700/80 bg-[#16161d] hover:bg-[#1c1c25]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-bold text-zinc-100">{srv.name}</div>
                      <div className="truncate font-mono text-[11px] text-zinc-400">
                        {srv.server_id} · {srv.transport.toUpperCase()} · {srv.tool_count}{" "}
                        {t("mcp.toolsCount")}
                      </div>
                    </div>
                    <span className="flex shrink-0 items-center gap-1.5 font-mono text-[11px] text-zinc-300">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          srv.last_status === "connected"
                            ? "bg-emerald-400"
                            : srv.last_status === "error"
                            ? "bg-rose-400"
                            : "bg-amber-400"
                        }`}
                      />
                      {srv.last_latency_ms != null ? `${srv.last_latency_ms}ms` : srv.last_status}
                    </span>
                  </div>

                  <div className="mt-2 truncate font-mono text-[11px] text-zinc-500">
                    {srv.url || srv.command}
                  </div>

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800 pt-2.5">
                    <label
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-1.5 text-xs text-zinc-300"
                    >
                      <input
                        type="checkbox"
                        checked={srv.include_in_discovery}
                        onChange={() => handleToggleDiscovery(srv)}
                        className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900"
                      />
                      <span>{t("mcp.includeDiscovery")}</span>
                    </label>

                    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleDiscover(srv.server_id)}
                        disabled={discoveringId === srv.server_id}
                        className="flex items-center gap-1 rounded border border-zinc-700 bg-[#1a1a22] px-2.5 py-1 text-xs text-zinc-200 hover:bg-[#24242f] disabled:opacity-50"
                      >
                        <RefreshCw
                          className={`h-3 w-3 ${
                            discoveringId === srv.server_id ? "animate-spin" : ""
                          }`}
                        />
                        {discoveringId === srv.server_id ? t("mcp.discovering") : t("mcp.discover")}
                      </button>
                      <button
                        onClick={() => handleDelete(srv.server_id)}
                        title={t("mcp.delete")}
                        className="rounded border border-zinc-700 bg-[#1a1a22] p-1 text-zinc-400 hover:text-rose-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: Discovered Tools & Live Caller */}
        <div className="space-y-4 lg:col-span-7">
          {selectedServer ? (
            <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-zinc-100">
                    {selectedServer.name} — {t("mcp.invokeTitle")}
                  </h3>
                  <p className="font-mono text-xs text-zinc-400">
                    {selectedServer.tool_count} {t("mcp.toolsCount")}
                  </p>
                </div>
              </div>

              {selectedServer.last_error && (
                <div className="mb-3 rounded-lg border border-zinc-800 bg-[#09090b] p-3 font-mono text-xs text-rose-400">
                  {selectedServer.last_error}
                </div>
              )}

              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs text-zinc-400">{t("mcp.selectTool")}</label>
                  <select
                    value={selectedTool}
                    onChange={(e) => setSelectedTool(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                  >
                    {selectedServer.discovered_tools.length === 0 ? (
                      <option value="">-- {t("mcp.discover")} --</option>
                    ) : (
                      selectedServer.discovered_tools.map((tool) => (
                        <option key={tool.name} value={tool.name}>
                          {tool.name} — {tool.description.slice(0, 60)}
                        </option>
                      ))
                    )}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-xs text-zinc-400">{t("mcp.argsJson")}</label>
                  <textarea
                    rows={3}
                    value={argsJson}
                    onChange={(e) => setArgsJson(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-[#09090b] p-2.5 font-mono text-xs text-zinc-200 focus:border-zinc-300 focus:outline-none"
                  />
                </div>

                <button
                  onClick={handleCallTool}
                  disabled={calling || !selectedTool}
                  className="flex items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
                >
                  <Play className="h-3.5 w-3.5" />
                  {calling ? t("mcp.runningTool") : t("mcp.runTool")}
                </button>

                {callOutput && (
                  <pre className="max-h-56 overflow-auto rounded-lg border border-zinc-800 bg-[#09090b] p-3 font-mono text-xs text-zinc-200">
                    {`// ${callOutput.latency_ms}ms (${callOutput.is_error ? "ERROR" : "OK"})\n${callOutput.text}`}
                  </pre>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
              <div className="mb-3 flex items-center gap-2">
                <Server className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
                <h3 className="text-base font-bold text-zinc-100">{t("mcp.serverTitle")}</h3>
              </div>
              <p className="text-xs text-zinc-400">{t("mcp.serverDesc")}</p>

              {hub && (
                <div className="mt-4 space-y-3">
                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3">
                    <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-400">
                      <span>{t("mcp.httpEndpoint")}</span>
                      <button
                        onClick={() => copyText("http", hub.quantseal_mcp_server.http_endpoint)}
                        className="flex items-center gap-1 text-zinc-300 hover:text-white"
                      >
                        {copiedKey === "http" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        {copiedKey === "http" ? t("mcp.copied") : t("mcp.copy")}
                      </button>
                    </div>
                    <code className="block overflow-x-auto whitespace-nowrap font-mono text-xs text-emerald-400">
                      {hub.quantseal_mcp_server.http_endpoint}
                    </code>
                  </div>

                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3">
                    <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-400">
                      <span>{t("mcp.stdioCmd")}</span>
                      <button
                        onClick={() => copyText("stdio", hub.quantseal_mcp_server.stdio_command)}
                        className="flex items-center gap-1 text-zinc-300 hover:text-white"
                      >
                        {copiedKey === "stdio" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        {copiedKey === "stdio" ? t("mcp.copied") : t("mcp.copy")}
                      </button>
                    </div>
                    <code className="block font-mono text-xs text-zinc-200">
                      {hub.quantseal_mcp_server.stdio_command}
                    </code>
                  </div>

                  <div className="rounded-lg border border-zinc-800 bg-[#09090b] p-3">
                    <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-400">
                      <span>MCP Client Config (Cursor / Claude / OpenClaw)</span>
                      <button
                        onClick={() => copyText("cfg", cursorSnippet)}
                        className="flex items-center gap-1 text-zinc-300 hover:text-white"
                      >
                        {copiedKey === "cfg" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        {copiedKey === "cfg" ? t("mcp.copied") : t("mcp.copy")}
                      </button>
                    </div>
                    <pre className="overflow-x-auto font-mono text-[11px] text-zinc-300">
                      {cursorSnippet}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Section 2: Built-in QuantSeal MCP Tool Catalog */}
      {hub && (
        <div className="rounded-xl border border-zinc-700/80 bg-[#16161d] p-5 shadow-lg">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
              <h3 className="text-base font-bold text-zinc-100">{t("mcp.builtinTools")}</h3>
            </div>
            <code className="rounded border border-zinc-800 bg-[#09090b] px-2.5 py-1 font-mono text-xs text-emerald-400">
              POST {hub.quantseal_mcp_server.http_endpoint}
            </code>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {hub.quantseal_mcp_server.tools.map((tool) => (
              <div
                key={tool.name}
                className="rounded-lg border border-zinc-800 bg-[#09090b] p-3.5"
              >
                <div className="font-mono text-xs font-semibold text-zinc-100">{tool.name}</div>
                <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">{tool.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Register External MCP Modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <div className="w-full max-w-lg rounded-xl border border-zinc-700 bg-[#16161d] p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-zinc-100">{t("mcp.modalTitle")}</h3>
                <p className="text-xs text-zinc-400">{t("mcp.modalSubtitle")}</p>
              </div>
              <button onClick={() => setShowAdd(false)} className="text-zinc-400 hover:text-zinc-100">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs text-zinc-400">{t("mcp.serverId")}</label>
                  <input
                    required
                    value={serverId}
                    onChange={(e) => setServerId(e.target.value)}
                    placeholder="macro-fred"
                    className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-zinc-400">{t("mcp.serverName")}</label>
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="FRED Macro Data MCP"
                    className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs text-zinc-400">{t("mcp.transport")}</label>
                <select
                  value={transport}
                  onChange={(e) => setTransport(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 text-sm text-zinc-100 focus:border-zinc-300 focus:outline-none"
                >
                  <option value="http">Streamable HTTP / SSE (JSON-RPC 2.0)</option>
                  <option value="stdio" disabled={!hub?.allow_stdio_mcp}>
                    Local Stdio {!hub?.allow_stdio_mcp ? "(Disabled)" : ""}
                  </option>
                </select>
                {!hub?.allow_stdio_mcp && (
                  <p className="mt-1 text-[11px] text-zinc-500">{t("mcp.stdioDisabled")}</p>
                )}
              </div>

              {transport === "http" ? (
                <>
                  <div>
                    <label className="mb-1 block text-xs text-zinc-400">{t("mcp.url")}</label>
                    <input
                      required
                      type="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://your-mcp-server.example/mcp"
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-zinc-400">{t("mcp.authHeader")}</label>
                    <input
                      type="password"
                      value={authHeader}
                      onChange={(e) => setAuthHeader(e.target.value)}
                      placeholder="Bearer ..."
                      className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                    />
                  </div>
                </>
              ) : (
                <div>
                  <label className="mb-1 block text-xs text-zinc-400">Command</label>
                  <input
                    required
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="uvx mcp-server-..."
                    className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                  />
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs text-zinc-400">{t("mcp.discoveryTool")}</label>
                <input
                  value={discTool}
                  onChange={(e) => setDiscTool(e.target.value)}
                  placeholder="get_macro_regime"
                  className="w-full rounded-lg border border-zinc-700 bg-[#09090b] px-3 py-2 font-mono text-xs text-zinc-100 focus:border-zinc-300 focus:outline-none"
                />
              </div>

              <label className="flex items-center gap-2 text-xs text-zinc-200">
                <input
                  type="checkbox"
                  checked={includeDiscovery}
                  onChange={(e) => setIncludeDiscovery(e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-600 bg-zinc-900"
                />
                <span>{t("mcp.includeDiscovery")}</span>
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  className="rounded-lg border border-zinc-700 bg-[#1a1a22] px-4 py-2 text-xs text-zinc-200 hover:bg-[#24242f]"
                >
                  {t("newCamp.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-lg bg-zinc-100 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
                >
                  {submitting ? t("mcp.registering") : t("mcp.register")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
