"""Core anti-overfitting quantitative primitives."""
from __future__ import annotations

from quantseal.core.costs import (
    MARKET_COST_PRESETS,
    CostBreakdown,
    CostModel,
    apply_cost,
    cost_breakdown,
    get_cost_model,
    round_trip_cost_pct,
)
from quantseal.core.evalue import (
    DEFAULT_ALPHA,
    DEFAULT_SCALE,
    evalue_betting,
    merge_evalues,
    rejects_h0,
)
from quantseal.core.gates import (
    audit_trade_records,
    cluster_bootstrap_ci,
    concentration_audit,
    cost_stress_test,
    evaluate_promotion_gate,
)
from quantseal.core.ladder import (
    LadderPolicy,
    LadderState,
    evaluate_ladder_transition,
)
from quantseal.core.split import (
    PROTOCOL,
    calendar_manifest,
    manifest_boundaries,
    partition,
    select_frames,
    temporal_boundaries,
    window_fits,
)

__all__ = [
    "CostBreakdown",
    "CostModel",
    "DEFAULT_ALPHA",
    "DEFAULT_SCALE",
    "LadderPolicy",
    "LadderState",
    "MARKET_COST_PRESETS",
    "PROTOCOL",
    "apply_cost",
    "audit_trade_records",
    "calendar_manifest",
    "cluster_bootstrap_ci",
    "concentration_audit",
    "cost_breakdown",
    "cost_stress_test",
    "evaluate_ladder_transition",
    "evaluate_promotion_gate",
    "evalue_betting",
    "get_cost_model",
    "manifest_boundaries",
    "merge_evalues",
    "partition",
    "rejects_h0",
    "round_trip_cost_pct",
    "select_frames",
    "temporal_boundaries",
    "window_fits",
]
