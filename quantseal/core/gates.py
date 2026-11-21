"""Fail-closed statistical governance gates and transaction cost stress testing.

Provides:
- Date-clustered Bootstrap 95% CI (prevents treating same-day cross-sectional
  signals as independent observations; fails closed when clusters < 5).
- Cost stress testing (1.0x, 1.5x, 2.0x execution friction multipliers).
- Profit concentration audit (single-asset and single-sector share caps).
- Unified standalone trade-record auditor usable on any external backtest export.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from quantseal.core.evalue import DEFAULT_ALPHA, DEFAULT_SCALE, evalue_betting


def cluster_bootstrap_ci(
    trades: Sequence[dict[str, Any]],
    *,
    cluster_key: str = "entry_date",
    n_bootstraps: int = 1500,
    ci: float = 0.95,
    random_seed: int = 42,
    min_clusters: int = 5,
) -> dict[str, Any]:
    """Estimate mean net return confidence interval by resampling date clusters."""
    if not trades:
        return {
            "mean": 0.0,
            "ci_lower": -99.0,
            "ci_upper": 0.0,
            "n_clusters": 0,
            "n_trades": 0,
            "passed": False,
            "failure_code": "empty_trades",
        }

    clusters: dict[object, list[float]] = {}
    for t in trades:
        key = t.get(cluster_key) or t.get("trade_date") or t.get("entry_date") or "default"
        clusters.setdefault(key, []).append(float(t.get("net", 0.0)))

    cluster_keys = list(clusters.keys())
    n_clusters = len(cluster_keys)
    all_rets = [float(t.get("net", 0.0)) for t in trades]
    obs_mean = float(np.mean(all_rets))

    if n_clusters < min_clusters:
        # Fail closed: never collapse CI bounds to the sample mean when clusters are too few.
        return {
            "mean": round(obs_mean, 4),
            "ci_lower": -99.0,
            "ci_upper": round(obs_mean, 4),
            "n_clusters": n_clusters,
            "n_trades": len(trades),
            "passed": False,
            "failure_code": "insufficient_clusters",
            "warning": (
                f"Only {n_clusters} trading-date clusters (< {min_clusters}); "
                "fail-closed against false independence."
            ),
        }

    rng = np.random.default_rng(random_seed)
    cluster_arrays = [np.asarray(clusters[k], dtype=np.float64) for k in cluster_keys]
    boot_means = np.empty(n_bootstraps, dtype=np.float64)

    for i in range(n_bootstraps):
        sampled_idx = rng.integers(0, n_clusters, size=n_clusters)
        total = 0.0
        count = 0
        for idx in sampled_idx:
            arr = cluster_arrays[idx]
            total += float(arr.sum())
            count += arr.size
        boot_means[i] = total / count if count > 0 else 0.0

    lower_pct = ((1.0 - ci) / 2.0) * 100.0
    upper_pct = (1.0 - (1.0 - ci) / 2.0) * 100.0
    ci_lower = float(np.percentile(boot_means, lower_pct))
    ci_upper = float(np.percentile(boot_means, upper_pct))

    return {
        "mean": round(obs_mean, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "ci_level": float(ci),
        "n_clusters": n_clusters,
        "n_trades": len(trades),
        "passed": ci_lower > 0.0,
    }


def cost_stress_test(
    trades: Sequence[dict[str, Any]],
    *,
    multipliers: Sequence[float] = (1.0, 1.5, 2.0),
) -> dict[str, dict[str, Any]]:
    """Evaluate average net return and profit factor under amplified friction."""
    if not trades:
        return {}

    results: dict[str, dict[str, Any]] = {}
    for mult in multipliers:
        stressed_rets: list[float] = []
        wins = 0.0
        losses = 0.0
        for t in trades:
            net = float(t.get("net", 0.0))
            if "gross" in t and t["gross"] is not None:
                gross = float(t["gross"])
                cost = max(0.0, gross - net)
            else:
                cost = max(0.0, float(t.get("cost", 0.2)))
                gross = net + cost
            stressed_net = gross - cost * float(mult)
            stressed_rets.append(stressed_net)
            if stressed_net > 0:
                wins += stressed_net
            else:
                losses += abs(stressed_net)

        avg_net = float(np.mean(stressed_rets))
        pf = (wins / losses) if losses > 0 else (99.0 if wins > 0 else 0.0)
        results[f"{mult:g}x"] = {
            "multiplier": float(mult),
            "avg_net_return": round(avg_net, 4),
            "profit_factor": round(pf, 3),
            "passed": avg_net > 0.0,
        }
    return results


def concentration_audit(
    trades: Sequence[dict[str, Any]],
    *,
    max_single_asset_pct: float = 20.0,
    max_single_sector_pct: float = 45.0,
    require_sector_metadata: bool = False,
) -> dict[str, Any]:
    """Audit whether strategy profits are dangerously concentrated in one symbol or sector."""
    if not trades:
        return {
            "passed": False,
            "reason": "empty_trades",
            "max_asset_pct": 0.0,
            "max_sector_pct": 0.0,
            "top_asset": None,
            "top_sector": None,
        }

    pos_trades = [t for t in trades if float(t.get("net", 0.0)) > 0]
    total_pos = sum(float(t.get("net", 0.0)) for t in pos_trades)
    if total_pos <= 0:
        return {
            "passed": False,
            "reason": "no_positive_profit",
            "max_asset_pct": 0.0,
            "max_sector_pct": 0.0,
            "top_asset": None,
            "top_sector": None,
        }

    asset_profits: dict[str, float] = {}
    sector_profits: dict[str, float] = {}
    missing_sector_count = 0

    for t in pos_trades:
        ret = float(t.get("net", 0.0))
        symbol = str(t.get("symbol") or t.get("stock_id") or "unknown").strip() or "unknown"
        raw_sector = t.get("sector") or t.get("industry")
        sector = str(raw_sector).strip() if raw_sector is not None else ""
        if not sector or sector.lower() == "unknown":
            missing_sector_count += 1
            sector = "unclassified"
        asset_profits[symbol] = asset_profits.get(symbol, 0.0) + ret
        sector_profits[sector] = sector_profits.get(sector, 0.0) + ret

    if require_sector_metadata and missing_sector_count > 0:
        coverage = round(((len(pos_trades) - missing_sector_count) / len(pos_trades)) * 100.0, 2)
        return {
            "passed": False,
            "reason": "missing_sector_metadata",
            "missing_sector_count": missing_sector_count,
            "sector_coverage_pct": coverage,
            "max_asset_pct": round((max(asset_profits.values()) / total_pos) * 100.0, 2),
            "max_sector_pct": 100.0,
            "top_asset": max(asset_profits, key=lambda k: asset_profits[k]),
            "top_sector": None,
        }

    top_asset = max(asset_profits, key=lambda k: asset_profits[k])
    top_asset_pct = (asset_profits[top_asset] / total_pos) * 100.0
    top_sector = max(sector_profits, key=lambda k: sector_profits[k])
    top_sector_pct = (sector_profits[top_sector] / total_pos) * 100.0

    asset_ok = top_asset_pct <= max_single_asset_pct
    sector_ok = True if (not require_sector_metadata and missing_sector_count == len(pos_trades)) else (
        top_sector_pct <= max_single_sector_pct
    )
    passed = asset_ok and sector_ok

    return {
        "passed": passed,
        "max_asset_pct": round(top_asset_pct, 2),
        "max_sector_pct": round(top_sector_pct, 2),
        "top_asset": top_asset,
        "top_sector": top_sector if missing_sector_count < len(pos_trades) else None,
        "asset_limit_pct": float(max_single_asset_pct),
        "sector_limit_pct": float(max_single_sector_pct),
    }


def evaluate_promotion_gate(
    validation_trades: Sequence[dict[str, Any]],
    *,
    min_trades: int = 30,
    min_avg_net_pct: float = 0.15,
    min_profit_factor: float = 1.15,
    required_cost_stress: str = "1.5x",
    max_single_asset_pct: float = 20.0,
    max_single_sector_pct: float = 45.0,
    require_sector_metadata: bool = False,
    evalue_alpha: float = DEFAULT_ALPHA,
    evalue_scale: float = DEFAULT_SCALE,
) -> dict[str, Any]:
    """Fail-closed statistical promotion gate across sample size, CI, cost stress, and concentration."""
    n_trades = len(validation_trades)
    rejections: list[str] = []

    if n_trades < min_trades:
        rejections.append(f"Sample size {n_trades} < minimum required {min_trades}")

    rets = [float(t.get("net", 0.0)) for t in validation_trades]
    avg_net = float(np.mean(rets)) if rets else 0.0
    wins = sum(r for r in rets if r > 0)
    losses = sum(abs(r) for r in rets if r < 0)
    pf = (wins / losses) if losses > 0 else (99.0 if wins > 0 else 0.0)
    win_rate = (sum(1 for r in rets if r > 0) / n_trades * 100.0) if n_trades > 0 else 0.0

    if avg_net < min_avg_net_pct:
        rejections.append(f"Average net return {avg_net:.3f}% < {min_avg_net_pct:.3f}%")
    if pf < min_profit_factor:
        rejections.append(f"Profit factor {pf:.2f} < {min_profit_factor:.2f}")

    boot = cluster_bootstrap_ci(validation_trades)
    if not boot.get("passed"):
        rejections.append(
            f"Cluster Bootstrap 95% CI lower bound {boot.get('ci_lower')} <= 0"
        )

    stress = cost_stress_test(validation_trades, multipliers=(1.0, 1.5, 2.0))
    stress_target = stress.get(required_cost_stress, {})
    if not stress_target.get("passed", False):
        rejections.append(
            f"Cost stress ({required_cost_stress}) failed: avg net = {stress_target.get('avg_net_return')}"
        )

    conc = concentration_audit(
        validation_trades,
        max_single_asset_pct=max_single_asset_pct,
        max_single_sector_pct=max_single_sector_pct,
        require_sector_metadata=require_sector_metadata,
    )
    if not conc.get("passed"):
        rejections.append(
            f"Concentration limit breached (top asset {conc.get('max_asset_pct')}%, "
            f"top sector {conc.get('max_sector_pct')}%)"
        )

    ev = evalue_betting(rets, cost=0.0, alpha=evalue_alpha, scale=evalue_scale, include_series=True)

    passed = len(rejections) == 0
    return {
        "passed": passed,
        "verdict": "PASS" if passed else "REJECTED",
        "rejection_reasons": rejections,
        "summary": {
            "n_trades": n_trades,
            "avg_net_return_pct": round(avg_net, 4),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(pf, 3),
        },
        "bootstrap_ci": boot,
        "cost_stress": stress,
        "concentration": conc,
        "evalue": ev,
    }


def audit_trade_records(
    trades: Sequence[dict[str, Any]],
    *,
    min_trades: int = 20,
    min_avg_net_pct: float = 0.10,
    min_profit_factor: float = 1.10,
    max_single_asset_pct: float = 25.0,
    evalue_alpha: float = DEFAULT_ALPHA,
    evalue_scale: float = DEFAULT_SCALE,
) -> dict[str, Any]:
    """Convenience wrapper for standalone trade-export auditing via API or CLI."""
    return evaluate_promotion_gate(
        trades,
        min_trades=min_trades,
        min_avg_net_pct=min_avg_net_pct,
        min_profit_factor=min_profit_factor,
        max_single_asset_pct=max_single_asset_pct,
        require_sector_metadata=False,
        evalue_alpha=evalue_alpha,
        evalue_scale=evalue_scale,
    )
