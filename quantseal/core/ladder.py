"""Pure forward-only Strategy Ladder promotion and automatic demotion state machine.

State lifecycle:
    shadow -> paper -> live_candidate -> live
    Any active state can be automatically demoted back to `shadow` or `retired`.

Core invariant:
    Promotion decisions ONLY inspect forward out-of-sample observations recorded
    after strategy registration — never historical backtest numbers.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

from quantseal.core.evalue import DEFAULT_ALPHA, DEFAULT_SCALE, evalue_betting


class LadderState(StrEnum):
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE_CANDIDATE = "live_candidate"
    LIVE = "live"
    RETIRED = "retired"


@dataclass(frozen=True)
class LadderPolicy:
    """Governance thresholds for forward promotion and circuit-breaker demotion."""

    shadow_to_paper_min_obs: int = 30
    paper_to_live_candidate_min_obs: int = 60
    evalue_alpha_shadow: float = 0.05       # Threshold 20.0 for shadow -> paper
    evalue_alpha_live: float = DEFAULT_ALPHA  # Threshold 100.0 for paper -> live_candidate
    evalue_scale: float = DEFAULT_SCALE
    cost_hurdle_pct: float = 0.0
    max_promotion_mdd_pct: float = 15.0
    demotion_mdd_pct: float = 20.0
    demotion_consecutive_losses: int = 5
    demotion_cumulative_lag_pct: float = -10.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "shadow_to_paper_min_obs": self.shadow_to_paper_min_obs,
            "paper_to_live_candidate_min_obs": self.paper_to_live_candidate_min_obs,
            "evalue_alpha_shadow": self.evalue_alpha_shadow,
            "evalue_alpha_live": self.evalue_alpha_live,
            "evalue_scale": self.evalue_scale,
            "cost_hurdle_pct": self.cost_hurdle_pct,
            "max_promotion_mdd_pct": self.max_promotion_mdd_pct,
            "demotion_mdd_pct": self.demotion_mdd_pct,
            "demotion_consecutive_losses": self.demotion_consecutive_losses,
            "demotion_cumulative_lag_pct": self.demotion_cumulative_lag_pct,
        }


def _compute_forward_drawdown_pct(returns_pct: Sequence[float]) -> float:
    if not returns_pct:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns_pct:
        equity *= max(0.01, 1.0 + float(r) / 100.0)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def _trailing_consecutive_losses(returns_pct: Sequence[float]) -> int:
    streak = 0
    for r in reversed(returns_pct):
        if float(r) < 0.0:
            streak += 1
        else:
            break
    return streak


def evaluate_ladder_transition(
    current_state: str | LadderState,
    observations: Sequence[dict[str, Any]],
    *,
    policy: LadderPolicy = LadderPolicy(),
) -> dict[str, Any]:
    """Evaluate a strategy's forward OOS observations and return next state + audit trail.

    Each observation dict expects:
        - `strategy_return_pct`: realized forward return (%)
        - `benchmark_return_pct`: paired benchmark return (%) [optional, defaults 0.0]
    """
    state = current_state if isinstance(current_state, LadderState) else LadderState(str(current_state))

    strat_rets = [float(o.get("strategy_return_pct", 0.0)) for o in observations]
    bench_rets = [float(o.get("benchmark_return_pct", 0.0)) for o in observations]
    deltas = [s - b for s, b in zip(strat_rets, bench_rets, strict=True)]

    n = len(observations)
    cum_strat = float(np.sum(strat_rets)) if strat_rets else 0.0
    cum_delta = float(np.sum(deltas)) if deltas else 0.0
    mdd_pct = _compute_forward_drawdown_pct(strat_rets)
    consec_losses = _trailing_consecutive_losses(strat_rets)

    ev_shadow = evalue_betting(
        deltas,
        cost=policy.cost_hurdle_pct,
        alpha=policy.evalue_alpha_shadow,
        scale=policy.evalue_scale,
        include_series=True,
    )
    ev_live = evalue_betting(
        deltas,
        cost=policy.cost_hurdle_pct,
        alpha=policy.evalue_alpha_live,
        scale=policy.evalue_scale,
        include_series=False,
    )

    next_state = state
    action = "hold"
    reason = "Accumulating forward out-of-sample evidence."

    if state == LadderState.RETIRED:
        return {
            "previous_state": state.value,
            "next_state": state.value,
            "action": "retired",
            "reason": "Strategy is permanently retired.",
            "metrics": _build_metrics(n, cum_strat, cum_delta, mdd_pct, consec_losses, ev_shadow, ev_live),
        }

    # Circuit-breaker demotion checks always run first (fail-closed risk governance).
    demotion_triggers: list[str] = []
    if mdd_pct >= policy.demotion_mdd_pct:
        demotion_triggers.append(f"Forward MDD {mdd_pct:.2f}% >= {policy.demotion_mdd_pct:.2f}%")
    if consec_losses >= policy.demotion_consecutive_losses:
        demotion_triggers.append(
            f"Trailing consecutive losses {consec_losses} >= {policy.demotion_consecutive_losses}"
        )
    if cum_delta <= policy.demotion_cumulative_lag_pct:
        demotion_triggers.append(
            f"Cumulative benchmark lag {cum_delta:.2f}% <= {policy.demotion_cumulative_lag_pct:.2f}%"
        )

    if demotion_triggers:
        if state in (LadderState.PAPER, LadderState.LIVE_CANDIDATE, LadderState.LIVE):
            next_state = LadderState.SHADOW
            action = "demoted"
            reason = "Circuit breaker demoted strategy back to shadow: " + "; ".join(demotion_triggers)
        else:
            next_state = LadderState.RETIRED
            action = "retired"
            reason = "Shadow strategy breached risk ceiling and was retired: " + "; ".join(demotion_triggers)
    elif state == LadderState.SHADOW:
        if (
            n >= policy.shadow_to_paper_min_obs
            and ev_shadow["rejected"]
            and mdd_pct <= policy.max_promotion_mdd_pct
            and cum_delta > 0.0
        ):
            next_state = LadderState.PAPER
            action = "promoted"
            reason = (
                f"Promoted to paper: n={n}, peak E-value={ev_shadow['peak_evalue']:.2f} "
                f">= {ev_shadow['threshold']:.1f}, MDD={mdd_pct:.2f}%."
            )
    elif state == LadderState.PAPER:
        if (
            n >= policy.paper_to_live_candidate_min_obs
            and ev_live["rejected"]
            and mdd_pct <= policy.max_promotion_mdd_pct
            and cum_delta > 0.0
        ):
            next_state = LadderState.LIVE_CANDIDATE
            action = "promoted"
            reason = (
                f"Promoted to live_candidate: n={n}, peak E-value={ev_live['peak_evalue']:.2f} "
                f">= {ev_live['threshold']:.1f}, MDD={mdd_pct:.2f}%. Requires explicit human arming for live."
            )

    return {
        "previous_state": state.value,
        "next_state": next_state.value,
        "action": action,
        "reason": reason,
        "metrics": _build_metrics(n, cum_strat, cum_delta, mdd_pct, consec_losses, ev_shadow, ev_live),
    }


def _build_metrics(
    n: int,
    cum_strat: float,
    cum_delta: float,
    mdd_pct: float,
    consec_losses: int,
    ev_shadow: dict[str, Any],
    ev_live: dict[str, Any],
) -> dict[str, Any]:
    return {
        "observations": n,
        "cumulative_return_pct": round(cum_strat, 4),
        "cumulative_excess_pct": round(cum_delta, 4),
        "max_drawdown_pct": mdd_pct,
        "consecutive_losses": consec_losses,
        "evalue": ev_shadow["evalue"],
        "peak_evalue": ev_shadow["peak_evalue"],
        "shadow_threshold": ev_shadow["threshold"],
        "live_threshold": ev_live["threshold"],
        "evalue_series": ev_shadow.get("series", []),
    }
