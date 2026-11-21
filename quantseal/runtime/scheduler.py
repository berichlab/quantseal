"""24/7 APScheduler background loop for scheduled shadow ticks and autonomous campaigns."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from quantseal.config import Settings, get_settings
from quantseal.data.base import LoaderConfig
from quantseal.discovery.campaign import CampaignBudget, CampaignConfig, run_or_resume_campaign
from quantseal.discovery.evaluator import EvaluatorConfig
from quantseal.runtime.notifier import dispatch_notification
from quantseal.runtime.shadow_service import (
    build_llm_config,
    build_notification_config,
    campaigns_root,
    get_effective_runtime_config,
    index_campaign_state,
    recompute_shadow_strategy,
)
from quantseal.storage.db import get_session_factory
from quantseal.storage.models import EventLog, ShadowStrategy

logger = logging.getLogger(__name__)


class QuantSealScheduler:
    """Manages periodic background research tasks for self-hosted 24/7 VPS deployments."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.reload_jobs()
        self._scheduler.start()
        self._started = True
        logger.info("QuantSeal background scheduler started.")

    def stop(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    def reload_jobs(self) -> None:
        for job in list(self._scheduler.get_jobs()):
            job.remove()

        factory = get_session_factory()
        with factory() as db:
            eff = get_effective_runtime_config(db, self.settings)["scheduler"]

        if not eff.get("enabled", True):
            return

        shadow_cron = str(eff.get("shadow_cron") or "").strip()
        if shadow_cron:
            try:
                self._scheduler.add_job(
                    self.run_shadow_reconcile_job,
                    CronTrigger.from_crontab(shadow_cron, timezone="UTC"),
                    id="shadow_reconcile",
                    replace_existing=True,
                )
            except Exception as exc:
                logger.warning("Invalid shadow_cron '%s': %s", shadow_cron, exc)

        campaign_cron = str(eff.get("campaign_cron") or "").strip()
        if campaign_cron:
            try:
                self._scheduler.add_job(
                    self.run_scheduled_campaign_job,
                    CronTrigger.from_crontab(campaign_cron, timezone="UTC"),
                    id="scheduled_campaign",
                    replace_existing=True,
                )
            except Exception as exc:
                logger.warning("Invalid campaign_cron '%s': %s", campaign_cron, exc)

    def status(self) -> dict[str, Any]:
        jobs = []
        for j in self._scheduler.get_jobs():
            next_run = getattr(j, "next_run_time", None)
            jobs.append(
                {
                    "id": j.id,
                    "next_run_time": next_run.isoformat() if next_run else None,
                    "trigger": str(j.trigger),
                }
            )
        return {"running": self._started, "jobs": jobs}

    def run_shadow_reconcile_job(self) -> dict[str, Any]:
        factory = get_session_factory()
        checked = 0
        transitions = 0
        with factory() as db:
            active = db.query(ShadowStrategy).filter(ShadowStrategy.state != "retired").all()
            for strat in active:
                prev = strat.state
                recompute_shadow_strategy(db, strat, notify=True, settings=self.settings)
                checked += 1
                if strat.state != prev:
                    transitions += 1
            db.add(
                EventLog(
                    category="scheduler",
                    level="info",
                    message=f"Shadow reconciliation completed ({checked} strategies checked, {transitions} state transitions).",
                    payload_json={"checked": checked, "transitions": transitions},
                )
            )
            db.commit()
        return {"checked": checked, "transitions": transitions}

    def run_scheduled_campaign_job(self) -> dict[str, Any]:
        factory = get_session_factory()
        today_tag = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M")
        cid = f"auto-{today_tag}"
        with factory() as db:
            eff = get_effective_runtime_config(db, self.settings)
            market = eff["market"]
            preset = str(market.get("default_preset") or "us_equities")
            symbols = tuple(market.get("default_symbols") or [])
            source = "crypto" if preset == "crypto_spot" else ("yahoo" if symbols else "demo")
            llm_cfg = build_llm_config(db, self.settings)

            cfg = CampaignConfig(
                campaign_id=cid,
                budget=CampaignBudget(
                    max_proposal_calls=1 if llm_cfg.is_configured() else 0,
                    max_ai_variants=3 if llm_cfg.is_configured() else 0,
                ),
                loader=LoaderConfig(source=source, symbols=symbols),
                evaluator=EvaluatorConfig(cost_preset=preset),
                development_only=True,
            )
            try:
                state = run_or_resume_campaign(cfg, storage_root=campaigns_root(self.settings), llm_config=llm_cfg)
            except Exception as exc:
                # Graceful fallback to demo dataset if external market API is unreachable
                logger.warning("Scheduled campaign source '%s' failed (%s); logging error.", source, exc)
                db.add(
                    EventLog(
                        category="scheduler",
                        level="error",
                        message=f"Scheduled campaign '{cid}' failed: {exc}",
                        payload_json={"campaign_id": cid, "source": source},
                    )
                )
                db.commit()
                return {"campaign_id": cid, "status": "error", "error": str(exc)}

            index_campaign_state(db, state)
            summary = state.get("summary") or {}
            msg = (
                f"Campaign '{cid}' finished discovery ({summary.get('dev_passed', 0)}/"
                f"{summary.get('total_candidates', 0)} passed discovery; awaiting single-shot validation)."
            )
            db.add(EventLog(category="scheduler", level="info", message=msg, payload_json=summary))
            db.commit()
            dispatch_notification("Scheduled Discovery Complete", msg, build_notification_config(db, self.settings))
            return {"campaign_id": cid, "status": state.get("status"), "summary": summary}


_scheduler_singleton: QuantSealScheduler | None = None


def get_scheduler() -> QuantSealScheduler:
    global _scheduler_singleton
    if _scheduler_singleton is None:
        _scheduler_singleton = QuantSealScheduler()
    return _scheduler_singleton
