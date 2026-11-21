"""Deterministic next-session-open evaluator with fixed-slot ledger and 4-arm falsification.

Anti-leakage & execution realism guarantees:
1. Causal entry: signals formed at close t execute strictly at next market session
   open (t+1). If the asset has no valid bar on t+1, the entry is skipped (never
   delayed to t+k).
2. Zero same-bar high lookahead: each bar checks exits in conservative order:
      open_gap_stop_loss -> open_gap_prior_bar_trailing_stop -> open_gap_take_profit
      -> intraday_stop_loss -> intraday_prior_bar_trailing_stop -> intraday_take_profit
      -> close_max_hold -> update_highest_price_after_exit_checks
3. Outcome-independent boundary exclusion: signals whose `max_hold_days` runway
   crosses `part_end` are excluded BEFORE entry (eliminates end-of-window winner bias).
4. Causal missing-data handling: missing bars during a hold lock capital/slots and
   carry the last valid mark until the next tradable open (never backdated exit).
5. Chronological fixed-slot capital ledger: enforces `max_daily_active_slots` with
   deterministic tie-breaking `(-signal_day_turnover, symbol ASC)` and full cost model.
6. 4-Arm Paired Comparison with Moving Block Bootstrap CI + sparse-arm inconclusive guard.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quantseal.core.costs import CostModel, cost_breakdown, get_cost_model
from quantseal.core.gates import cluster_bootstrap_ci, concentration_audit, cost_stress_test
from quantseal.data.base import LoadedDiscoveryDataset
from quantseal.discovery.spec import SHARED_DEFAULT_EXIT_POLICY, evaluate_spec_arms

ARMS: tuple[str, ...] = ("full", "baseline", "ablation", "reverse_control")
INITIAL_CAPITAL = 100_000.0


@dataclass(frozen=True)
class EvaluatorConfig:
    cost_preset: str = "us_equities"
    min_dev_trades: int = 10
    min_dev_signal_days: int = 5
    min_val_trades: int = 5
    min_val_signal_days: int = 3
    max_daily_active_slots: int = 5
    bootstrap_block_days: int = 5
    bootstrap_iterations: int = 400
    exit_policy: dict[str, Any] | None = None

    def resolved_exit_policy(self) -> dict[str, Any]:
        base = dict(SHARED_DEFAULT_EXIT_POLICY)
        if self.exit_policy:
            base.update(self.exit_policy)
        return base

    def resolved_cost_model(self) -> CostModel:
        return get_cost_model(self.cost_preset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_preset": self.cost_preset,
            "min_dev_trades": int(self.min_dev_trades),
            "min_dev_signal_days": int(self.min_dev_signal_days),
            "min_val_trades": int(self.min_val_trades),
            "min_val_signal_days": int(self.min_val_signal_days),
            "max_daily_active_slots": int(self.max_daily_active_slots),
            "bootstrap_block_days": int(self.bootstrap_block_days),
            "bootstrap_iterations": int(self.bootstrap_iterations),
            "exit_policy": self.resolved_exit_policy(),
        }


def simulate_single_trade(
    df: pd.DataFrame,
    signal_date: dt.date,
    *,
    runway_dates: list[dt.date],
    exit_policy: dict[str, Any],
    cost_model: CostModel,
) -> dict[str, Any] | None:
    """Simulate one trade entering strictly on runway_dates[0] (t+1 open)."""
    if not runway_dates:
        return None
    entry_date = runway_dates[0]
    row_by_date: dict[dt.date, tuple[float, float, float, float]] = {}
    for row in df[["trade_date", "open", "high", "low", "close"]].itertuples(index=False):
        d, o, h, lo, c = row
        if all(x is not None and np.isfinite(x) and x > 0 for x in (o, h, lo, c)):
            row_by_date[d] = (float(o), float(h), float(lo), float(c))

    if entry_date not in row_by_date:
        # Strict causal rule: no bar on t+1 means skip entry (never peek ahead to t+2).
        return None

    entry_open = row_by_date[entry_date][0]
    sl_pct = float(exit_policy["stop_loss_pct"]) / 100.0
    tp_pct = float(exit_policy["take_profit_pct"]) / 100.0
    trail_pct = float(exit_policy["trailing_stop_pct"]) / 100.0
    max_hold = int(exit_policy["max_hold_days"])

    sl_price = entry_open * (1.0 + sl_pct)
    tp_price = entry_open * (1.0 + tp_pct)

    prior_highest = entry_open
    last_valid_close = entry_open
    saw_missing_bar = False
    daily_marks: dict[dt.date, float] = {}
    exit_date: dt.date | None = None
    exit_price: float | None = None
    exit_reason = "max_hold"
    mfe_pct = 0.0
    mae_pct = 0.0

    for hold_step, cur_date in enumerate(runway_dates[:max_hold]):
        bar = row_by_date.get(cur_date)
        if bar is None:
            saw_missing_bar = True
            daily_marks[cur_date] = last_valid_close
            continue

        o, h, lo, c = bar
        if saw_missing_bar:
            # Causal missing-data rule: resume & exit at first tradable open (never backdate)
            exit_date = cur_date
            exit_price = o
            exit_reason = "missing_data_next_open"
            daily_marks[cur_date] = o
            break

        trail_trigger = prior_highest * (1.0 + trail_pct)

        # 1. Open-gap exit checks (conservative order: stop -> prior-bar trail -> take profit)
        if hold_step > 0:
            if o <= sl_price:
                exit_date, exit_price, exit_reason = cur_date, o, "open_gap_stop_loss"
                daily_marks[cur_date] = o
                break
            if o <= trail_trigger:
                exit_date, exit_price, exit_reason = cur_date, o, "open_gap_trailing_stop"
                daily_marks[cur_date] = o
                break
            if o >= tp_price:
                exit_date, exit_price, exit_reason = cur_date, o, "open_gap_take_profit"
                daily_marks[cur_date] = o
                break

        # 2. Intraday exit checks (strictly using prior_highest from bars < hold_step)
        if lo <= sl_price:
            exit_date, exit_price, exit_reason = cur_date, sl_price, "stop_loss"
            daily_marks[cur_date] = sl_price
            break
        if hold_step > 0 and lo <= trail_trigger:
            exit_date, exit_price, exit_reason = cur_date, trail_trigger, "trailing_stop"
            daily_marks[cur_date] = trail_trigger
            break
        if h >= tp_price:
            exit_date, exit_price, exit_reason = cur_date, tp_price, "take_profit"
            daily_marks[cur_date] = tp_price
            break

        # Track MFE / MAE
        mfe_pct = max(mfe_pct, ((h / entry_open) - 1.0) * 100.0)
        mae_pct = min(mae_pct, ((lo / entry_open) - 1.0) * 100.0)

        # 3. Max-hold close exit
        if hold_step == max_hold - 1:
            exit_date, exit_price, exit_reason = cur_date, c, "max_hold"
            daily_marks[cur_date] = c
            break

        # 4. Update highest price strictly AFTER all exit checks on this bar
        if h > prior_highest:
            prior_highest = h
        last_valid_close = c
        daily_marks[cur_date] = c

    if exit_date is None or exit_price is None:
        return {
            "signal_date": signal_date.isoformat(),
            "entry_date": entry_date.isoformat(),
            "exit_date": None,
            "entry_price": round(entry_open, 4),
            "exit_price": None,
            "exit_reason": "unresolved_missing_data",
            "unresolved_missing_data": True,
            "gross": None,
            "net": None,
            "cost": None,
            "daily_marks": daily_marks,
        }

    gross_pct = ((exit_price / entry_open) - 1.0) * 100.0
    cb = cost_breakdown(model=cost_model, price=entry_open)
    net_pct = round(gross_pct - cb.total_pct, 4)
    return {
        "signal_date": signal_date.isoformat(),
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_date.isoformat(),
        "entry_price": round(entry_open, 4),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "unresolved_missing_data": False,
        "gross": round(gross_pct, 4),
        "net": net_pct,
        "cost": cb.total_pct,
        "mfe_pct": round(mfe_pct, 4),
        "mae_pct": round(mae_pct, 4),
        "daily_marks": daily_marks,
    }


def _evaluate_arm_on_partition(
    dataset: LoadedDiscoveryDataset,
    signals_by_symbol: dict[str, pd.Series],
    *,
    part_start: dt.date,
    part_end: dt.date,
    config: EvaluatorConfig,
    exit_policy: dict[str, Any],
) -> dict[str, Any]:
    """Chronological fixed-slot capital ledger on [part_start, part_end]."""
    part_dates = [d for d in dataset.calendar_dates if part_start <= d <= part_end]
    date_to_pos = {d: i for i, d in enumerate(part_dates)}
    max_hold = int(exit_policy["max_hold_days"])
    cost_model = config.resolved_cost_model()

    # Collect all candidate signals with deterministic tie-breaker
    signals_by_date: dict[dt.date, list[tuple[float, str]]] = {}
    boundary_excluded = 0
    for sym, sig_series in sorted(signals_by_symbol.items()):
        df = dataset.frames[sym]
        sig_mask = sig_series.to_numpy(dtype=bool)
        dates_arr = df["trade_date"].tolist()
        turnovers = df["turnover"].to_numpy(dtype=np.float64)
        for idx, is_sig in enumerate(sig_mask):
            if not is_sig:
                continue
            s_date = dates_arr[idx]
            if s_date not in date_to_pos:
                continue
            pos = date_to_pos[s_date]
            # Outcome-independent boundary check: full max_hold runway must fit inside partition
            if pos + max_hold >= len(part_dates):
                boundary_excluded += 1
                continue
            tov = float(turnovers[idx]) if np.isfinite(turnovers[idx]) else 0.0
            signals_by_date.setdefault(s_date, []).append((-tov, sym))

    # Chronological fixed-slot portfolio ledger
    max_slots = int(config.max_daily_active_slots)
    cash = INITIAL_CAPITAL
    active_positions: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    daily_equity: dict[str, float] = {}
    daily_returns: dict[str, float] = {}
    capacity_skipped = 0
    unresolved_count = 0
    prev_equity = INITIAL_CAPITAL

    for day_idx, cur_date in enumerate(part_dates):
        # 1. Close positions exiting on or before cur_date
        still_open: list[dict[str, Any]] = []
        for pos in active_positions:
            if pos["exit_date_obj"] is not None and pos["exit_date_obj"] <= cur_date:
                cash += pos["notional"] * (1.0 + pos["net"] / 100.0)
                closed_trades.append(pos["trade"])
            else:
                still_open.append(pos)
        active_positions = still_open

        # 2. Admit signals triggered on yesterday's session (cur_date == t+1)
        if day_idx > 0:
            prev_date = part_dates[day_idx - 1]
            candidates = sorted(signals_by_date.get(prev_date, []))
            held_symbols = {p["symbol"] for p in active_positions}
            for _neg_tov, sym in candidates:
                if sym in held_symbols:
                    continue
                if len(active_positions) >= max_slots:
                    capacity_skipped += 1
                    continue
                runway = part_dates[day_idx : day_idx + max_hold]
                sim = simulate_single_trade(
                    dataset.frames[sym],
                    prev_date,
                    runway_dates=runway,
                    exit_policy=exit_policy,
                    cost_model=cost_model,
                )
                if sim is None:
                    continue
                if sim["unresolved_missing_data"]:
                    unresolved_count += 1
                    continue
                free_slots = max(1, max_slots - len(active_positions))
                notional = cash / free_slots
                cash -= notional
                trade_rec = {
                    "symbol": sym,
                    "sector": dataset.sector_map.get(sym, "General"),
                    "signal_date": sim["signal_date"],
                    "entry_date": sim["entry_date"],
                    "exit_date": sim["exit_date"],
                    "entry_price": sim["entry_price"],
                    "exit_price": sim["exit_price"],
                    "exit_reason": sim["exit_reason"],
                    "gross": sim["gross"],
                    "net": sim["net"],
                    "cost": sim["cost"],
                    "mfe_pct": sim["mfe_pct"],
                    "mae_pct": sim["mae_pct"],
                }
                exit_d = dt.date.fromisoformat(sim["exit_date"])
                if exit_d == cur_date:
                    # Same-day entry + exit (e.g. intraday stop or take profit on t+1)
                    cash += notional * (1.0 + sim["net"] / 100.0)
                    closed_trades.append(trade_rec)
                else:
                    active_positions.append(
                        {
                            "symbol": sym,
                            "notional": notional,
                            "entry_price": sim["entry_price"],
                            "exit_date_obj": exit_d,
                            "net": sim["net"],
                            "marks": sim["daily_marks"],
                            "trade": trade_rec,
                        }
                    )
                    held_symbols.add(sym)

        # 3. Mark-to-market daily equity
        open_value = 0.0
        for pos in active_positions:
            mark = pos["marks"].get(cur_date, pos["entry_price"])
            open_value += pos["notional"] * (mark / pos["entry_price"])
        equity = cash + open_value
        iso = cur_date.isoformat()
        daily_equity[iso] = round(equity, 2)
        daily_returns[iso] = round(((equity / prev_equity) - 1.0) * 100.0, 6) if prev_equity > 0 else 0.0
        prev_equity = equity

    n_trades = len(closed_trades)
    signal_days = len({t["signal_date"] for t in closed_trades})
    rets = [t["net"] for t in closed_trades]
    avg_net = float(np.mean(rets)) if rets else 0.0
    wins = sum(r for r in rets if r > 0)
    losses = sum(abs(r) for r in rets if r < 0)
    pf = (wins / losses) if losses > 0 else (99.0 if wins > 0 else 0.0)
    win_rate = (sum(1 for r in rets if r > 0) / n_trades * 100.0) if n_trades > 0 else 0.0

    # Equity curve drawdown & Sharpe
    eq_vals = list(daily_equity.values())
    ret_vals = list(daily_returns.values())
    peak = INITIAL_CAPITAL
    mdd = 0.0
    for eq in eq_vals:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
        if dd > mdd:
            mdd = dd
    cum_ret_pct = ((eq_vals[-1] / INITIAL_CAPITAL) - 1.0) * 100.0 if eq_vals else 0.0
    sharpe = 0.0
    if len(ret_vals) >= 10:
        sd = float(np.std(ret_vals, ddof=1))
        if sd > 1e-9:
            sharpe = float(np.mean(ret_vals) / sd * np.sqrt(252.0))

    return {
        "n_trades": n_trades,
        "n_signal_days": signal_days,
        "avg_net_return_pct": round(avg_net, 4),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 3),
        "cumulative_portfolio_return_pct": round(cum_ret_pct, 4),
        "max_drawdown_pct": round(mdd, 4),
        "annualized_sharpe": round(sharpe, 3),
        "boundary_excluded_signals": boundary_excluded,
        "capacity_skipped_signals": capacity_skipped,
        "unresolved_missing_data_count": unresolved_count,
        "bootstrap_ci": cluster_bootstrap_ci(closed_trades),
        "cost_stress": cost_stress_test(closed_trades, multipliers=(1.0, 1.5, 2.0)),
        "concentration": concentration_audit(closed_trades),
        "_daily_returns": daily_returns,
        "_trades": closed_trades,
    }


def moving_block_bootstrap_ci(
    deltas: list[float],
    *,
    block_size: int = 5,
    n_iterations: int = 400,
    seed: int = 42,
) -> dict[str, Any]:
    """Deterministic moving-block bootstrap 95% CI on daily paired return differences."""
    arr = np.asarray([float(x) for x in deltas if np.isfinite(x)], dtype=np.float64)
    n = len(arr)
    if n < max(5, block_size):
        mean_v = float(np.mean(arr)) if n > 0 else 0.0
        return {
            "mean": round(mean_v, 6),
            "ci_lower": -99.0,
            "ci_upper": round(mean_v, 6),
            "n_days": n,
            "passed": False,
        }

    b = min(block_size, n)
    n_blocks = int(np.ceil(n / b))
    max_start = n - b + 1
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_iterations, dtype=np.float64)

    for i in range(n_iterations):
        starts = rng.integers(0, max_start, size=n_blocks)
        sampled = np.concatenate([arr[s : s + b] for s in starts])[:n]
        boot_means[i] = float(np.mean(sampled))

    ci_lo = float(np.percentile(boot_means, 2.5))
    ci_hi = float(np.percentile(boot_means, 97.5))
    obs_mean = float(np.mean(arr))
    return {
        "mean": round(obs_mean, 6),
        "ci_lower": round(ci_lo, 6),
        "ci_upper": round(ci_hi, 6),
        "n_days": n,
        "passed": ci_lo > 0.0,
    }


def _strip_private(arm: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in arm.items() if not k.startswith("_")}


def _build_pairwise_comparison(
    full_arm: dict[str, Any],
    ref_arm: dict[str, Any],
    *,
    min_ref_trades: int,
    config: EvaluatorConfig,
) -> dict[str, Any]:
    ref_n = int(ref_arm["n_trades"])
    if ref_n < min_ref_trades:
        return {
            "status": "inconclusive_sparse_control",
            "ref_trades": ref_n,
            "mean_daily_delta_pct": None,
            "cum_return_delta_pct": None,
            "beat_reference": False,
            "bootstrap": None,
        }

    full_daily = full_arm["_daily_returns"]
    ref_daily = ref_arm["_daily_returns"]
    common_dates = sorted(set(full_daily.keys()) & set(ref_daily.keys()))
    deltas = [full_daily[d] - ref_daily[d] for d in common_dates]
    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    cum_delta = float(full_arm["cumulative_portfolio_return_pct"]) - float(
        ref_arm["cumulative_portfolio_return_pct"]
    )
    boot = moving_block_bootstrap_ci(
        deltas,
        block_size=config.bootstrap_block_days,
        n_iterations=config.bootstrap_iterations,
    )
    return {
        "status": "comparable",
        "ref_trades": ref_n,
        "n_paired_days": len(common_dates),
        "mean_daily_delta_pct": round(mean_delta, 6),
        "cum_return_delta_pct": round(cum_delta, 4),
        "beat_reference": mean_delta > 0.0 and cum_delta > 0.0,
        "bootstrap": boot,
    }


def _evaluate_spec_on_partition(
    dataset: LoadedDiscoveryDataset,
    spec: dict[str, Any],
    *,
    part_start: dt.date,
    part_end: dt.date,
    min_trades: int,
    min_signal_days: int,
    config: EvaluatorConfig,
    partition_name: str,
) -> dict[str, Any]:
    exit_policy = config.resolved_exit_policy()
    if isinstance(spec.get("exit_policy"), dict):
        merged = dict(exit_policy)
        merged.update(spec["exit_policy"])
        exit_policy = merged

    arm_signals: dict[str, dict[str, pd.Series]] = {arm: {} for arm in ARMS}
    for sym, df in dataset.frames.items():
        arms_map = evaluate_spec_arms(df, spec)
        for arm in ARMS:
            arm_signals[arm][sym] = arms_map[arm]

    raw_arms = {
        arm: _evaluate_arm_on_partition(
            dataset,
            arm_signals[arm],
            part_start=part_start,
            part_end=part_end,
            config=config,
            exit_policy=exit_policy,
        )
        for arm in ARMS
    }

    full = raw_arms["full"]
    min_ref = max(3, min_trades // 2)
    comparisons = {
        ref: _build_pairwise_comparison(full, raw_arms[ref], min_ref_trades=min_ref, config=config)
        for ref in ("baseline", "ablation", "reverse_control")
    }

    # Verdict logic: fail-closed on sparse data, unresolved data, or failing falsification arms
    if full["unresolved_missing_data_count"] > 0:
        verdict = "inconclusive"
        reason = "Unresolved missing market data encountered during open holding periods."
    elif full["n_trades"] < min_trades or full["n_signal_days"] < min_signal_days:
        verdict = "inconclusive"
        reason = (
            f"Sparse sample on {partition_name}: {full['n_trades']} trades across "
            f"{full['n_signal_days']} signal days (need >= {min_trades} trades, >= {min_signal_days} days)."
        )
    elif any(c["status"] != "comparable" for c in comparisons.values()):
        sparse_arms = [k for k, c in comparisons.items() if c["status"] != "comparable"]
        verdict = "inconclusive"
        reason = f"Sparse control arm(s) {sparse_arms}; cannot claim outperformance against empty controls."
    elif full["cumulative_portfolio_return_pct"] <= 0.0 or full["avg_net_return_pct"] <= 0.0:
        verdict = "failed"
        reason = (
            f"Negative net expectation after costs on {partition_name}: "
            f"cum={full['cumulative_portfolio_return_pct']:.2f}%, avg_trade={full['avg_net_return_pct']:.3f}%."
        )
    elif not comparisons["baseline"]["beat_reference"]:
        verdict = "failed"
        reason = "Failed to outperform context-only baseline."
    elif not comparisons["ablation"]["beat_reference"]:
        verdict = "failed"
        reason = "Failed ablation test: removing the setup component did not degrade performance."
    elif not comparisons["reverse_control"]["beat_reference"]:
        verdict = "failed"
        reason = "Failed reverse control: inverted directional trigger matched or beat full mechanism."
    elif not full["cost_stress"].get("1.5x", {}).get("passed", False):
        verdict = "failed"
        reason = "Failed 1.5x transaction cost stress test."
    else:
        verdict = (
            "passed_development"
            if partition_name == "discovery"
            else "passed_historical_validation"
        )
        reason = (
            f"Passed all 4-arm falsification checks and 1.5x cost stress on {partition_name} "
            f"(cum={full['cumulative_portfolio_return_pct']:+.2f}%, PF={full['profit_factor']:.2f})."
        )

    return {
        "partition": partition_name,
        "start_date": part_start.isoformat(),
        "end_date": part_end.isoformat(),
        "verdict": verdict,
        "reason": reason,
        "arms": {arm: _strip_private(res) for arm, res in raw_arms.items()},
        "pairwise_comparisons": comparisons,
        "full_daily_returns": full["_daily_returns"],
        "full_trades": full["_trades"][:250],
    }


def evaluate_spec_development(
    dataset: LoadedDiscoveryDataset,
    spec: dict[str, Any],
    config: EvaluatorConfig = EvaluatorConfig(),
) -> dict[str, Any]:
    """Evaluate a mechanism spec strictly on the discovery partition."""
    return _evaluate_spec_on_partition(
        dataset,
        spec,
        part_start=dataset.discovery_start,
        part_end=dataset.discovery_end,
        min_trades=config.min_dev_trades,
        min_signal_days=config.min_dev_signal_days,
        config=config,
        partition_name="discovery",
    )


def evaluate_batch_validation_once(
    dataset: LoadedDiscoveryDataset,
    dev_eligible_specs: list[dict[str, Any]],
    config: EvaluatorConfig = EvaluatorConfig(),
) -> dict[str, dict[str, Any]]:
    """Single-shot frozen validation on the validation partition for dev-eligible specs only."""
    results: dict[str, dict[str, Any]] = {}
    for spec in dev_eligible_specs:
        sid = str(spec["spec_id"])
        results[sid] = _evaluate_spec_on_partition(
            dataset,
            spec,
            part_start=dataset.validation_start,
            part_end=dataset.validation_end,
            min_trades=config.min_val_trades,
            min_signal_days=config.min_val_signal_days,
            config=config,
            partition_name="validation",
        )
    return results
