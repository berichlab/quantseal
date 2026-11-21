"""Command-line entrypoint for QuantSeal (`python -m quantseal` or `quantseal`)."""
from __future__ import annotations

import argparse
import json
import sys

import uvicorn

from quantseal.config import get_settings
from quantseal.data.base import LoaderConfig
from quantseal.discovery.campaign import CampaignBudget, CampaignConfig, run_or_resume_campaign
from quantseal.discovery.evaluator import EvaluatorConfig
from quantseal.runtime.shadow_service import campaigns_root, index_campaign_state
from quantseal.storage.db import configure_database, get_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quantseal",
        description="QuantSeal — Self-hosted anti-overfitting autonomous quant research lab.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the QuantSeal web server and 24/7 scheduler")
    serve_p.add_argument("--host", default=None)
    serve_p.add_argument("--port", type=int, default=None)

    run_p = sub.add_parser("run-campaign", help="Run an immutable bounded discovery campaign from CLI")
    run_p.add_argument("--campaign-id", required=True)
    run_p.add_argument("--source", default="demo", choices=["demo", "yahoo", "crypto", "csv"])
    run_p.add_argument("--cost-preset", default="us_equities")
    run_p.add_argument("--csv-dir", default=None)
    run_p.add_argument("--development-only", action="store_true")
    run_p.add_argument("--prior-campaign-id", default=None)

    sub.add_parser("mcp", help="Run QuantSeal as a stdio MCP server (for Claude Desktop / Cursor / Codex)")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "mcp":
        from quantseal.mcp.server import run_stdio_mcp_server

        return run_stdio_mcp_server(settings)

    if args.command == "serve":
        uvicorn.run(
            "quantseal.api.main:app",
            host=args.host or settings.host,
            port=args.port or settings.port,
            log_level="info",
        )
        return 0

    if args.command == "run-campaign":
        configure_database(settings.resolved_database_url())
        cfg = CampaignConfig(
            campaign_id=args.campaign_id,
            budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0),
            loader=LoaderConfig(source=args.source, csv_dir=args.csv_dir),
            evaluator=EvaluatorConfig(cost_preset=args.cost_preset),
            prior_campaign_id=args.prior_campaign_id,
            development_only=args.development_only,
        )
        state = run_or_resume_campaign(cfg, storage_root=campaigns_root(settings))
        with get_session_factory()() as db:
            index_campaign_state(db, state)
        print(
            json.dumps(
                {
                    "campaign_id": state["campaign_id"],
                    "status": state["status"],
                    "config_hash": state["config_hash"],
                    "data_hash": state["data_hash"],
                    "code_hash": state["code_hash"],
                    "summary": state["summary"],
                },
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
