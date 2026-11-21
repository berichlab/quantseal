"""Campaign indexing, forward shadow ladder tracking, and first-boot demo bootstrap."""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from quantseal.config import Settings, get_settings
from quantseal.core.ladder import LadderPolicy, evaluate_ladder_transition
from quantseal.data.base import LoaderConfig
from quantseal.discovery.campaign import (
    CampaignBudget,
    CampaignConfig,
    run_or_resume_campaign,
)
from quantseal.discovery.evaluator import EvaluatorConfig
from quantseal.discovery.llm import LLMConfig
from quantseal.runtime.notifier import NotificationConfig, dispatch_notification
from quantseal.storage.models import (
    CampaignIndex,
    EventLog,
    RuntimeSetting,
    ShadowObservation,
    ShadowStrategy,
)

logger = logging.getLogger(__name__)


def campaigns_root(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    root = cfg.resolved_data_dir() / "campaigns"
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_campaign_state_file(campaign_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    path = campaigns_root(settings) / campaign_id / "state.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def index_campaign_state(db: Session, state: dict[str, Any]) -> CampaignIndex:
    cid = str(state["campaign_id"])
    cfg = state.get("config") or {}
    loader = cfg.get("loader") or {}
    ev = cfg.get("evaluator") or {}
    summary = state.get("summary") or {}

    row = db.query(CampaignIndex).filter_by(campaign_id=cid).first()
    now = dt.datetime.now(dt.UTC)
    if row is None:
        row = CampaignIndex(
            campaign_id=cid,
            status=str(state.get("status", "running")),
            source=str(loader.get("source", "demo")),
            cost_preset=str(ev.get("cost_preset", "us_equities")),
            config_hash=str(state.get("config_hash", "")),
            data_hash=str(state.get("data_hash", "")),
            code_hash=str(state.get("code_hash", "")),
            prior_campaign_id=state.get("prior_campaign_id"),
            validation_evaluated_once=bool(state.get("validation_evaluated_once")),
            validation_contaminated=bool(state.get("validation_holdout_contaminated")),
            total_candidates=int(summary.get("total_candidates", 0)),
            dev_passed=int(summary.get("dev_passed", 0)),
            qualified_count=int(summary.get("qualified_for_shadow", 0)),
            summary_json=summary,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.status = str(state.get("status", row.status))
        row.validation_evaluated_once = bool(state.get("validation_evaluated_once"))
        row.validation_contaminated = bool(state.get("validation_holdout_contaminated"))
        row.total_candidates = int(summary.get("total_candidates", 0))
        row.dev_passed = int(summary.get("dev_passed", 0))
        row.qualified_count = int(summary.get("qualified_for_shadow", 0))
        row.summary_json = summary
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def get_effective_runtime_config(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    """Merge environment defaults with persisted RuntimeSetting overrides."""
    cfg = settings or get_settings()
    stored: dict[str, Any] = {}
    for row in db.query(RuntimeSetting).all():
        stored[row.key] = row.value_json

    llm_row = stored.get("llm") or {}
    market_row = stored.get("market") or {}
    notif_row = stored.get("notifications") or {}
    sched_row = stored.get("scheduler") or {}

    return {
        "llm": {
            "provider": llm_row.get("provider", cfg.llm_provider),
            "api_key": llm_row.get("api_key", cfg.llm_api_key),
            "model": llm_row.get("model", cfg.llm_model),
            "base_url": llm_row.get("base_url", cfg.llm_base_url),
        },
        "market": {
            "default_preset": market_row.get("default_preset", cfg.default_market_preset),
            "default_symbols": market_row.get("default_symbols", cfg.default_symbol_list()),
        },
        "notifications": {
            "telegram_bot_token": notif_row.get("telegram_bot_token", cfg.telegram_bot_token),
            "telegram_chat_id": notif_row.get("telegram_chat_id", cfg.telegram_chat_id),
            "discord_webhook_url": notif_row.get("discord_webhook_url", cfg.discord_webhook_url),
            "generic_webhook_url": notif_row.get("generic_webhook_url", cfg.generic_webhook_url),
        },
        "scheduler": {
            "enabled": sched_row.get("enabled", cfg.scheduler_enabled),
            "shadow_cron": sched_row.get("shadow_cron", cfg.shadow_cron),
            "campaign_cron": sched_row.get("campaign_cron", cfg.campaign_cron),
        },
    }


def build_llm_config(db: Session, settings: Settings | None = None) -> LLMConfig:
    eff = get_effective_runtime_config(db, settings)["llm"]
    return LLMConfig(
        provider=str(eff.get("provider") or "none"),
        api_key=str(eff.get("api_key") or ""),
        model=str(eff.get("model") or "gpt-4o-mini"),
        base_url=str(eff.get("base_url") or ""),
    )


def build_notification_config(db: Session, settings: Settings | None = None) -> NotificationConfig:
    eff = get_effective_runtime_config(db, settings)["notifications"]
    return NotificationConfig(
        telegram_bot_token=str(eff.get("telegram_bot_token") or ""),
        telegram_chat_id=str(eff.get("telegram_chat_id") or ""),
        discord_webhook_url=str(eff.get("discord_webhook_url") or ""),
        generic_webhook_url=str(eff.get("generic_webhook_url") or ""),
    )


def recompute_shadow_strategy(
    db: Session,
    strategy: ShadowStrategy,
    *,
    policy: LadderPolicy = LadderPolicy(),
    notify: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Recompute E-value trajectory and ladder transition strictly from forward observations."""
    obs_rows = (
        db.query(ShadowObservation)
        .filter_by(strategy_id=strategy.id)
        .order_by(ShadowObservation.obs_date.asc())
        .all()
    )
    obs_dicts = [
        {
            "obs_date": o.obs_date.isoformat(),
            "strategy_return_pct": o.strategy_return_pct,
            "benchmark_return_pct": o.benchmark_return_pct,
        }
        for o in obs_rows
    ]
    evaluation = evaluate_ladder_transition(strategy.state, obs_dicts, policy=policy)
    m = evaluation["metrics"]

    prev_state = strategy.state
    strategy.state = evaluation["next_state"]
    strategy.observations_count = int(m["observations"])
    strategy.evalue = float(m["evalue"])
    strategy.peak_evalue = float(m["peak_evalue"])
    strategy.cumulative_return_pct = float(m["cumulative_return_pct"])
    strategy.cumulative_excess_pct = float(m["cumulative_excess_pct"])
    strategy.max_drawdown_pct = float(m["max_drawdown_pct"])
    strategy.consecutive_losses = int(m["consecutive_losses"])
    strategy.last_reason = str(evaluation["reason"])
    strategy.updated_at = dt.datetime.now(dt.UTC)

    if prev_state != strategy.state:
        event_msg = (
            f"Strategy '{strategy.strategy_key}' transitioned {prev_state} -> {strategy.state}: "
            f"{strategy.last_reason}"
        )
        db.add(
            EventLog(
                category="ladder",
                level="warning" if evaluation["action"] in ("demoted", "retired") else "info",
                message=event_msg,
                payload_json={"strategy_key": strategy.strategy_key, "action": evaluation["action"]},
            )
        )
        if notify:
            dispatch_notification(
                f"Ladder {evaluation['action'].upper()}: {strategy.strategy_key}",
                event_msg,
                build_notification_config(db, settings),
            )

    db.commit()
    db.refresh(strategy)
    return evaluation


def enroll_strategy_to_shadow(
    db: Session,
    *,
    strategy_key: str,
    title: str,
    spec_json: dict[str, Any],
    source_campaign_id: str | None = None,
) -> ShadowStrategy:
    existing = db.query(ShadowStrategy).filter_by(strategy_key=strategy_key).first()
    if existing:
        return existing
    now = dt.datetime.now(dt.UTC)
    strat = ShadowStrategy(
        strategy_key=strategy_key,
        title=title,
        source_campaign_id=source_campaign_id,
        spec_fingerprint=str(spec_json.get("fingerprint") or ""),
        spec_json=spec_json,
        state="shadow",
        created_at=now,
        updated_at=now,
    )
    db.add(strat)
    db.add(
        EventLog(
            category="ladder",
            level="info",
            message=f"Enrolled '{strategy_key}' into forward-only shadow tracking.",
            payload_json={"strategy_key": strategy_key, "source_campaign_id": source_campaign_id},
        )
    )
    db.commit()
    db.refresh(strat)
    return strat


def record_shadow_observation(
    db: Session,
    strategy: ShadowStrategy,
    *,
    obs_date: dt.date,
    strategy_return_pct: float,
    benchmark_return_pct: float = 0.0,
    note: str = "",
    notify: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Append or update one forward out-of-sample observation and re-evaluate ladder."""
    excess = round(float(strategy_return_pct) - float(benchmark_return_pct), 4)
    row = (
        db.query(ShadowObservation)
        .filter_by(strategy_id=strategy.id, obs_date=obs_date)
        .first()
    )
    if row is None:
        row = ShadowObservation(
            strategy_id=strategy.id,
            obs_date=obs_date,
            strategy_return_pct=round(float(strategy_return_pct), 4),
            benchmark_return_pct=round(float(benchmark_return_pct), 4),
            excess_return_pct=excess,
            note=note[:250],
        )
        db.add(row)
    else:
        row.strategy_return_pct = round(float(strategy_return_pct), 4)
        row.benchmark_return_pct = round(float(benchmark_return_pct), 4)
        row.excess_return_pct = excess
        row.note = note[:250]
    db.commit()
    return recompute_shadow_strategy(db, strategy, notify=notify, settings=settings)


def ensure_demo_seeded(db: Session, settings: Settings | None = None) -> bool:
    """Seed a deterministic demo campaign + pending campaign + 3 shadow strategies on an empty DB.

    Guarantees a rich, live research console within 60 seconds of a 1-Click Hostinger deploy
    even before the user adds any LLM API key or external webhook.
    """
    cfg = settings or get_settings()
    if not cfg.auto_demo:
        return False
    if db.query(CampaignIndex).count() > 0 or db.query(ShadowStrategy).count() > 0:
        return False

    logger.info("Bootstrapping deterministic QuantSeal demo workspace...")
    root = campaigns_root(cfg)

    # 1. Sealed completed demo campaign
    sealed_cfg = CampaignConfig(
        campaign_id="demo-us-sectors-v1",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_total_variants=4, max_assets=16, max_days=220, warmup_days=60),
        loader=LoaderConfig(source="demo", max_assets=16, max_days=220, warmup_days=60),
        evaluator=EvaluatorConfig(cost_preset="us_equities", min_dev_trades=8, min_dev_signal_days=4, min_val_trades=4, min_val_signal_days=2),
        development_only=False,
    )
    sealed_state = run_or_resume_campaign(sealed_cfg, storage_root=root)
    index_campaign_state(db, sealed_state)

    # 2. Pending development-only campaign so users can test clicking "Unlock Single-Shot Validation"
    pending_cfg = CampaignConfig(
        campaign_id="demo-pending-seal-v2",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_total_variants=4, max_assets=12, max_days=200, warmup_days=60),
        loader=LoaderConfig(source="demo", max_assets=12, max_days=200, warmup_days=60),
        evaluator=EvaluatorConfig(cost_preset="us_equities", min_dev_trades=8, min_dev_signal_days=4, min_val_trades=4, min_val_signal_days=2),
        development_only=True,
    )
    pending_state = run_or_resume_campaign(pending_cfg, storage_root=root)
    index_campaign_state(db, pending_state)

    # 3. Seed 3 realistic shadow ladder trajectories illustrating all 3 outcomes:
    #    (a) Genuine edge building anytime-valid E-value -> promoted to paper
    #    (b) Zero-edge null strategy -> stays in shadow with K ~ 1
    #    (c) High-drawdown overfit strategy -> circuit-breaker retired
    rng = np.random.default_rng(20261120)
    start_day = dt.date(2026, 8, 3)
    bdays: list[dt.date] = []
    cur = start_day
    while len(bdays) < 42:
        if cur.weekday() < 5:
            bdays.append(cur)
        cur += dt.timedelta(days=1)

    seed_specs = {e["spec_id"]: e["spec"] for e in sealed_state.get("experiments") or []}

    # (a) Strong forward edge -> promoted to paper
    s1 = enroll_strategy_to_shadow(
        db,
        strategy_key="vol_compression_breakout_v1",
        title="Volatility Compression Above MA20 (Demo Forward Track)",
        spec_json=seed_specs.get("seed_vol_compression_breakout", {}),
        source_campaign_id="demo-us-sectors-v1",
    )
    for d in bdays:
        bench = float(rng.normal(0.04, 0.75))
        strat = bench + float(rng.normal(2.2, 0.95))
        record_shadow_observation(db, s1, obs_date=d, strategy_return_pct=strat, benchmark_return_pct=bench, note="demo forward bar")

    # (b) Null noise strategy -> remains shadow near E-value ~ 1
    s2 = enroll_strategy_to_shadow(
        db,
        strategy_key="pullback_reclaim_null_v1",
        title="Short-Term Pullback Reclaim (Flat Null Control)",
        spec_json=seed_specs.get("seed_pullback_reclaim_in_uptrend", {}),
        source_campaign_id="demo-us-sectors-v1",
    )
    for d in bdays[:34]:
        bench = float(rng.normal(0.05, 0.75))
        strat = bench + float(rng.normal(0.0, 0.85))
        record_shadow_observation(db, s2, obs_date=d, strategy_return_pct=strat, benchmark_return_pct=bench, note="demo forward bar")

    # (c) Drawdown blowup -> auto-retired by circuit breaker
    s3 = enroll_strategy_to_shadow(
        db,
        strategy_key="high_beta_exhaustion_v1",
        title="High-Volume Oversold Rebound (Circuit-Breaker Retired)",
        spec_json=seed_specs.get("seed_volume_surge_mean_reversion", {}),
        source_campaign_id="demo-us-sectors-v1",
    )
    blowup_deltas = [0.6, 0.4, -1.8, -2.5, -3.2, -4.1, -3.9, -4.4, -3.8]
    for d, delta in zip(bdays[: len(blowup_deltas)], blowup_deltas, strict=True):
        record_shadow_observation(db, s3, obs_date=d, strategy_return_pct=delta, benchmark_return_pct=0.05, note="demo drawdown stress")

    db.add(
        EventLog(
            category="system",
            level="info",
            message="QuantSeal demo workspace initialized (2 campaigns, 3 forward shadow strategies).",
            payload_json={"campaigns": ["demo-us-sectors-v1", "demo-pending-seal-v2"]},
        )
    )
    db.commit()
    return True
