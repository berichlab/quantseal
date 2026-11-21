"""Tests for statistical governance gates, cost stress, concentration audit, and ladder state machine."""
from __future__ import annotations

from quantseal.core.costs import apply_cost, cost_breakdown
from quantseal.core.gates import (
    cluster_bootstrap_ci,
    concentration_audit,
    cost_stress_test,
    evaluate_promotion_gate,
)
from quantseal.core.ladder import LadderPolicy, LadderState, evaluate_ladder_transition


def test_cost_model_tiered_slippage():
    low_price = cost_breakdown(model="us_equities", price=3.0)
    high_price = cost_breakdown(model="us_equities", price=100.0)
    assert low_price.slippage_multiplier == 2.0
    assert high_price.slippage_multiplier == 1.0
    assert low_price.total_pct > high_price.total_pct
    assert apply_cost(2.0, model="us_equities", price=100.0) < 2.0


def test_cluster_bootstrap_fails_closed_under_five_clusters():
    # 20 trades all on only 3 trading dates -> MUST fail closed (never fake independence)
    trades = [
        {"entry_date": f"2026-01-0{(i % 3) + 1}", "net": 3.5}
        for i in range(20)
    ]
    res = cluster_bootstrap_ci(trades)
    assert res["passed"] is False
    assert res["failure_code"] == "insufficient_clusters"
    assert res["ci_lower"] == -99.0


def test_cost_stress_and_concentration_audit():
    trades = []
    symbols = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLI"]
    sectors = ["Broad", "Tech", "Small", "Tech", "Fin", "Energy", "Health", "Ind"]
    for i in range(40):
        idx = i % len(symbols)
        trades.append(
            {
                "entry_date": f"2026-02-{(i % 20) + 1:02d}",
                "symbol": symbols[idx],
                "sector": sectors[idx],
                "gross": 1.4,
                "net": 1.1,
            }
        )
    stress = cost_stress_test(trades)
    assert stress["1x"]["passed"] is True
    assert stress["1.5x"]["passed"] is True
    assert stress["2x"]["passed"] is True

    conc = concentration_audit(trades, max_single_asset_pct=20.0, max_single_sector_pct=45.0)
    assert conc["passed"] is True

    gate = evaluate_promotion_gate(trades, min_trades=30)
    assert gate["passed"] is True
    assert gate["verdict"] == "PASS"


def test_concentration_rejects_single_winner_mirage():
    trades = [{"entry_date": f"2026-03-{i+1:02d}", "symbol": "NVDA", "sector": "Tech", "gross": 10.0, "net": 9.8} for i in range(10)]
    trades += [{"entry_date": f"2026-04-{i+1:02d}", "symbol": f"S{i}", "sector": "Other", "gross": 0.4, "net": 0.2} for i in range(10)]
    conc = concentration_audit(trades, max_single_asset_pct=20.0)
    assert conc["passed"] is False
    assert conc["top_asset"] == "NVDA"


def test_ladder_promotion_and_circuit_breaker_demotion():
    policy = LadderPolicy(shadow_to_paper_min_obs=30, paper_to_live_candidate_min_obs=60)
    strong_obs = [{"strategy_return_pct": 3.0, "benchmark_return_pct": 0.0} for _ in range(40)]
    res = evaluate_ladder_transition(LadderState.SHADOW, strong_obs, policy=policy)
    assert res["next_state"] == LadderState.PAPER.value
    assert res["action"] == "promoted"

    # Paper strategy hits 5 consecutive losses -> auto-demoted back to shadow
    crash_obs = strong_obs + [{"strategy_return_pct": -1.5, "benchmark_return_pct": 0.1} for _ in range(5)]
    dem = evaluate_ladder_transition(LadderState.PAPER, crash_obs, policy=policy)
    assert dem["next_state"] == LadderState.SHADOW.value
    assert dem["action"] == "demoted"

    # Shadow strategy breaches MDD >= 20% -> auto-retired
    blowup = [{"strategy_return_pct": -6.0, "benchmark_return_pct": 0.0} for _ in range(5)]
    ret = evaluate_ladder_transition(LadderState.SHADOW, blowup, policy=policy)
    assert ret["next_state"] == LadderState.RETIRED.value
    assert ret["action"] == "retired"
