"""Tests for immutable campaign hashing, single-shot validation seal, contamination, and LLM reservation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantseal.data.base import LoaderConfig
from quantseal.discovery.campaign import (
    CampaignBudget,
    CampaignConfig,
    CampaignImmutableMismatchError,
    run_or_resume_campaign,
)
from quantseal.discovery.evaluator import EvaluatorConfig
from quantseal.discovery.llm import LLMConfig


def test_single_shot_validation_seal_and_immutable_config(tmp_path: Path):
    cfg = CampaignConfig(
        campaign_id="seal-test-v1",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_total_variants=4, max_assets=12, max_days=180, warmup_days=50),
        loader=LoaderConfig(source="demo", max_assets=12, max_days=180, warmup_days=50),
        evaluator=EvaluatorConfig(cost_preset="us_equities", min_dev_trades=5, min_dev_signal_days=3, min_val_trades=3, min_val_signal_days=2),
        development_only=True,
    )
    state_dev = run_or_resume_campaign(cfg, storage_root=tmp_path)
    assert state_dev["status"] == "completed_development_only"
    assert state_dev["validation_evaluated_once"] is False
    assert all(e["validation"] is None for e in state_dev["experiments"])

    # Altering config on resume without unlocking MUST raise CampaignImmutableMismatchError
    tampered = CampaignConfig(
        campaign_id="seal-test-v1",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_total_variants=6, max_assets=12, max_days=180, warmup_days=50),
        loader=cfg.loader,
        evaluator=cfg.evaluator,
        development_only=True,
    )
    with pytest.raises(CampaignImmutableMismatchError):
        run_or_resume_campaign(tampered, storage_root=tmp_path)

    # Explicit single-shot unlock seals validation permanently
    state_sealed = run_or_resume_campaign(cfg, storage_root=tmp_path, unlock_validation=True)
    assert state_sealed["status"] == "completed_sealed"
    assert state_sealed["validation_evaluated_once"] is True
    claimed_ts = state_sealed["validation_claimed_at"]

    # Calling resume again returns sealed state untouched (no second validation peek!)
    state_again = run_or_resume_campaign(cfg, storage_root=tmp_path, unlock_validation=True)
    assert state_again["validation_claimed_at"] == claimed_ts


def test_prior_revision_contamination_tracking(tmp_path: Path):
    base_loader = LoaderConfig(source="demo", max_assets=12, max_days=180, warmup_days=50)
    ev = EvaluatorConfig(min_dev_trades=5, min_dev_signal_days=3, min_val_trades=3, min_val_signal_days=2)

    parent_cfg = CampaignConfig(
        campaign_id="parent-v1",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_assets=12, max_days=180, warmup_days=50),
        loader=base_loader,
        evaluator=ev,
        development_only=False,
    )
    parent = run_or_resume_campaign(parent_cfg, storage_root=tmp_path)
    assert parent["validation_evaluated_once"] is True
    assert parent["validation_holdout_contaminated"] is False

    # Child referencing parent with overlapping validation window MUST be marked contaminated
    child_cfg = CampaignConfig(
        campaign_id="child-v2",
        budget=CampaignBudget(max_proposal_calls=0, max_ai_variants=0, max_assets=12, max_days=180, warmup_days=50),
        loader=base_loader,
        evaluator=ev,
        prior_campaign_id="parent-v1",
        development_only=False,
    )
    child = run_or_resume_campaign(child_cfg, storage_root=tmp_path)
    assert child["validation_holdout_contaminated"] is True
    assert child["contamination_label"] == "contaminated_development_from_prior_revision"
    assert child["summary"]["qualified_for_shadow"] == 0


def test_pre_call_llm_reservation_and_bounded_ai_acceptance(tmp_path: Path):
    fake_ai_spec = [
        {
            "spec_id": "ai_tight_range_expansion",
            "title": "Tight Range Intraday Expansion",
            "source": "ai",
            "information_time": "t_close_execute_t_plus_1_open",
            "hypothesis": "Low prior range followed by strong close position indicates upward expansion.",
            "prediction": "Full beats baseline, ablation, and weak close reverse control.",
            "falsifier": "Paired daily delta <= 0 after costs.",
            "baseline": {"description": "Close >= 0.99 * MA15"},
            "ablation": {"remove_component": "setup", "description": "Remove range tightness filter"},
            "reverse_control": {"description": "Weak close position <= 0.3"},
            "context": {
                "type": "all",
                "clauses": [{"type": "compare", "left": {"feature": "close", "transform": "ratio_to_rolling_mean", "window": 15, "lag": 0}, "op": ">=", "right": 0.99}],
            },
            "setup": {
                "type": "all",
                "clauses": [{"type": "compare", "left": {"feature": "range_pct", "transform": "rolling_mean", "window": 4, "lag": 1}, "op": "<=", "right": 2.2}],
            },
            "trigger": {
                "type": "all",
                "clauses": [{"type": "compare", "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0}, "op": ">=", "right": 0.72}],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [{"type": "compare", "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0}, "op": "<=", "right": 0.28}],
            },
        },
        {
            # Unsafe spec attempting Python code injection -> MUST be rejected & logged
            "spec_id": "ai_malicious_exec",
            "src": "import os; os.system('echo pwned')",
        },
    ]

    def fake_caller(_prompt: str, _cfg: LLMConfig):
        return {"text": json.dumps(fake_ai_spec), "usage": {"total_tokens": 500}}

    cfg = CampaignConfig(
        campaign_id="ai-proposal-v1",
        budget=CampaignBudget(max_proposal_calls=1, max_ai_variants=2, max_total_variants=6, max_assets=12, max_days=180, warmup_days=50),
        loader=LoaderConfig(source="demo", max_assets=12, max_days=180, warmup_days=50),
        evaluator=EvaluatorConfig(min_dev_trades=5, min_dev_signal_days=3),
        development_only=True,
    )
    llm_cfg = LLMConfig(provider="openai", api_key="sk-test-secret-redacted-1234567890", model="gpt-4o-mini")
    state = run_or_resume_campaign(cfg, storage_root=tmp_path, llm_config=llm_cfg, llm_caller=fake_caller)

    assert len(state["proposal_reservations"]) == 1
    assert state["proposal_audits"][0]["accepted_count"] == 1
    assert any(r.get("error_code") == "unsafe_spec_key" for r in state["proposal_audits"][0]["rejected"])
    assert "sk-test-secret" not in json.dumps(state)
    assert any(e["spec_id"] == "ai_tight_range_expansion" for e in state["experiments"])
