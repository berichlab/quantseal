"""Built-in QuantSeal MCP Server (JSON-RPC 2.0 for both HTTP `/api/mcp` and stdio `quantseal mcp`).

Allows any external MCP host (Claude Desktop, Cursor, Claude Code, Codex,
OpenClaw, n8n, or another QuantSeal node) to invoke QuantSeal's fail-closed
statistical gates, anytime-valid E-value engine, campaign ledger, and shadow ladder.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

from sqlalchemy.orm import Session

from quantseal import __version__
from quantseal.config import Settings, get_settings
from quantseal.core.evalue import DEFAULT_ALPHA, DEFAULT_SCALE, evalue_betting
from quantseal.core.gates import audit_trade_records
from quantseal.mcp.client import MCP_PROTOCOL_VERSION
from quantseal.runtime.shadow_service import load_campaign_state_file, record_shadow_observation
from quantseal.storage.db import configure_database, get_session_factory
from quantseal.storage.models import CampaignIndex, ShadowStrategy

QUANTSEAL_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "quantseal_audit_trades",
        "description": (
            "Run QuantSeal's fail-closed statistical governance audit on a list of trade records: "
            "date-clustered Bootstrap 95% CI, 1.5x/2.0x cost stress, single-asset/sector concentration, "
            "and anytime-valid test-martingale E-value."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "trades": {
                    "type": "array",
                    "description": "List of trade objects with entry_date, symbol, net (%), optional gross, sector.",
                    "items": {"type": "object"},
                },
                "min_trades": {"type": "integer", "default": 15},
                "min_avg_net_pct": {"type": "number", "default": 0.10},
                "min_profit_factor": {"type": "number", "default": 1.10},
                "max_single_asset_pct": {"type": "number", "default": 25.0},
            },
            "required": ["trades"],
        },
    },
    {
        "name": "quantseal_compute_evalue",
        "description": (
            "Compute one-sided anytime-valid test-martingale E-value (Waudby-Smith & Ramdas) on "
            "paired return differences under H0: E[delta] <= cost without peeking inflation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "deltas": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Sequence of excess returns in percentage points.",
                },
                "cost": {"type": "number", "default": 0.0},
                "alpha": {"type": "number", "default": DEFAULT_ALPHA},
                "scale": {"type": "number", "default": DEFAULT_SCALE},
            },
            "required": ["deltas"],
        },
    },
    {
        "name": "quantseal_list_campaigns",
        "description": "List all immutable QuantSeal research campaigns with SHA-256 seals and summary metrics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "quantseal_get_campaign",
        "description": "Retrieve full immutable ledger and 4-arm falsification matrix for a specific campaign_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "quantseal_list_shadow_ladder",
        "description": "List all strategies on the forward-only Shadow Ladder with E-values, MDD, and promotion states.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "quantseal_record_shadow_observation",
        "description": "Append one forward out-of-sample return observation and recompute E-value and ladder state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy_key": {"type": "string"},
                "obs_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "strategy_return_pct": {"type": "number"},
                "benchmark_return_pct": {"type": "number", "default": 0.0},
                "note": {"type": "string", "default": ""},
            },
            "required": ["strategy_key", "obs_date", "strategy_return_pct"],
        },
    },
]


def _execute_tool(
    name: str,
    args: dict[str, Any],
    db: Session,
    settings: Settings,
) -> tuple[Any, bool]:
    try:
        if name == "quantseal_audit_trades":
            trades = args.get("trades") or []
            if not isinstance(trades, list) or not trades:
                return {"error": "trades must be a non-empty list"}, True
            res = audit_trade_records(
                trades,
                min_trades=int(args.get("min_trades", 15)),
                min_avg_net_pct=float(args.get("min_avg_net_pct", 0.10)),
                min_profit_factor=float(args.get("min_profit_factor", 1.10)),
                max_single_asset_pct=float(args.get("max_single_asset_pct", 25.0)),
            )
            return res, False

        if name == "quantseal_compute_evalue":
            deltas = args.get("deltas")
            if not isinstance(deltas, list):
                return {"error": "deltas must be a list of numbers"}, True
            res = evalue_betting(
                [float(x) for x in deltas],
                cost=float(args.get("cost", 0.0)),
                alpha=float(args.get("alpha", DEFAULT_ALPHA)),
                scale=float(args.get("scale", DEFAULT_SCALE)),
                include_series=False,
            )
            return res, False

        if name == "quantseal_list_campaigns":
            rows = db.query(CampaignIndex).order_by(CampaignIndex.created_at.desc()).all()
            return {
                "campaigns": [
                    {
                        "campaign_id": r.campaign_id,
                        "status": r.status,
                        "source": r.source,
                        "config_hash": r.config_hash,
                        "data_hash": r.data_hash,
                        "code_hash": r.code_hash,
                        "validation_evaluated_once": r.validation_evaluated_once,
                        "validation_contaminated": r.validation_contaminated,
                        "dev_passed": r.dev_passed,
                        "total_candidates": r.total_candidates,
                        "qualified_count": r.qualified_count,
                    }
                    for r in rows
                ]
            }, False

        if name == "quantseal_get_campaign":
            cid = str(args.get("campaign_id") or "").strip()
            state = load_campaign_state_file(cid, settings)
            if state is None:
                return {"error": f"Campaign '{cid}' not found"}, True
            # Return concise audit-friendly view (omit giant raw trade arrays)
            compact_exps = [
                {
                    "spec_id": e.get("spec_id"),
                    "title": e.get("title"),
                    "source": e.get("source"),
                    "fingerprint": e.get("fingerprint"),
                    "development_verdict": (e.get("development") or {}).get("verdict"),
                    "development_reason": (e.get("development") or {}).get("reason"),
                    "validation_verdict": (e.get("validation") or {}).get("verdict"),
                    "outcome": e.get("outcome"),
                }
                for e in (state.get("experiments") or [])
            ]
            return {
                "campaign_id": state.get("campaign_id"),
                "status": state.get("status"),
                "config_hash": state.get("config_hash"),
                "data_hash": state.get("data_hash"),
                "code_hash": state.get("code_hash"),
                "validation_evaluated_once": state.get("validation_evaluated_once"),
                "validation_holdout_contaminated": state.get("validation_holdout_contaminated"),
                "partitions": state.get("partitions"),
                "summary": state.get("summary"),
                "experiments": compact_exps,
            }, False

        if name == "quantseal_list_shadow_ladder":
            rows = db.query(ShadowStrategy).order_by(ShadowStrategy.peak_evalue.desc()).all()
            return {
                "strategies": [
                    {
                        "strategy_key": r.strategy_key,
                        "title": r.title,
                        "state": r.state,
                        "observations_count": r.observations_count,
                        "evalue": round(r.evalue, 4),
                        "peak_evalue": round(r.peak_evalue, 4),
                        "cumulative_excess_pct": round(r.cumulative_excess_pct, 4),
                        "max_drawdown_pct": round(r.max_drawdown_pct, 4),
                        "last_reason": r.last_reason,
                    }
                    for r in rows
                ]
            }, False

        if name == "quantseal_record_shadow_observation":
            key = str(args.get("strategy_key") or "").strip()
            strat = db.query(ShadowStrategy).filter_by(strategy_key=key).first()
            if strat is None:
                return {"error": f"Shadow strategy '{key}' not found"}, True
            obs_date = dt.date.fromisoformat(str(args["obs_date"])[:10])
            ev = record_shadow_observation(
                db,
                strat,
                obs_date=obs_date,
                strategy_return_pct=float(args["strategy_return_pct"]),
                benchmark_return_pct=float(args.get("benchmark_return_pct", 0.0)),
                note=str(args.get("note", "via mcp")),
                notify=True,
                settings=settings,
            )
            return {
                "strategy_key": strat.strategy_key,
                "state": strat.state,
                "action": ev["action"],
                "reason": ev["reason"],
                "peak_evalue": ev["metrics"]["peak_evalue"],
            }, False

        return {"error": f"Unknown tool '{name}'"}, True
    except Exception as exc:
        return {"error": str(exc)}, True


def handle_mcp_jsonrpc(
    payload: dict[str, Any],
    *,
    db: Session,
    settings: Settings,
) -> dict[str, Any] | None:
    """Process one MCP JSON-RPC 2.0 request and return a JSON-RPC response (or None for notifications)."""
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id") if isinstance(payload, dict) else None,
            "error": {"code": -32600, "message": "Invalid JSON-RPC 2.0 request"},
        }

    req_id = payload.get("id")
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    # Notifications have no `id` and expect no reply
    if req_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "quantseal", "version": __version__},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": QUANTSEAL_MCP_TOOLS}}

    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        tool_args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        data, is_err = _execute_tool(tool_name, tool_args, db, settings)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}],
                "isError": is_err,
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_mcp_server(settings: Settings | None = None) -> int:
    """Run QuantSeal as a local stdio MCP server (`python -m quantseal mcp`)."""
    cfg = settings or get_settings()
    configure_database(cfg.resolved_database_url())
    factory = get_session_factory()

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            req = json.loads(text)
        except ValueError:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue

        with factory() as db:
            resp = handle_mcp_jsonrpc(req, db=db, settings=cfg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
