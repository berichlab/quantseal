"""Unit and Monte Carlo regression tests for anytime-valid test-martingale E-values."""
from __future__ import annotations

import random

from quantseal.core.evalue import evalue_betting, merge_evalues, rejects_h0


def test_empty_returns_no_evidence():
    r = evalue_betting([])
    assert r["n"] == 0
    assert r["evalue"] == 1.0
    assert r["peak_evalue"] == 1.0
    assert r["rejected"] is False
    assert rejects_h0([]) is False


def test_strong_positive_signal_rejects():
    deltas = [4.0] * 120
    r = evalue_betting(deltas, cost=0.0, alpha=0.01, include_series=True)
    assert r["peak_evalue"] >= 100.0
    assert r["rejected"] is True
    assert len(r["series"]) == 120
    assert rejects_h0(deltas, cost=0.0, alpha=0.01) is True


def test_symmetric_null_does_not_reject():
    deltas = [3.0, -3.0] * 60
    assert rejects_h0(deltas, cost=0.0, alpha=0.01) is False
    assert evalue_betting(deltas, cost=0.0)["peak_evalue"] < 100.0


def test_negative_signal_stays_bounded_at_one():
    deltas = [-4.0] * 120
    r = evalue_betting(deltas, cost=0.0)
    assert r["evalue"] <= 1.0 + 1e-9
    assert r["rejected"] is False


def test_cost_hurdle_prevents_false_rejection():
    deltas = [0.3] * 150
    assert rejects_h0(deltas, cost=0.45, alpha=0.01) is False


def test_deterministic_and_valid_merge():
    deltas = [1.0, -0.5, 2.0, 0.1, -1.0] * 30
    assert evalue_betting(deltas, cost=0.1) == evalue_betting(deltas, cost=0.1)
    assert merge_evalues([2.0, 6.0]) == 4.0
    assert merge_evalues([2.0, 6.0], weights=[1.0, 3.0]) == 5.0


def test_type1_error_controlled_under_symmetric_null():
    rng = random.Random(20260730)
    trials = 250
    false_rejects = 0
    for _ in range(trials):
        deltas = [rng.gauss(0.0, 2.0) for _ in range(120)]
        if rejects_h0(deltas, cost=0.0, alpha=0.01):
            false_rejects += 1
    assert false_rejects <= 10, f"Type-I error inflated under symmetric null: {false_rejects}/{trials}"


def test_type1_error_controlled_under_left_skew_null():
    """Critical regression: heavy left-tail zero-mean null must NOT blow up via clipping."""
    rng = random.Random(20260730)
    p_crash, crash = 0.15, -18.0
    small_win = -p_crash * crash / (1.0 - p_crash)
    trials = 600
    false_rejects = 0
    for _ in range(trials):
        deltas = [crash if rng.random() < p_crash else small_win for _ in range(150)]
        if rejects_h0(deltas, cost=0.0, alpha=0.01):
            false_rejects += 1
    assert false_rejects <= 18, f"Left-skew null false promotion rate inflated: {false_rejects}/{trials}"
