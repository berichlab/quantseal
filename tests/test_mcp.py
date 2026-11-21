"""Tests for QuantSeal bidirectional MCP: outbound MCP client connectors + inbound QuantSeal MCP server."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from quantseal.api.main import create_app
from quantseal.config import Settings, get_settings
from quantseal.mcp import MCPClientError, MCPServerConfig, call_mcp_tool, discover_mcp_tools


def _start_mock_mcp_http_server(*, sse_mode: bool = False):
    """Spin up a lightweight live HTTP JSON-RPC 2.0 MCP server on an ephemeral localhost port."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            method = body.get("method")
            req_id = body.get("id")

            if req_id is None:
                self.send_response(202)
                self.end_headers()
                return

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mock-macro-mcp", "version": "1.0.0"},
                    },
                }
            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "get_macro_regime",
                                "description": "Return current macro volatility and rates snapshot",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"region": {"type": "string"}},
                                },
                            }
                        ]
                    },
                }
            elif method == "tools/call":
                args = (body.get("params") or {}).get("arguments") or {}
                region = args.get("region", "US")
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {"region": region, "vix_regime": "moderate", "yield_curve": "positive"}
                                ),
                            }
                        ],
                        "isError": False,
                    },
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }

            self.send_response(200)
            self.send_header("Mcp-Session-Id", "sess-test-123")
            if sse_mode:
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"event: message\ndata: {json.dumps(resp)}\n\n".encode())
            else:
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}/mcp"


def test_outbound_mcp_client_json_and_sse():
    for sse_mode in (False, True):
        srv, url = _start_mock_mcp_http_server(sse_mode=sse_mode)
        try:
            cfg = MCPServerConfig(
                server_id="macro-feed",
                name="Macro Feed MCP",
                transport="http",
                url=url,
                headers={"Authorization": "Bearer sk-mock-token-1234567890"},
            )
            disc = discover_mcp_tools(cfg)
            assert disc["tool_count"] == 1
            assert disc["tools"][0]["name"] == "get_macro_regime"

            res = call_mcp_tool(cfg, "get_macro_regime", {"region": "US"})
            assert res["is_error"] is False
            assert "moderate" in res["text"]
        finally:
            srv.shutdown()
            srv.server_close()


def test_stdio_mcp_blocked_by_default():
    cfg = MCPServerConfig(
        server_id="local-exec",
        name="Unsafe Local Stdio",
        transport="stdio",
        command="python3",
        args=("-m", "quantseal", "mcp"),
    )
    try:
        discover_mcp_tools(cfg, allow_stdio=False)
        raise AssertionError("Expected MCPClientError when allow_stdio=False")
    except MCPClientError as exc:
        assert "disabled by default" in str(exc)


def test_mcp_hub_api_and_quantseal_mcp_server_e2e(tmp_path: Path):
    srv, mock_url = _start_mock_mcp_http_server(sse_mode=False)
    settings = Settings(
        admin_password="",
        data_dir=str(tmp_path / "qs_mcp"),
        auto_demo=True,
        scheduler_enabled=False,
        allow_stdio_mcp=False,
    )
    app = create_app(settings=settings, start_scheduler=False)
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with TestClient(app) as client:
            # 1. Built-in QuantSeal Streamable HTTP MCP Server: initialize -> tools/list -> tools/call
            init = client.post(
                "/api/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            assert init.status_code == 200
            assert init.json()["result"]["serverInfo"]["name"] == "quantseal"

            notif = client.post(
                "/api/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )
            assert notif.status_code == 202

            tools = client.post(
                "/api/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ).json()
            names = [t["name"] for t in tools["result"]["tools"]]
            assert "quantseal_audit_trades" in names
            assert "quantseal_compute_evalue" in names
            assert "quantseal_list_shadow_ladder" in names

            ev_call = client.post(
                "/api/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "quantseal_compute_evalue",
                        "arguments": {"deltas": [3.5] * 60, "cost": 0.0, "alpha": 0.01},
                    },
                },
            ).json()
            ev_payload = json.loads(ev_call["result"]["content"][0]["text"])
            assert ev_payload["rejected"] is True
            assert ev_payload["peak_evalue"] >= 100.0

            # 2. Register external MCP server -> verify masked headers -> discover -> invoke -> inject into campaign discovery!
            reg = client.post(
                "/api/mcp/servers",
                json={
                    "server_id": "macro-feed",
                    "name": "Macro Regime MCP",
                    "transport": "http",
                    "url": mock_url,
                    "headers": {"Authorization": "Bearer sk-external-secret-999999999"},
                    "include_in_discovery": True,
                    "discovery_tools": [{"tool_name": "get_macro_regime", "arguments": {"region": "US"}}],
                },
            )
            assert reg.status_code == 201
            assert "sk-external-secret-999999999" not in json.dumps(reg.json())

            # Stdio registration rejected when allow_stdio_mcp=False
            bad_stdio = client.post(
                "/api/mcp/servers",
                json={
                    "server_id": "bad-stdio",
                    "name": "Blocked Stdio",
                    "transport": "stdio",
                    "command": "echo",
                },
            )
            assert bad_stdio.status_code == 400

            disc = client.post("/api/mcp/servers/macro-feed/discover")
            assert disc.status_code == 200
            assert disc.json()["server"]["tool_count"] == 1
            assert disc.json()["server"]["last_status"] == "connected"

            call = client.post(
                "/api/mcp/servers/macro-feed/call",
                json={"tool_name": "get_macro_regime", "arguments": {"region": "EU"}},
            )
            assert call.status_code == 200
            assert "EU" in call.json()["text"]

            # 3. Launch a discovery campaign with use_mcp=True -> verify external_mcp_evidence landed strictly in evidence_cards
            camp = client.post(
                "/api/campaigns",
                json={
                    "campaign_id": "mcp-discovery-v1",
                    "source": "demo",
                    "development_only": True,
                    "use_mcp": True,
                },
            )
            assert camp.status_code == 201
            ev_cards = camp.json()["evidence_cards"]
            assert len(ev_cards.get("external_mcp_evidence") or []) == 1
            assert ev_cards["external_mcp_evidence"][0]["tool_name"] == "get_macro_regime"
            assert "pit_warning" in ev_cards["external_mcp_evidence"][0]
    finally:
        srv.shutdown()
        srv.server_close()
