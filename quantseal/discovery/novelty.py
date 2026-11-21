"""Zero-exec structural and behavioral novelty audit against reference proxy strategies.

Computes:
- Structural AST token Jaccard similarity vs known reference specs.
- Behavioral signal-set Jaccard and containment overlap on the discovery partition.
- Honest classification (`duplicate_existing`, `improvement_not_new_mechanism`,
  or `distinct_candidate`) without ever invoking exec() or arbitrary code.
"""
from __future__ import annotations

from typing import Any

from quantseal.data.base import LoadedDiscoveryDataset
from quantseal.discovery.spec import evaluate_spec_arms, extract_structural_tokens


def _signal_pairs(
    dataset: LoadedDiscoveryDataset,
    spec: dict[str, Any],
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for sym, df in dataset.frames.items():
        disc_mask = (df["trade_date"] >= dataset.discovery_start) & (
            df["trade_date"] <= dataset.discovery_end
        )
        full_sig = evaluate_spec_arms(df, spec)["full"] & disc_mask
        for d in df.loc[full_sig, "trade_date"].tolist():
            pairs.add((sym, d.isoformat()))
    return pairs


def _jaccard(a: set[Any], b: set[Any]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union > 0 else 0.0


def _containment(a: set[Any], b: set[Any]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def build_reference_library(
    dataset: LoadedDiscoveryDataset,
    reference_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    library: list[dict[str, Any]] = []
    for spec in reference_specs:
        library.append(
            {
                "spec_id": spec["spec_id"],
                "fingerprint": spec.get("fingerprint"),
                "tokens": extract_structural_tokens(spec),
                "signals": _signal_pairs(dataset, spec),
            }
        )
    return library


def assess_candidate_novelty(
    dataset: LoadedDiscoveryDataset,
    spec: dict[str, Any],
    reference_library: list[dict[str, Any]],
    *,
    dev_eval: dict[str, Any],
) -> dict[str, Any]:
    """Compare a candidate against reference specs on structure and discovery signals."""
    cand_tokens = extract_structural_tokens(spec)
    cand_signals = _signal_pairs(dataset, spec)

    max_struct_jaccard = 0.0
    max_sig_jaccard = 0.0
    max_sig_containment = 0.0
    closest_ref: str | None = None

    for ref in reference_library:
        if ref["spec_id"] == spec["spec_id"]:
            continue
        sj = _jaccard(cand_tokens, ref["tokens"])
        bj = _jaccard(cand_signals, ref["signals"])
        bc = _containment(cand_signals, ref["signals"])
        score = max(bj, bc * 0.85, sj * 0.7)
        if score > max(max_sig_jaccard, max_sig_containment * 0.85, max_struct_jaccard * 0.7):
            closest_ref = ref["spec_id"]
        max_struct_jaccard = max(max_struct_jaccard, sj)
        max_sig_jaccard = max(max_sig_jaccard, bj)
        max_sig_containment = max(max_sig_containment, bc)

    if len(cand_signals) == 0:
        state = "inconclusive"
        explanation = "Zero discovery signals; novelty cannot be assessed."
    elif max_sig_jaccard >= 0.75:
        state = "duplicate_existing"
        explanation = (
            f"High behavioral overlap (signal Jaccard {max_sig_jaccard:.2f}) with "
            f"reference '{closest_ref}'; classified as duplicate."
        )
    elif max_sig_containment >= 0.80:
        state = "improvement_not_new_mechanism"
        explanation = (
            f"Candidate signals are largely a subset (containment {max_sig_containment:.2f}) "
            f"of '{closest_ref}'; classified as filter refinement rather than novel mechanism."
        )
    else:
        state = "distinct_candidate"
        explanation = (
            f"Distinct behavioral profile (max signal Jaccard {max_sig_jaccard:.2f}, "
            f"structural Jaccard {max_struct_jaccard:.2f} vs '{closest_ref or 'none'}')."
        )

    return {
        "state": state,
        "closest_reference": closest_ref,
        "max_structural_jaccard": round(max_struct_jaccard, 4),
        "max_signal_jaccard": round(max_sig_jaccard, 4),
        "max_signal_containment": round(max_sig_containment, 4),
        "candidate_signal_count": len(cand_signals),
        "explanation": explanation,
    }
