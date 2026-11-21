"""REST API endpoints for QuantSeal Research Console and programmatic access."""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from quantseal import __version__
from quantseal.api.auth import (
    clear_session_cookie,
    is_authenticated,
    require_auth,
    set_session_cookie,
    verify_password,
)
from quantseal.config import Settings, get_settings
from quantseal.core.costs import MARKET_COST_PRESETS
from quantseal.core.evalue import DEFAULT_ALPHA, DEFAULT_SCALE
from quantseal.core.gates import audit_trade_records
from quantseal.core.ladder import LadderPolicy, evaluate_ladder_transition
from quantseal.data.base import LoaderConfig
from quantseal.discovery.campaign import (
    CampaignBudget,
    CampaignConfig,
    CampaignError,
    CampaignImmutableMismatchError,
    compute_code_hash,
    run_or_resume_campaign,
)
from quantseal.discovery.evaluator import EvaluatorConfig
from quantseal.discovery.llm import LLMConfig
from quantseal.mcp import (
    QUANTSEAL_MCP_TOOLS,
    MCPClientError,
    MCPServerConfig,
    call_mcp_tool,
    collect_discovery_mcp_evidence,
    discover_mcp_tools,
    handle_mcp_jsonrpc,
)
from quantseal.runtime.notifier import dispatch_notification
from quantseal.runtime.scheduler import get_scheduler
from quantseal.runtime.shadow_service import (
    build_llm_config,
    build_notification_config,
    campaigns_root,
    enroll_strategy_to_shadow,
    get_effective_runtime_config,
    index_campaign_state,
    load_campaign_state_file,
    record_shadow_observation,
)
from quantseal.storage.db import get_db
from quantseal.storage.models import (
    CampaignIndex,
    EventLog,
    MCPServerRecord,
    RuntimeSetting,
    ShadowObservation,
    ShadowStrategy,
)

router = APIRouter(prefix="/api", tags=["quantseal"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


class CreateCampaignRequest(BaseModel):
    campaign_id: str = Field(..., min_length=2, max_length=64)
    source: str = Field(default="demo")
    symbols: list[str] = Field(default_factory=list)
    cost_preset: str = Field(default="us_equities")
    development_only: bool = Field(default=True)
    prior_campaign_id: str | None = Field(default=None)
    use_llm: bool = Field(default=False)
    use_mcp: bool = Field(default=False)
    max_ai_variants: int = Field(default=3, ge=0, le=10)
    max_days: int = Field(default=220, ge=30, le=1500)
    warmup_days: int = Field(default=60, ge=15, le=200)
    csv_dir: str | None = Field(default=None)


class ObservationRequest(BaseModel):
    obs_date: str
    strategy_return_pct: float
    benchmark_return_pct: float = 0.0
    note: str = ""


class AuditTradesRequest(BaseModel):
    trades: list[dict[str, Any]] | None = None
    csv_text: str | None = None
    min_trades: int = Field(default=15, ge=5, le=5000)
    min_avg_net_pct: float = Field(default=0.10)
    min_profit_factor: float = Field(default=1.10, ge=0.5)
    max_single_asset_pct: float = Field(default=25.0, ge=5.0, le=100.0)
    evalue_alpha: float = Field(default=DEFAULT_ALPHA, gt=0.0001, lt=0.5)
    evalue_scale: float = Field(default=DEFAULT_SCALE, gt=1.0, le=200.0)


class SettingsUpdateRequest(BaseModel):
    llm: dict[str, Any] | None = None
    market: dict[str, Any] | None = None
    notifications: dict[str, Any] | None = None
    scheduler: dict[str, Any] | None = None


class MCPServerCreateRequest(BaseModel):
    server_id: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{1,63}$")
    name: str = Field(..., min_length=2, max_length=120)
    transport: str = Field(default="http")
    url: str = Field(default="")
    headers: dict[str, str] = Field(default_factory=dict)
    command: str = Field(default="")
    args: list[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)
    include_in_discovery: bool = Field(default=False)
    discovery_tools: list[dict[str, Any]] = Field(default_factory=list)


class MCPServerUpdateRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    command: str | None = None
    args: list[str] | None = None
    enabled: bool | None = None
    include_in_discovery: bool | None = None
    discovery_tools: list[dict[str, Any]] | None = None


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

@router.get("/auth/status")
def auth_status(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "auth_enabled": bool(settings.admin_password.strip()),
        "authenticated": is_authenticated(request, settings),
        "version": __version__,
    }


@router.post("/auth/login")
def auth_login(
    payload: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not verify_password(payload.password, settings.admin_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    set_session_cookie(response, settings)
    return {"ok": True}


@router.post("/auth/logout")
def auth_logout(response: Response) -> dict[str, Any]:
    clear_session_cookie(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/overview")
def get_overview(
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    campaigns = db.query(CampaignIndex).order_by(CampaignIndex.updated_at.desc()).all()
    shadows = db.query(ShadowStrategy).order_by(ShadowStrategy.peak_evalue.desc()).all()
    events = db.query(EventLog).order_by(EventLog.created_at.desc()).limit(12).all()

    state_counts = {"shadow": 0, "paper": 0, "live_candidate": 0, "live": 0, "retired": 0}
    for s in shadows:
        if s.state in state_counts:
            state_counts[s.state] += 1

    featured_shadow: dict[str, Any] | None = None
    if shadows:
        top = shadows[0]
        obs_rows = (
            db.query(ShadowObservation)
            .filter_by(strategy_id=top.id)
            .order_by(ShadowObservation.obs_date.asc())
            .all()
        )
        ev = evaluate_ladder_transition(
            top.state,
            [
                {"strategy_return_pct": o.strategy_return_pct, "benchmark_return_pct": o.benchmark_return_pct}
                for o in obs_rows
            ],
        )
        featured_shadow = {
            "strategy_key": top.strategy_key,
            "title": top.title,
            "state": top.state,
            "peak_evalue": top.peak_evalue,
            "evalue": top.evalue,
            "observations_count": top.observations_count,
            "cumulative_excess_pct": top.cumulative_excess_pct,
            "series": [
                {
                    "date": obs_rows[idx].obs_date.isoformat(),
                    **pt,
                }
                for idx, pt in enumerate(ev["metrics"].get("evalue_series", []))
            ],
            "shadow_threshold": ev["metrics"]["shadow_threshold"],
            "live_threshold": ev["metrics"]["live_threshold"],
        }

    eff_llm = build_llm_config(db, settings)
    return {
        "version": __version__,
        "engine_code_hash": compute_code_hash(),
        "auth_enabled": bool(settings.admin_password.strip()),
        "llm_configured": eff_llm.is_configured(),
        "llm_provider": eff_llm.provider,
        "llm_model": eff_llm.model,
        "kpis": {
            "total_campaigns": len(campaigns),
            "sealed_campaigns": sum(1 for c in campaigns if c.validation_evaluated_once),
            "pending_validation": sum(1 for c in campaigns if not c.validation_evaluated_once),
            "active_shadow_strategies": sum(
                state_counts[k] for k in ("shadow", "paper", "live_candidate", "live")
            ),
            "promoted_strategies": state_counts["paper"] + state_counts["live_candidate"] + state_counts["live"],
            "retired_strategies": state_counts["retired"],
            "highest_peak_evalue": round(max((s.peak_evalue for s in shadows), default=1.0), 2),
        },
        "ladder_counts": state_counts,
        "featured_shadow": featured_shadow,
        "scheduler": get_scheduler().status(),
        "recent_events": [
            {
                "id": e.id,
                "category": e.category,
                "level": e.level,
                "message": e.message,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/campaigns")
def list_campaigns(
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.query(CampaignIndex).order_by(CampaignIndex.created_at.desc()).all()
    return {
        "campaigns": [
            {
                "campaign_id": r.campaign_id,
                "status": r.status,
                "source": r.source,
                "cost_preset": r.cost_preset,
                "config_hash": r.config_hash,
                "data_hash": r.data_hash,
                "code_hash": r.code_hash,
                "prior_campaign_id": r.prior_campaign_id,
                "validation_evaluated_once": r.validation_evaluated_once,
                "validation_contaminated": r.validation_contaminated,
                "total_candidates": r.total_candidates,
                "dev_passed": r.dev_passed,
                "qualified_count": r.qualified_count,
                "summary": r.summary_json,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ],
        "cost_presets": {k: v.to_dict() for k, v in MARKET_COST_PRESETS.items()},
    }


@router.get("/campaigns/{campaign_id}")
def get_campaign_detail(
    campaign_id: str,
    _auth: dict[str, Any] = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    state = load_campaign_state_file(campaign_id, settings)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    return state


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CreateCampaignRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if db.query(CampaignIndex).filter_by(campaign_id=payload.campaign_id).first():
        raise HTTPException(
            status_code=409,
            detail=f"Campaign '{payload.campaign_id}' already exists (campaigns are immutable).",
        )

    llm_cfg = build_llm_config(db, settings) if payload.use_llm else LLMConfig(provider="none")
    cfg = CampaignConfig(
        campaign_id=payload.campaign_id,
        budget=CampaignBudget(
            max_proposal_calls=1 if (payload.use_llm and llm_cfg.is_configured()) else 0,
            max_ai_variants=payload.max_ai_variants if payload.use_llm else 0,
            max_total_variants=4 + (payload.max_ai_variants if payload.use_llm else 0),
            max_days=payload.max_days,
            warmup_days=payload.warmup_days,
        ),
        loader=LoaderConfig(
            source=payload.source,
            symbols=tuple(s.strip().upper() for s in payload.symbols if s.strip()),
            max_days=payload.max_days,
            warmup_days=payload.warmup_days,
            csv_dir=payload.csv_dir,
        ),
        evaluator=EvaluatorConfig(cost_preset=payload.cost_preset),
        prior_campaign_id=payload.prior_campaign_id or None,
        development_only=payload.development_only,
    )

    mcp_evidence: list[dict[str, Any]] | None = None
    if payload.use_mcp:
        mcp_rows = (
            db.query(MCPServerRecord)
            .filter_by(enabled=True, include_in_discovery=True)
            .all()
        )
        mcp_configs = [_record_to_mcp_config(r) for r in mcp_rows]
        if mcp_configs:
            mcp_evidence = collect_discovery_mcp_evidence(
                mcp_configs, allow_stdio=settings.allow_stdio_mcp
            )

    try:
        state = run_or_resume_campaign(
            cfg,
            storage_root=campaigns_root(settings),
            llm_config=llm_cfg,
            external_mcp_evidence=mcp_evidence,
        )
    except (CampaignError, ValueError, RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    index_campaign_state(db, state)
    db.add(
        EventLog(
            category="campaign",
            level="info",
            message=f"Created campaign '{payload.campaign_id}' ({state.get('status')}).",
            payload_json=state.get("summary") or {},
        )
    )
    db.commit()
    return state


@router.post("/campaigns/{campaign_id}/validate-once")
def unlock_single_shot_validation(
    campaign_id: str,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    existing = load_campaign_state_file(campaign_id, settings)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    if existing.get("validation_evaluated_once"):
        raise HTTPException(
            status_code=409,
            detail="Single-shot validation seal has already been consumed for this campaign.",
        )

    cfg_dict = existing.get("config") or {}
    ev_dict = cfg_dict.get("evaluator") or {}
    ldr_dict = cfg_dict.get("loader") or {}
    bgt_dict = cfg_dict.get("budget") or {}

    cfg = CampaignConfig(
        campaign_id=campaign_id,
        budget=CampaignBudget(**{k: v for k, v in bgt_dict.items() if k in CampaignBudget.__dataclass_fields__}),
        loader=LoaderConfig(
            source=ldr_dict.get("source", "demo"),
            symbols=tuple(ldr_dict.get("symbols") or ()),
            max_assets=int(ldr_dict.get("max_assets", 30)),
            max_days=int(ldr_dict.get("max_days", 220)),
            warmup_days=int(ldr_dict.get("warmup_days", 60)),
            csv_dir=ldr_dict.get("csv_dir"),
        ),
        evaluator=EvaluatorConfig(
            cost_preset=ev_dict.get("cost_preset", "us_equities"),
            min_dev_trades=int(ev_dict.get("min_dev_trades", 10)),
            min_dev_signal_days=int(ev_dict.get("min_dev_signal_days", 5)),
            min_val_trades=int(ev_dict.get("min_val_trades", 5)),
            min_val_signal_days=int(ev_dict.get("min_val_signal_days", 3)),
            max_daily_active_slots=int(ev_dict.get("max_daily_active_slots", 5)),
            bootstrap_block_days=int(ev_dict.get("bootstrap_block_days", 5)),
            bootstrap_iterations=int(ev_dict.get("bootstrap_iterations", 400)),
            exit_policy=ev_dict.get("exit_policy"),
        ),
        prior_campaign_id=cfg_dict.get("prior_campaign_id"),
        development_only=False,
    )

    try:
        state = run_or_resume_campaign(
            cfg,
            storage_root=campaigns_root(settings),
            unlock_validation=True,
        )
    except CampaignImmutableMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    index_campaign_state(db, state)
    db.add(
        EventLog(
            category="campaign",
            level="info",
            message=f"Sealed single-shot validation for '{campaign_id}': {state['summary'].get('qualified_for_shadow', 0)} qualified.",
            payload_json=state.get("summary") or {},
        )
    )
    db.commit()
    return state


@router.post("/campaigns/{campaign_id}/enroll/{spec_id}")
def enroll_campaign_spec(
    campaign_id: str,
    spec_id: str,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    state = load_campaign_state_file(campaign_id, settings)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    match = next((e for e in (state.get("experiments") or []) if e.get("spec_id") == spec_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found in '{campaign_id}'")
    key = f"{spec_id}__{campaign_id}"[:96]
    strat = enroll_strategy_to_shadow(
        db,
        strategy_key=key,
        title=str(match.get("title") or spec_id),
        spec_json=match.get("spec") or {},
        source_campaign_id=campaign_id,
    )
    return {
        "strategy_key": strat.strategy_key,
        "state": strat.state,
        "title": strat.title,
    }


# ---------------------------------------------------------------------------
# Shadow Ladder & Anytime-Valid E-Values
# ---------------------------------------------------------------------------

@router.get("/shadow")
def list_shadow_strategies(
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.query(ShadowStrategy).order_by(ShadowStrategy.peak_evalue.desc()).all()
    policy = LadderPolicy().to_dict()
    return {
        "policy": policy,
        "strategies": [
            {
                "strategy_key": r.strategy_key,
                "title": r.title,
                "source_campaign_id": r.source_campaign_id,
                "spec_fingerprint": r.spec_fingerprint,
                "state": r.state,
                "observations_count": r.observations_count,
                "evalue": round(r.evalue, 4),
                "peak_evalue": round(r.peak_evalue, 4),
                "cumulative_return_pct": round(r.cumulative_return_pct, 4),
                "cumulative_excess_pct": round(r.cumulative_excess_pct, 4),
                "max_drawdown_pct": round(r.max_drawdown_pct, 4),
                "consecutive_losses": r.consecutive_losses,
                "last_reason": r.last_reason,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/shadow/{strategy_key}")
def get_shadow_detail(
    strategy_key: str,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    strat = db.query(ShadowStrategy).filter_by(strategy_key=strategy_key).first()
    if strat is None:
        raise HTTPException(status_code=404, detail=f"Shadow strategy '{strategy_key}' not found")
    obs_rows = (
        db.query(ShadowObservation)
        .filter_by(strategy_id=strat.id)
        .order_by(ShadowObservation.obs_date.asc())
        .all()
    )
    ev = evaluate_ladder_transition(
        strat.state,
        [
            {"strategy_return_pct": o.strategy_return_pct, "benchmark_return_pct": o.benchmark_return_pct}
            for o in obs_rows
        ],
    )
    series = ev["metrics"].get("evalue_series", [])
    return {
        "strategy_key": strat.strategy_key,
        "title": strat.title,
        "source_campaign_id": strat.source_campaign_id,
        "spec_fingerprint": strat.spec_fingerprint,
        "spec": strat.spec_json,
        "state": strat.state,
        "observations_count": strat.observations_count,
        "evalue": round(strat.evalue, 4),
        "peak_evalue": round(strat.peak_evalue, 4),
        "cumulative_return_pct": round(strat.cumulative_return_pct, 4),
        "cumulative_excess_pct": round(strat.cumulative_excess_pct, 4),
        "max_drawdown_pct": round(strat.max_drawdown_pct, 4),
        "consecutive_losses": strat.consecutive_losses,
        "last_reason": strat.last_reason,
        "policy": LadderPolicy().to_dict(),
        "shadow_threshold": ev["metrics"]["shadow_threshold"],
        "live_threshold": ev["metrics"]["live_threshold"],
        "series": [
            {
                "date": obs_rows[idx].obs_date.isoformat(),
                "strategy_return_pct": obs_rows[idx].strategy_return_pct,
                "benchmark_return_pct": obs_rows[idx].benchmark_return_pct,
                "note": obs_rows[idx].note,
                **pt,
            }
            for idx, pt in enumerate(series)
        ],
    }


@router.post("/shadow/{strategy_key}/observations")
def add_shadow_observation(
    strategy_key: str,
    payload: ObservationRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    strat = db.query(ShadowStrategy).filter_by(strategy_key=strategy_key).first()
    if strat is None:
        raise HTTPException(status_code=404, detail=f"Shadow strategy '{strategy_key}' not found")
    try:
        obs_date = dt.date.fromisoformat(payload.obs_date.strip()[:10])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="obs_date must be YYYY-MM-DD") from exc

    result = record_shadow_observation(
        db,
        strat,
        obs_date=obs_date,
        strategy_return_pct=payload.strategy_return_pct,
        benchmark_return_pct=payload.benchmark_return_pct,
        note=payload.note,
        notify=True,
        settings=settings,
    )
    return {
        "strategy_key": strat.strategy_key,
        "state": strat.state,
        "evaluation": result,
    }


# ---------------------------------------------------------------------------
# Standalone Statistical Gate & E-Value Auditor (for ANY external backtest!)
# ---------------------------------------------------------------------------

def _parse_trades_csv(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    trades: list[dict[str, Any]] = []
    for row in reader:
        norm = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        if not norm:
            continue
        net_raw = norm.get("net") or norm.get("net_return_pct") or norm.get("return_pct") or norm.get("pnl_pct")
        if net_raw is None or net_raw == "":
            continue
        item: dict[str, Any] = {
            "entry_date": norm.get("entry_date") or norm.get("trade_date") or norm.get("date") or "unknown",
            "symbol": norm.get("symbol") or norm.get("ticker") or norm.get("stock_id") or "UNKNOWN",
            "sector": norm.get("sector") or norm.get("industry") or None,
            "net": float(net_raw),
        }
        if norm.get("gross") not in (None, ""):
            item["gross"] = float(norm["gross"])
        elif norm.get("cost") not in (None, ""):
            item["cost"] = float(norm["cost"])
        trades.append(item)
    return trades


@router.post("/audit/trades")
def audit_external_trades(
    payload: AuditTradesRequest,
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    trades = list(payload.trades or [])
    if not trades and payload.csv_text:
        try:
            trades = _parse_trades_csv(payload.csv_text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc
    if not trades:
        raise HTTPException(status_code=400, detail="Provide non-empty 'trades' array or 'csv_text'.")
    return audit_trade_records(
        trades,
        min_trades=payload.min_trades,
        min_avg_net_pct=payload.min_avg_net_pct,
        min_profit_factor=payload.min_profit_factor,
        max_single_asset_pct=payload.max_single_asset_pct,
        evalue_alpha=payload.evalue_alpha,
        evalue_scale=payload.evalue_scale,
    )


# ---------------------------------------------------------------------------
# Runtime Settings, Scheduler & Notifications
# ---------------------------------------------------------------------------

def _mask_secret(val: str) -> str:
    s = str(val or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "••••••••"
    return s[:4] + "••••" + s[-4:]


@router.get("/settings")
def get_runtime_settings(
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    eff = get_effective_runtime_config(db, settings)
    return {
        "llm": {
            "provider": eff["llm"]["provider"],
            "model": eff["llm"]["model"],
            "base_url": eff["llm"]["base_url"],
            "api_key_configured": bool(str(eff["llm"]["api_key"]).strip()),
            "api_key_masked": _mask_secret(eff["llm"]["api_key"]),
        },
        "market": eff["market"],
        "notifications": {
            "telegram_configured": bool(
                str(eff["notifications"]["telegram_bot_token"]).strip()
                and str(eff["notifications"]["telegram_chat_id"]).strip()
            ),
            "telegram_chat_id": eff["notifications"]["telegram_chat_id"],
            "discord_configured": bool(str(eff["notifications"]["discord_webhook_url"]).strip()),
            "generic_webhook_configured": bool(str(eff["notifications"]["generic_webhook_url"]).strip()),
        },
        "scheduler": {
            **eff["scheduler"],
            "runtime": get_scheduler().status(),
        },
    }


def _upsert_setting(db: Session, key: str, value: dict[str, Any]) -> None:
    now = dt.datetime.now(dt.UTC)
    row = db.query(RuntimeSetting).filter_by(key=key).first()
    if row is None:
        db.add(RuntimeSetting(key=key, value_json=value, updated_at=now))
    else:
        merged = dict(row.value_json or {})
        merged.update(value)
        row.value_json = merged
        row.updated_at = now


@router.put("/settings")
def update_runtime_settings(
    payload: SettingsUpdateRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if payload.llm is not None:
        clean_llm = {k: v for k, v in payload.llm.items() if k in ("provider", "model", "base_url", "api_key")}
        if clean_llm.get("api_key") in ("", None) and "api_key" in clean_llm:
            clean_llm.pop("api_key")  # Do not wipe stored key when field left blank
        _upsert_setting(db, "llm", clean_llm)
    if payload.market is not None:
        clean_mkt = {k: v for k, v in payload.market.items() if k in ("default_preset", "default_symbols")}
        _upsert_setting(db, "market", clean_mkt)
    if payload.notifications is not None:
        clean_not = {
            k: v
            for k, v in payload.notifications.items()
            if k in ("telegram_bot_token", "telegram_chat_id", "discord_webhook_url", "generic_webhook_url")
            and v not in (None, "")
        }
        if clean_not:
            _upsert_setting(db, "notifications", clean_not)
    if payload.scheduler is not None:
        clean_sched = {k: v for k, v in payload.scheduler.items() if k in ("enabled", "shadow_cron", "campaign_cron")}
        _upsert_setting(db, "scheduler", clean_sched)

    db.commit()
    get_scheduler().reload_jobs()
    return get_runtime_settings(_auth=_auth, db=db, settings=settings)


@router.post("/notifications/test")
def test_notification(
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    cfg = build_notification_config(db, settings)
    return dispatch_notification(
        "Test Alert",
        "Your QuantSeal self-hosted research lab notification channel is connected.",
        cfg,
    )


@router.post("/scheduler/run-shadow")
def trigger_shadow_reconcile(
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    return get_scheduler().run_shadow_reconcile_job()


# ---------------------------------------------------------------------------
# MCP Hub: Connect External MCP Servers + Expose QuantSeal as an MCP Server
# ---------------------------------------------------------------------------

def _record_to_mcp_config(row: MCPServerRecord) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=row.server_id,
        name=row.name,
        transport=row.transport,
        url=row.url,
        headers=dict(row.headers_json or {}),
        command=row.command,
        args=tuple(row.args_json or ()),
        enabled=bool(row.enabled),
        include_in_discovery=bool(row.include_in_discovery),
        discovery_tools=tuple(row.discovery_tools_json or ()),
    )


def _serialize_mcp_server(row: MCPServerRecord) -> dict[str, Any]:
    masked_headers = {
        str(k): _mask_secret(str(v))
        for k, v in (row.headers_json or {}).items()
    }
    return {
        "server_id": row.server_id,
        "name": row.name,
        "transport": row.transport,
        "url": row.url,
        "headers_masked": masked_headers,
        "command": row.command,
        "args": list(row.args_json or []),
        "enabled": bool(row.enabled),
        "include_in_discovery": bool(row.include_in_discovery),
        "discovery_tools": list(row.discovery_tools_json or []),
        "discovered_tools": list(row.discovered_tools_json or []),
        "tool_count": len(row.discovered_tools_json or []),
        "last_status": row.last_status,
        "last_error": row.last_error,
        "last_latency_ms": row.last_latency_ms,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/mcp/servers")
def list_mcp_servers(
    request: Request,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    rows = db.query(MCPServerRecord).order_by(MCPServerRecord.created_at.desc()).all()
    origin = str(request.base_url).rstrip("/")
    return {
        "allow_stdio_mcp": bool(settings.allow_stdio_mcp),
        "servers": [_serialize_mcp_server(r) for r in rows],
        "quantseal_mcp_server": {
            "http_endpoint": f"{origin}/api/mcp",
            "stdio_command": "python -m quantseal mcp",
            "tools": QUANTSEAL_MCP_TOOLS,
        },
    }


@router.post("/mcp/servers", status_code=status.HTTP_201_CREATED)
def create_mcp_server(
    payload: MCPServerCreateRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if db.query(MCPServerRecord).filter_by(server_id=payload.server_id).first():
        raise HTTPException(
            status_code=409,
            detail=f"MCP server '{payload.server_id}' already exists.",
        )

    cfg = MCPServerConfig(
        server_id=payload.server_id,
        name=payload.name.strip(),
        transport=payload.transport.strip().lower(),
        url=payload.url.strip(),
        headers=payload.headers,
        command=payload.command.strip(),
        args=tuple(payload.args),
        enabled=payload.enabled,
        include_in_discovery=payload.include_in_discovery,
        discovery_tools=tuple(payload.discovery_tools),
    )
    try:
        cfg.validate(allow_stdio=settings.allow_stdio_mcp)
    except MCPClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = dt.datetime.now(dt.UTC)
    row = MCPServerRecord(
        server_id=cfg.server_id,
        name=cfg.name,
        transport=cfg.transport,
        url=cfg.url,
        headers_json=dict(cfg.headers),
        command=cfg.command,
        args_json=list(cfg.args),
        enabled=cfg.enabled,
        include_in_discovery=cfg.include_in_discovery,
        discovery_tools_json=list(cfg.discovery_tools),
        discovered_tools_json=[],
        last_status="unverified",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        EventLog(
            category="mcp",
            level="info",
            message=f"Registered external MCP server '{cfg.server_id}' ({cfg.transport}).",
            payload_json={"server_id": cfg.server_id, "transport": cfg.transport},
        )
    )
    db.commit()
    db.refresh(row)
    return _serialize_mcp_server(row)


@router.put("/mcp/servers/{server_id}")
def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdateRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    row = db.query(MCPServerRecord).filter_by(server_id=server_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.url is not None:
        row.url = payload.url.strip()
    if payload.headers is not None:
        merged = dict(row.headers_json or {})
        for k, v in payload.headers.items():
            if v == "":
                merged.pop(k, None)
            else:
                merged[k] = v
        row.headers_json = merged
    if payload.command is not None:
        row.command = payload.command.strip()
    if payload.args is not None:
        row.args_json = list(payload.args)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.include_in_discovery is not None:
        row.include_in_discovery = payload.include_in_discovery
    if payload.discovery_tools is not None:
        row.discovery_tools_json = list(payload.discovery_tools)

    try:
        _record_to_mcp_config(row).validate(allow_stdio=settings.allow_stdio_mcp)
    except MCPClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row.updated_at = dt.datetime.now(dt.UTC)
    db.commit()
    db.refresh(row)
    return _serialize_mcp_server(row)


@router.delete("/mcp/servers/{server_id}")
def delete_mcp_server(
    server_id: str,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.query(MCPServerRecord).filter_by(server_id=server_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
    db.delete(row)
    db.commit()
    return {"deleted": server_id}


@router.post("/mcp/servers/{server_id}/discover")
def discover_external_mcp_server(
    server_id: str,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    row = db.query(MCPServerRecord).filter_by(server_id=server_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")

    cfg = _record_to_mcp_config(row)
    try:
        res = discover_mcp_tools(cfg, allow_stdio=settings.allow_stdio_mcp)
        row.discovered_tools_json = res["tools"]
        row.last_status = "connected"
        row.last_error = ""
        row.last_latency_ms = res["latency_ms"]
        row.updated_at = dt.datetime.now(dt.UTC)
        db.commit()
        db.refresh(row)
        return {"server": _serialize_mcp_server(row), "discovery": res}
    except Exception as exc:
        row.last_status = "error"
        row.last_error = str(exc)[:500]
        row.updated_at = dt.datetime.now(dt.UTC)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mcp/servers/{server_id}/call")
def call_external_mcp_server(
    server_id: str,
    payload: MCPToolCallRequest,
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    row = db.query(MCPServerRecord).filter_by(server_id=server_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")

    cfg = _record_to_mcp_config(row)
    try:
        return call_mcp_tool(
            cfg,
            payload.tool_name,
            payload.arguments,
            allow_stdio=settings.allow_stdio_mcp,
        )
    except MCPClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mcp")
def quantseal_mcp_http_endpoint(
    payload: dict[str, Any],
    _auth: dict[str, Any] = Depends(require_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Built-in QuantSeal Streamable HTTP MCP Server endpoint (JSON-RPC 2.0)."""
    resp = handle_mcp_jsonrpc(payload, db=db, settings=settings)
    if resp is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return resp

