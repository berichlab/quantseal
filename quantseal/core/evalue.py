"""Anytime-valid E-value (test-martingale) sequential testing for shadow promotion.

Why E-values instead of p-values or classic SPRT:
- Composite null hypothesis (H0: E[delta] <= cost with unknown variance) where
  simple-vs-simple parametric SPRT assumptions break down.
- Multiple challengers can be combined validly by simple averaging (`merge_evalues`).
- Anytime-valid under continuous monitoring: you can inspect shadow equity after
  every single trade or day without inflating Type-I error. By Ville's inequality,
  for any non-negative supermartingale K_t under H0:
      P(sup_t K_t >= 1 / alpha) <= alpha.

Construction (one-sided betting / hedged capital martingale, Waudby-Smith & Ramdas 2023):
  Test H0: E[delta] <= cost (challenger is no better than benchmark/baseline).
  Bounded transform:
      y_i = clip((delta_i - cost + scale) / (2 * scale), 0, 1) in [0, 1]
      H0 <=> E[y] <= 0.5 = m0.
  Capital process:
      K_t = prod_{i <= t} (1 + lambda_i * (y_i - m0))
  where lambda_i in [0, lambda_max] is strictly predictable (computed only from
  observations 1 .. i-1) via aGRAPA-style shrinkage:
      lambda_i = clip((mu_hat - m0) / (var_hat + (mu_hat - m0)^2), 0, lambda_max).

CRITICAL TAIL-SCALE INVARIANT:
  `scale` MUST cover the true left tail of |delta - cost|. If `scale` is too
  small, clipping large losses at y = 0 systematically understates left-tail
  mass, turning a zero-mean left-skewed null (many small wins + occasional large
  loss) into E[y] > 0.5, breaking supermartingale validity and inflating false
  promotions. Default `DEFAULT_SCALE = 20.0` (%) covers typical daily/swing
  return differences; increase `scale` for higher-volatility assets (e.g. crypto
  alts) and verify against a left-skewed null Monte Carlo test.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

DEFAULT_ALPHA = 0.01   # Threshold 1 / alpha = 100.0
DEFAULT_SCALE = 20.0   # Percentage-point scale protecting against left-skew clip bias
_M0 = 0.5
_LAMBDA_MAX = 1.5      # < 2.0 guarantees every factor >= 1 - 1.5 * 0.5 = 0.25 > 0


def evalue_betting(
    deltas: Iterable[float],
    *,
    cost: float = 0.0,
    alpha: float = DEFAULT_ALPHA,
    scale: float = DEFAULT_SCALE,
    lambda_max: float = _LAMBDA_MAX,
    include_series: bool = False,
) -> dict[str, Any]:
    """Compute one-sided test-martingale E-value on paired return differences.

    Args:
        deltas: Sequence of paired return differences in percentage points.
        cost: Hurdle / extra cost drag in percentage points under H0: E[delta] <= cost.
        alpha: Significance level for anytime threshold `1 / alpha`.
        scale: Symmetric clipping bound (+/- scale) in percentage points.
        lambda_max: Maximum predictable betting fraction (< 2.0).
        include_series: When True, includes full step-by-step capital trajectory.

    Returns:
        Dict with `evalue`, `peak_evalue`, `threshold`, `rejected`, `n`,
        `clipped_count`, and optionally `series`.
    """
    if scale <= 0:
        raise ValueError("scale must be strictly positive")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")
    if not (0.0 < lambda_max < 2.0):
        raise ValueError("lambda_max must be in (0, 2)")

    capital = 1.0
    peak = 1.0
    sum_y = 0.0
    sum_y2 = 0.0
    n = 0
    clipped = 0
    threshold = 1.0 / float(alpha)
    series: list[dict[str, float | int]] = []

    for raw_delta in deltas:
        d = float(raw_delta)
        raw_y = (d - float(cost) + float(scale)) / (2.0 * float(scale))
        if raw_y > 1.0:
            y = 1.0
            clipped += 1
        elif raw_y < 0.0:
            y = 0.0
            clipped += 1
        else:
            y = raw_y

        # Predictable betting fraction lambda_i: strictly uses history 1..i-1
        if n >= 2:
            mu = sum_y / n
            var = sum_y2 / n - mu * mu
            if var < 1e-6:
                var = 1e-6
            lam = (mu - _M0) / (var + (mu - _M0) ** 2)
            if lam > lambda_max:
                lam = lambda_max
            elif lam < 0.0:
                lam = 0.0
        else:
            lam = 0.0

        capital *= 1.0 + lam * (y - _M0)
        if capital > peak:
            peak = capital

        sum_y += y
        sum_y2 += y * y
        n += 1

        if include_series:
            series.append(
                {
                    "step": n,
                    "delta": round(d, 4),
                    "lambda": round(lam, 4),
                    "evalue": round(capital, 4),
                    "peak_evalue": round(peak, 4),
                }
            )

    result: dict[str, Any] = {
        "evalue": round(capital, 6),
        "peak_evalue": round(peak, 6),
        "threshold": round(threshold, 4),
        "alpha": float(alpha),
        "scale": float(scale),
        "rejected": peak >= threshold,
        "n": n,
        "clipped_count": clipped,
    }
    if include_series:
        result["series"] = series
    return result


def rejects_h0(
    deltas: Iterable[float],
    *,
    cost: float = 0.0,
    alpha: float = DEFAULT_ALPHA,
    scale: float = DEFAULT_SCALE,
) -> bool:
    """Anytime-valid rejection decision: True iff sup_t K_t >= 1 / alpha."""
    return bool(evalue_betting(deltas, cost=cost, alpha=alpha, scale=scale)["rejected"])


def merge_evalues(evalues: Sequence[float], weights: Sequence[float] | None = None) -> float:
    """Validly combine multiple E-values under arbitrary dependence via weighted average."""
    if not evalues:
        return 1.0
    if weights is None:
        return float(sum(float(e) for e in evalues) / len(evalues))
    if len(weights) != len(evalues):
        raise ValueError("weights length must match evalues length")
    total_w = sum(float(w) for w in weights)
    if total_w <= 0:
        raise ValueError("weights must sum to a positive number")
    return float(sum(float(e) * float(w) for e, w in zip(evalues, weights, strict=True)) / total_w)
