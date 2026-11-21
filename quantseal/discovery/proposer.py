"""Discovery-only empirical evidence cards and fail-closed AI mechanism proposer.

Anti-leakage & budget guarantees:
1. Evidence cards are physically sliced strictly to `<= discovery_end`, with
   warmup rows excluded from discovery quantile statistics and forward-return
   horizons bounded strictly inside `<= discovery_end`. Validation and sealed
   partitions are NEVER passed into the proposer.
2. Pre-call quota reservation: `on_before_call` persists the redacted prompt
   before invoking the external LLM so crashes still count against budget.
3. Zero synthetic fallback: if no LLM key is configured or the call fails,
   returns 0 AI candidates honestly — never disguises templates as AI proposals.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from quantseal.data.base import LoadedDiscoveryDataset
from quantseal.discovery.llm import LLMConfig, complete_text, sanitize_text_no_secrets
from quantseal.discovery.spec import (
    APPROVED_OPS,
    APPROVED_TRANSFORMS,
    MAX_AST_DEPTH,
    MAX_CLAUSES_PER_COMPONENT,
    MAX_LOOKBACK,
    REQUIRED_INFORMATION_TIME,
    SpecValidationError,
    evaluate_operand,
    validate_spec,
)


def build_discovery_evidence_cards(
    dataset: LoadedDiscoveryDataset,
    *,
    horizon_days: int = 5,
    prior_dev_summary: list[dict[str, Any]] | None = None,
    external_mcp_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute strictly discovery-only feature quantiles and unconditional forward stats."""
    disc_start = dataset.discovery_start
    disc_end = dataset.discovery_end

    dev_rows: list[pd.DataFrame] = []
    for sym, df in sorted(dataset.frames.items()):
        # Physically exclude everything after discovery_end before any rolling computation
        up_to_end = df[df["trade_date"] <= disc_end].reset_index(drop=True)
        if up_to_end.empty:
            continue

        if "volume" in up_to_end.columns:
            for w in (5, 20):
                up_to_end[f"_vol_ratio_{w}"] = evaluate_operand(
                    up_to_end,
                    {"feature": "volume", "transform": "ratio_to_rolling_mean", "window": w, "lag": 0},
                )

        # Forward exploratory return strictly bounded inside <= discovery_end
        opens = up_to_end["open"].to_numpy(dtype=np.float64)
        closes = up_to_end["close"].to_numpy(dtype=np.float64)
        fwd = np.full(len(up_to_end), np.nan, dtype=np.float64)
        for i in range(len(up_to_end)):
            entry_i = i + 1
            exit_i = i + horizon_days
            if exit_i < len(up_to_end) and np.isfinite(opens[entry_i]) and opens[entry_i] > 0 and np.isfinite(closes[exit_i]):
                fwd[i] = ((closes[exit_i] / opens[entry_i]) - 1.0) * 100.0
        up_to_end["_dev_fwd_ret"] = fwd

        # Trim to [discovery_start, discovery_end] so warmup rows do not skew quantiles
        sub = up_to_end[
            (up_to_end["trade_date"] >= disc_start) & (up_to_end["trade_date"] <= disc_end)
        ].copy()
        if not sub.empty:
            sub["_symbol"] = sym
            dev_rows.append(sub)

    if not dev_rows:
        return {
            "partition": "discovery_only",
            "discovery_start": disc_start.isoformat(),
            "discovery_end": disc_end.isoformat(),
            "asset_count": 0,
            "available_features": sorted(dataset.available_columns),
            "feature_quantiles": {},
        }

    combined = pd.concat(dev_rows, ignore_index=True)
    quantiles_summary: dict[str, dict[str, Any]] = {}
    for col in sorted(dataset.available_columns):
        if col not in combined.columns:
            continue
        vals = pd.to_numeric(combined[col], errors="coerce").dropna()
        vals = vals[np.isfinite(vals)]
        if len(vals) < 5:
            continue
        qs = np.quantile(vals.to_numpy(dtype=np.float64), [0.1, 0.25, 0.5, 0.75, 0.9])
        quantiles_summary[col] = {
            "unit": dataset.feature_units.get(col, "numeric"),
            "p10": round(float(qs[0]), 4),
            "p25": round(float(qs[1]), 4),
            "p50": round(float(qs[2]), 4),
            "p75": round(float(qs[3]), 4),
            "p90": round(float(qs[4]), 4),
            "n": int(len(vals)),
        }

    valid_fwd = combined[combined["_dev_fwd_ret"].notna()]
    uncond_mean = round(float(valid_fwd["_dev_fwd_ret"].mean()), 4) if not valid_fwd.empty else None

    cards: dict[str, Any] = {
        "partition": "discovery_only",
        "warmup_excluded": True,
        "discovery_start": disc_start.isoformat(),
        "discovery_end": disc_end.isoformat(),
        "asset_count": int(combined["_symbol"].nunique()),
        "row_count": int(len(combined)),
        "exploratory_horizon_days": int(horizon_days),
        "unconditional_fwd_mean_pct": uncond_mean,
        "available_features": sorted(dataset.available_columns),
        "feature_quantiles": quantiles_summary,
    }
    if prior_dev_summary:
        # Strictly pass whitelisted discovery-only outcome codes from direct parent
        safe_prior = [
            {
                "spec_id": str(item.get("spec_id", ""))[:64],
                "dev_verdict": str(item.get("dev_verdict", ""))[:48],
                "dev_reason": str(item.get("dev_reason", ""))[:200],
            }
            for item in prior_dev_summary[:10]
        ]
        cards["prior_discovery_feedback"] = safe_prior
    if external_mcp_evidence:
        cards["external_mcp_evidence"] = external_mcp_evidence[:10]
    return cards


def _extract_json_array(raw_text: str) -> list[Any] | None:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", cleaned, re.IGNORECASE)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("specs"), list):
            return parsed["specs"]
    except ValueError:
        return None
    return None


def build_proposal_prompt(
    evidence_cards: dict[str, Any],
    *,
    existing_spec_ids: list[str],
    max_variants: int,
) -> str:
    safe_cards = dict(evidence_cards)
    for forbidden in ("validation", "sealed", "holdout", "raw_response"):
        safe_cards.pop(forbidden, None)

    avail = ", ".join(safe_cards.get("available_features") or [])
    transforms = ", ".join(sorted(APPROVED_TRANSFORMS))
    ops = ", ".join(sorted(APPROVED_OPS))

    example = [
        {
            "spec_id": "ai_low_vol_reclaim",
            "title": "Low Volatility Trend Pullback Reclaim",
            "source": "ai",
            "information_time": REQUIRED_INFORMATION_TIME,
            "hypothesis": "Assets above 20d mean with compressed 5d range that expand upward intraday exhibit follow-through.",
            "prediction": "Full mechanism outperforms context baseline, setup ablation, and negative-intraday reverse control.",
            "falsifier": "Falsified if paired excess return vs baseline, ablation, or reverse_control is <= 0 after costs.",
            "baseline": {"description": "Close >= 0.98 * 20d rolling mean"},
            "ablation": {"remove_component": "setup", "description": "Remove 5d range compression setup"},
            "reverse_control": {"description": "Invert trigger to intraday_ret < -0.4"},
            "context": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close", "transform": "ratio_to_rolling_mean", "window": 20, "lag": 0},
                        "op": ">=",
                        "right": 0.98,
                    }
                ],
            },
            "setup": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "range_pct", "transform": "rolling_mean", "window": 5, "lag": 1},
                        "op": "<=",
                        "right": 2.5,
                    }
                ],
            },
            "trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "intraday_ret", "transform": "raw", "lag": 0},
                        "op": ">",
                        "right": 0.4,
                    }
                ],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "intraday_ret", "transform": "raw", "lag": 0},
                        "op": "<",
                        "right": -0.4,
                    }
                ],
            },
        }
    ]

    return (
        "You are a skeptical quantitative researcher designing falsifiable trading hypotheses.\n"
        f"Propose up to {max_variants} distinct bounded JSON mechanism specs based ONLY on the discovery-period evidence below.\n\n"
        "STRICT GRAMMAR RULES:\n"
        "- Return ONLY a valid JSON array of spec objects. No Python code, no exec/eval/src keys.\n"
        f"- information_time MUST be '{REQUIRED_INFORMATION_TIME}'.\n"
        f"- Allowed features: {avail}\n"
        f"- Allowed transforms: {transforms}\n"
        f"- Allowed ops: {ops}\n"
        f"- lag >= 0, lag + window <= {MAX_LOOKBACK}, AST depth <= {MAX_AST_DEPTH}, clauses/node <= {MAX_CLAUSES_PER_COMPONENT}.\n"
        "- rolling_quantile MUST specify explicit 'q' in [0.0, 1.0].\n"
        "- Every spec MUST include: spec_id (lowercase snake_case), title, source='ai', information_time, "
        "hypothesis, prediction, falsifier, baseline, ablation (remove_component='context' or 'setup'), "
        "reverse_control, context, setup, trigger, reverse_trigger (structurally distinct from trigger).\n"
        f"- Avoid duplicating existing spec_ids: {existing_spec_ids}\n\n"
        f"DISCOVERY EVIDENCE CARDS:\n{json.dumps(safe_cards, indent=2)}\n\n"
        f"VALID EXAMPLE SCHEMA:\n{json.dumps(example, indent=2)}\n"
    )


def propose_autonomous_specs(
    evidence_cards: dict[str, Any],
    *,
    llm_config: LLMConfig,
    available_columns: set[str],
    existing_spec_ids: list[str],
    existing_fingerprints: set[str],
    max_variants: int = 3,
    on_before_call: Callable[[dict[str, Any]], None] | None = None,
    llm_caller: Callable[[str, LLMConfig], dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Invoke BYOK LLM with pre-call reservation and validate returned specs fail-closed."""
    audit: dict[str, Any] = {
        "called": False,
        "provider": llm_config.provider,
        "model": llm_config.model,
        "accepted_count": 0,
        "rejected": [],
        "error": None,
    }

    if max_variants <= 0 or not llm_config.is_configured():
        audit["status"] = "skipped_unconfigured" if not llm_config.is_configured() else "skipped_zero_budget"
        return [], audit

    prompt = build_proposal_prompt(
        evidence_cards,
        existing_spec_ids=existing_spec_ids,
        max_variants=max_variants,
    )
    redacted_prompt = sanitize_text_no_secrets(prompt)

    # Pre-call quota reservation before hitting external API
    if on_before_call is not None:
        on_before_call(
            {
                "reserved_at": dt.datetime.now(dt.UTC).isoformat(),
                "provider": llm_config.provider,
                "model": llm_config.model,
                "prompt_preview": redacted_prompt[:1200],
            }
        )

    audit["called"] = True
    try:
        caller = llm_caller or (lambda p, cfg: complete_text(p, cfg))
        response = caller(prompt, llm_config)
        raw_text = sanitize_text_no_secrets(response.get("text") or "")
        audit["usage"] = response.get("usage") or {}
        audit["raw_response_preview"] = raw_text[:2000]
    except Exception as exc:
        audit["status"] = "llm_call_failed"
        audit["error"] = sanitize_text_no_secrets(str(exc), max_len=500)
        return [], audit

    parsed = _extract_json_array(raw_text)
    if parsed is None:
        audit["status"] = "invalid_json_response"
        audit["error"] = "LLM response did not contain a parseable JSON array"
        return [], audit

    accepted: list[dict[str, Any]] = []
    seen_ids = set(existing_spec_ids)
    seen_fps = set(existing_fingerprints)

    for idx, raw_item in enumerate(parsed):
        if len(accepted) >= max_variants:
            audit["rejected"].append({"index": idx, "reason": "exceeded_max_ai_variants"})
            continue
        if not isinstance(raw_item, dict):
            audit["rejected"].append({"index": idx, "reason": "non_object_spec"})
            continue
        candidate = dict(raw_item)
        candidate["source"] = "ai"
        try:
            validated = validate_spec(candidate, available_columns=available_columns)
        except SpecValidationError as exc:
            audit["rejected"].append(
                {
                    "index": idx,
                    "spec_id": str(raw_item.get("spec_id", "")),
                    "error_code": exc.error_code,
                    "reason": str(exc),
                }
            )
            continue

        fp = validated["fingerprint"]
        sid = validated["spec_id"]
        if sid in seen_ids or fp in seen_fps:
            audit["rejected"].append(
                {
                    "index": idx,
                    "spec_id": sid,
                    "error_code": "duplicate_spec",
                    "reason": "Duplicate spec_id or executable AST fingerprint",
                }
            )
            continue

        seen_ids.add(sid)
        seen_fps.add(fp)
        accepted.append(validated)

    audit["accepted_count"] = len(accepted)
    audit["status"] = "completed"
    return accepted, audit
