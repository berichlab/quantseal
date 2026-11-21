"""Tests for zero-exec bounded spec grammar, anti-leakage checks, and causal evaluator."""
from __future__ import annotations

import copy
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quantseal.core.costs import get_cost_model
from quantseal.data.synthetic import load_demo_dataset
from quantseal.discovery.evaluator import EvaluatorConfig, evaluate_spec_development, simulate_single_trade
from quantseal.discovery.spec import (
    SpecValidationError,
    build_default_seed_and_control_specs,
    evaluate_condition_node,
    spec_fingerprint,
    validate_spec,
)


def _sample_spec() -> dict:
    return copy.deepcopy(build_default_seed_and_control_specs()[0])


def test_rejects_forbidden_code_keys():
    s = _sample_spec()
    s["src"] = "def detect(df): return True"
    with pytest.raises(SpecValidationError) as exc:
        validate_spec(s)
    assert exc.value.error_code == "unsafe_spec_key"


def test_rejects_negative_lag_future_lookahead():
    s = _sample_spec()
    s["trigger"]["clauses"][0]["left"]["lag"] = -1
    with pytest.raises(SpecValidationError) as exc:
        validate_spec(s)
    assert exc.value.error_code == "future_lookahead"


def test_rejects_missing_rolling_quantile_q():
    s = _sample_spec()
    s["setup"]["clauses"][0]["left"] = {
        "feature": "close",
        "transform": "rolling_quantile",
        "window": 10,
        "lag": 0,
    }
    with pytest.raises(SpecValidationError) as exc:
        validate_spec(s)
    assert exc.value.error_code == "missing_quantile_q"


def test_rejects_static_contradiction():
    s = _sample_spec()
    s["trigger"]["clauses"] = [
        {"type": "compare", "left": {"feature": "ret_1d", "transform": "raw", "lag": 0}, "op": ">", "right": 3.0},
        {"type": "compare", "left": {"feature": "ret_1d", "transform": "raw", "lag": 0}, "op": "<=", "right": 1.0},
    ]
    with pytest.raises(SpecValidationError) as exc:
        validate_spec(s)
    assert exc.value.error_code == "static_contradiction"


def test_fingerprint_invariant_to_renaming_and_prose():
    s1 = _sample_spec()
    s2 = _sample_spec()
    s2["spec_id"] = "ai_completely_renamed_spec"
    s2["title"] = "Completely Different Marketing Title"
    s2["hypothesis"] = "Rewritten prose claiming something totally different."
    assert spec_fingerprint(s1) == spec_fingerprint(s2)


def test_nan_comparison_strictly_false():
    df = pd.DataFrame({"ret_1d": [1.0, np.nan, -2.0, np.inf]})
    node = {
        "type": "compare",
        "left": {"feature": "ret_1d", "transform": "raw", "lag": 0},
        "op": "<=",
        "right": 0.0,
    }
    res = evaluate_condition_node(df, node).tolist()
    assert res == [False, False, True, False]


def test_no_same_bar_high_lookahead_for_trailing_stop():
    """On entry day, a huge intraday spike + close cannot retroactively trigger same-bar trailing stop."""
    dates = [dt.date(2026, 1, 2), dt.date(2026, 1, 5), dt.date(2026, 1, 6)]
    df = pd.DataFrame(
        {
            "trade_date": dates,
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 112.0, 101.0],  # Day 1 spikes +12% then pulls back; trailing stop uses PRIOR bar high only
            "low": [99.0, 97.0, 99.0],      # 97 is > 95 (-5% SL), and < 112*0.94 (105.28), MUST NOT stop out on Day 1!
            "close": [100.0, 100.0, 100.0],
        }
    )
    policy = {
        "stop_loss_pct": -5.0,
        "take_profit_pct": 20.0,
        "trailing_stop_pct": -6.0,
        "max_hold_days": 2,
    }
    sim = simulate_single_trade(
        df,
        signal_date=dates[0],
        runway_dates=[dates[1], dates[2]],
        exit_policy=policy,
        cost_model=get_cost_model("us_equities"),
    )
    assert sim is not None
    # Day 1 did NOT trigger trailing stop from Day 1's own high; Day 2 opens at 100 <= 112*0.94=105.28 -> open gap trail
    assert sim["exit_date"] == dates[2].isoformat()
    assert sim["exit_reason"] == "open_gap_trailing_stop"


def test_causal_missing_bar_never_backdates_exit():
    dates = [dt.date(2026, 1, 2), dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)]
    # Missing bar on 2026-01-06; resumes on 2026-01-07 with lower open (92.0) -> MUST exit at 92.0 open, not backdate!
    df = pd.DataFrame(
        {
            "trade_date": [dates[0], dates[1], dates[3]],
            "open": [100.0, 100.0, 92.0],
            "high": [101.0, 102.0, 95.0],
            "low": [99.0, 99.0, 91.0],
            "close": [100.0, 101.0, 94.0],
        }
    )
    policy = {"stop_loss_pct": -10.0, "take_profit_pct": 15.0, "trailing_stop_pct": -10.0, "max_hold_days": 3}
    sim = simulate_single_trade(
        df,
        signal_date=dates[0],
        runway_dates=[dates[1], dates[2], dates[3]],
        exit_policy=policy,
        cost_model=get_cost_model("us_equities"),
    )
    assert sim is not None
    assert sim["exit_reason"] == "missing_data_next_open"
    assert sim["exit_date"] == dates[3].isoformat()
    assert sim["exit_price"] == 92.0


def test_four_arm_development_evaluation_runs_cleanly():
    ds = load_demo_dataset()
    spec = _sample_spec()
    res = evaluate_spec_development(ds, spec, EvaluatorConfig(min_dev_trades=5, min_dev_signal_days=3))
    assert res["partition"] == "discovery"
    assert set(res["arms"].keys()) == {"full", "baseline", "ablation", "reverse_control"}
    assert set(res["pairwise_comparisons"].keys()) == {"baseline", "ablation", "reverse_control"}
