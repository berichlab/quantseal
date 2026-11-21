"""MCP (Model Context Protocol) client for connecting QuantSeal to external MCP servers.

Supports:
- Streamable HTTP / JSON-RPC 2.0 (`application/json` and `text/event-stream` SSE responses)
- Optional local stdio JSON-RPC 2.0 (strictly gated behind `allow_stdio=True`, fail-closed by default)

Security invariants:
- External stdio execution is DISABLED by default on self-hosted servers to prevent RCE.
- Strict request timeout and response byte cap prevent resource exhaustion.
- Sensitive headers and tool outputs are redacted before persisting or injecting into prompts.
- External MCP tool outputs passed into discovery are strictly tagged as unverified
  external context and are never used to bypass validation or sealed holdout rules.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from quantseal.discovery.llm import sanitize_text_no_secrets

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-03-26"
MAX_MCP_RESPONSE_BYTES = 262_144  # 256 KB cap
MAX_DISCOVERY_TOOL_CHARS = 4_000


class MCPClientError(RuntimeError):
    """Raised when connecting to or invoking an external MCP server fails."""


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    name: str
    transport: str = "http"  # "http" | "stdio"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    command: str = ""
    args: tuple[str, ...] = ()
    enabled: bool = True
    include_in_discovery: bool = False
    discovery_tools: tuple[dict[str, Any], ...] = ()
    timeout_seconds: float = 15.0

    def validate(self, *, allow_stdio: bool = False) -> None:
        tr = self.transport.strip().lower()
        if tr == "http":
            parsed = urlparse(self.url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise MCPClientError(f"Invalid HTTP MCP URL: '{self.url}'")
        elif tr == "stdio":
            if not allow_stdio:
                raise MCPClientError(
                    "Local stdio MCP transport is disabled by default for security. "
                    "Set QUANTSEAL_ALLOW_STDIO_MCP=true to enable stdio connectors."
                )
            if not self.command.strip():
                raise MCPClientError("stdio MCP server requires a non-empty 'command'")
        else:
            raise MCPClientError(f"Unsupported MCP transport '{self.transport}' (use 'http' or 'stdio')")


def _parse_jsonrpc_http_body(raw_bytes: bytes, content_type: str) -> dict[str, Any]:
    raw = raw_bytes[:MAX_MCP_RESPONSE_BYTES]
    text = raw.decode("utf-8", errors="replace").strip()
    ct = content_type.lower()

    if "text/event-stream" in ct or text.startswith("event:") or text.startswith("data:"):
        # Parse MCP Streamable HTTP SSE stream and extract the last JSON-RPC message
        last_msg: dict[str, Any] | None = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                        last_msg = parsed
                except ValueError:
                    continue
        if last_msg is not None:
            return last_msg
        raise MCPClientError("SSE MCP response did not contain a valid JSON-RPC message")

    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise MCPClientError(f"Invalid JSON from MCP server: {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise MCPClientError("MCP server response must be a JSON-RPC object")
    return parsed


def _unwrap_jsonrpc(msg: dict[str, Any]) -> dict[str, Any]:
    if "error" in msg and msg["error"] is not None:
        err = msg["error"]
        if isinstance(err, dict):
            raise MCPClientError(f"MCP error {err.get('code')}: {err.get('message')}")
        raise MCPClientError(f"MCP error: {err}")
    res = msg.get("result")
    return res if isinstance(res, dict) else {"value": res}


def _http_exchange(
    config: MCPServerConfig,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    base_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "QuantSeal-MCP/0.1",
        **{str(k): str(v) for k, v in config.headers.items() if str(k).strip()},
    }
    timeout = min(30.0, max(1.0, float(config.timeout_seconds)))
    session_id: str | None = None
    responses: list[dict[str, Any]] = []

    for req_payload in requests:
        req_headers = dict(base_headers)
        if session_id:
            req_headers["Mcp-Session-Id"] = session_id
        data = json.dumps(req_payload).encode("utf-8")
        request = urllib.request.Request(
            config.url.strip(),
            data=data,
            headers=req_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    session_id = sid
                raw = resp.read(MAX_MCP_RESPONSE_BYTES + 1)
                ct = resp.headers.get("Content-Type", "")
        except HTTPError as exc:
            err_body = exc.read(512).decode("utf-8", errors="replace")
            raise MCPClientError(
                f"MCP HTTP {exc.code}: {sanitize_text_no_secrets(err_body, max_len=300)}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MCPClientError(f"MCP connection failed: {exc}") from exc

        if "id" not in req_payload:
            continue
        if not raw.strip():
            responses.append({})
        else:
            responses.append(_unwrap_jsonrpc(_parse_jsonrpc_http_body(raw, ct)))
    return responses


def _stdio_exchange(
    config: MCPServerConfig,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeout = min(30.0, max(1.0, float(config.timeout_seconds)))
    cmd = [config.command.strip(), *[str(a) for a in config.args]]
    stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MCPClientError(f"stdio MCP command timed out after {timeout}s") from exc
    except OSError as exc:
        raise MCPClientError(f"Failed to start stdio MCP server: {exc}") from exc

    expected_ids = [r["id"] for r in requests if "id" in r]
    by_id: dict[Any, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "id" in obj:
            by_id[obj["id"]] = obj

    if not by_id and proc.returncode != 0:
        raise MCPClientError(
            f"stdio MCP exited {proc.returncode}: {sanitize_text_no_secrets(proc.stderr, max_len=300)}"
        )

    out: list[dict[str, Any]] = []
    for req_id in expected_ids:
        if req_id not in by_id:
            raise MCPClientError(f"Missing JSON-RPC response for id={req_id}")
        out.append(_unwrap_jsonrpc(by_id[req_id]))
    return out


def _build_handshake() -> list[dict[str, Any]]:
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "QuantSeal", "version": "0.1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    ]


def discover_mcp_tools(
    config: MCPServerConfig,
    *,
    allow_stdio: bool = False,
) -> dict[str, Any]:
    """Handshake with an external MCP server and retrieve its tool catalog."""
    config.validate(allow_stdio=allow_stdio)
    started = time.monotonic()
    reqs = _build_handshake() + [{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
    results = (
        _http_exchange(config, reqs)
        if config.transport.strip().lower() == "http"
        else _stdio_exchange(config, reqs)
    )
    elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
    init_res = results[0] if len(results) >= 1 else {}
    tools_res = results[1] if len(results) >= 2 else {}
    raw_tools = tools_res.get("tools") or []
    tools: list[dict[str, Any]] = []
    for t in raw_tools:
        if not isinstance(t, dict) or not t.get("name"):
            continue
        tools.append(
            {
                "name": str(t["name"]),
                "description": sanitize_text_no_secrets(str(t.get("description") or ""), max_len=500),
                "inputSchema": t.get("inputSchema") or {"type": "object", "properties": {}},
            }
        )
    return {
        "server_info": init_res.get("serverInfo") or {},
        "protocol_version": init_res.get("protocolVersion") or MCP_PROTOCOL_VERSION,
        "tools": tools,
        "tool_count": len(tools),
        "latency_ms": elapsed_ms,
    }


def call_mcp_tool(
    config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    allow_stdio: bool = False,
) -> dict[str, Any]:
    """Invoke a single tool on an external MCP server and return redacted output."""
    config.validate(allow_stdio=allow_stdio)
    if not str(tool_name or "").strip():
        raise MCPClientError("tool_name must be non-empty")
    started = time.monotonic()
    reqs = _build_handshake() + [
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": str(tool_name).strip(), "arguments": arguments or {}},
        }
    ]
    results = (
        _http_exchange(config, reqs)
        if config.transport.strip().lower() == "http"
        else _stdio_exchange(config, reqs)
    )
    elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
    call_res = results[1] if len(results) >= 2 else {}
    content_blocks = call_res.get("content") or []
    text_parts: list[str] = []
    for block in content_blocks:
        if isinstance(block, dict):
            if "text" in block:
                text_parts.append(str(block["text"]))
            else:
                text_parts.append(json.dumps(block, ensure_ascii=False))
        else:
            text_parts.append(str(block))
    rendered = sanitize_text_no_secrets("\n".join(text_parts), max_len=MAX_MCP_RESPONSE_BYTES)
    return {
        "tool_name": str(tool_name).strip(),
        "is_error": bool(call_res.get("isError", False)),
        "text": rendered,
        "raw_result": call_res,
        "latency_ms": elapsed_ms,
    }


def collect_discovery_mcp_evidence(
    servers: list[MCPServerConfig],
    *,
    allow_stdio: bool = False,
) -> list[dict[str, Any]]:
    """Query enabled discovery-tagged external MCP tools safely for discovery evidence cards."""
    evidence: list[dict[str, Any]] = []
    for srv in servers:
        if not srv.enabled or not srv.include_in_discovery or not srv.discovery_tools:
            continue
        for item in srv.discovery_tools[:5]:
            tname = str(item.get("tool_name") or item.get("name") or "").strip()
            targs = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            if not tname:
                continue
            try:
                res = call_mcp_tool(srv, tname, targs, allow_stdio=allow_stdio)
                evidence.append(
                    {
                        "server_id": srv.server_id,
                        "server_name": srv.name,
                        "tool_name": tname,
                        "status": "error" if res["is_error"] else "ok",
                        "latency_ms": res["latency_ms"],
                        "output": sanitize_text_no_secrets(res["text"], max_len=MAX_DISCOVERY_TOOL_CHARS),
                        "pit_warning": (
                            "Unverified external MCP context (discovery-only). "
                            "Do not treat live external MCP outputs as point-in-time validation evidence."
                        ),
                    }
                )
            except Exception as exc:
                logger.warning("External MCP discovery tool %s/%s failed: %s", srv.server_id, tname, exc)
                evidence.append(
                    {
                        "server_id": srv.server_id,
                        "server_name": srv.name,
                        "tool_name": tname,
                        "status": "failed",
                        "error": sanitize_text_no_secrets(str(exc), max_len=300),
                    }
                )
    return evidence
