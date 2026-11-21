"""Model Context Protocol (MCP) client connectors and built-in QuantSeal MCP server."""
from __future__ import annotations

from quantseal.mcp.client import (
    MCP_PROTOCOL_VERSION,
    MCPClientError,
    MCPServerConfig,
    call_mcp_tool,
    collect_discovery_mcp_evidence,
    discover_mcp_tools,
)
from quantseal.mcp.server import (
    QUANTSEAL_MCP_TOOLS,
    handle_mcp_jsonrpc,
    run_stdio_mcp_server,
)

__all__ = [
    "MCPClientError",
    "MCPServerConfig",
    "MCP_PROTOCOL_VERSION",
    "QUANTSEAL_MCP_TOOLS",
    "call_mcp_tool",
    "collect_discovery_mcp_evidence",
    "discover_mcp_tools",
    "handle_mcp_jsonrpc",
    "run_stdio_mcp_server",
]
