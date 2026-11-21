"""Zero-exec Bounded Mechanism Spec Grammar for autonomous strategy discovery.

Core safety & scientific invariants:
1. ZERO arbitrary code execution: no exec/eval/compile/Python strings. Every
   strategy candidate is a strictly validated declarative JSON AST.
2. Strict lookback & complexity bounds: lag >= 0, lag + window <= 60,
   MAX_AST_DEPTH = 4, MAX_CLAUSES_PER_COMPONENT = 6, MAX_TOTAL_NODES = 32.
3. Mandatory 4-arm falsification structure: `context`, `setup`, `trigger`,
   and explicit `reverse_trigger`, plus required scientific fields
   (`information_time`, `hypothesis`, `prediction`, `falsifier`, `baseline`,
   `ablation`, `reverse_control`).
4. Missing-value semantics: any comparison involving NaN evaluates strictly to
   False (never coerced to 0). Specs referencing unavailable columns fail closed.
5. Static pure-conjunction contradiction detection rejects logically impossible
   conditions (e.g. `ret_1d > 2.0` AND `ret_1d <= 1.0`) before evaluation.
6. Canonical `spec_fingerprint` hashes executable logic ONLY, guaranteeing
   deterministic deduplication even when an LLM renames a spec or rewrites prose.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from quantseal.data.base import CORE_OBSERVABLE_COLUMNS

MAX_AST_DEPTH = 4
MAX_LOOKBACK = 60
MAX_CLAUSES_PER_COMPONENT = 6
MAX_TOTAL_NODES = 32
MAX_SEQUENCE_STEPS = 3

VALID_SOURCES = ("seed", "control", "ai")
REQUIRED_INFORMATION_TIME = "t_close_execute_t_plus_1_open"

CAUSAL_DISCLAIMER_DEFAULT = (
    "This specification relies solely on surface observable bar features at close t "
    "with execution at next session open t+1; prose hypotheses do not constitute "
    "causal proof or guaranteed future live profitability."
)

SHARED_DEFAULT_EXIT_POLICY: dict[str, Any] = {
    "policy_name": "shared_swing_v1",
    "entry_rule": "t_plus_1_open",
    "stop_loss_pct": -5.0,
    "take_profit_pct": 10.0,
    "trailing_stop_pct": -6.0,
    "max_hold_days": 10,
}

WINDOWED_TRANSFORMS: frozenset[str] = frozenset(
    {
        "diff",
        "pct_change",
        "rolling_mean",
        "rolling_std",
        "rolling_max",
        "rolling_min",
        "rolling_sum",
        "rolling_zscore",
        "rolling_quantile",
        "ratio_to_rolling_mean",
    }
)

APPROVED_TRANSFORMS: frozenset[str] = frozenset({"raw", "lag", "sign"}) | WINDOWED_TRANSFORMS
APPROVED_OPS: frozenset[str] = frozenset({">", ">=", "<", "<=", "=="})
INVERT_OP_MAP: dict[str, str] = {">": "<=", ">=": "<", "<": ">=", "<=": ">", "==": "<"}

FORBIDDEN_CODE_KEYS: frozenset[str] = frozenset(
    {"src", "code", "python", "exec", "eval", "compile", "lambda", "__import__", "script"}
)

_SPEC_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class SpecValidationError(ValueError):
    """Raised when a mechanism specification violates grammar, causality, or data bounds."""

    def __init__(self, message: str, *, error_code: str = "invalid_spec") -> None:
        super().__init__(message)
        self.error_code = error_code


def _is_finite_number(val: Any) -> bool:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def _check_no_forbidden_keys(obj: Any, path: str = "spec") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            if key_str.lower() in FORBIDDEN_CODE_KEYS or "__" in key_str:
                raise SpecValidationError(
                    f"{path}.{key_str} contains a forbidden code or dunder key",
                    error_code="unsafe_spec_key",
                )
            _check_no_forbidden_keys(v, f"{path}.{key_str}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _check_no_forbidden_keys(item, f"{path}[{idx}]")


def _validate_operand(
    operand: Any,
    *,
    path: str,
    approved_features: frozenset[str],
    referenced_features: set[str],
    max_lookback_seen: list[int],
) -> int:
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        if not _is_finite_number(operand):
            raise SpecValidationError(
                f"{path} constant must be finite", error_code="non_finite_constant"
            )
        return 0

    if not isinstance(operand, dict):
        raise SpecValidationError(
            f"{path} operand must be a finite number or feature dict",
            error_code="invalid_operand",
        )

    if "const" in operand:
        if "feature" in operand:
            raise SpecValidationError(
                f"{path} operand cannot contain both 'const' and 'feature'",
                error_code="mixed_const_and_feature",
            )
        extra = sorted(set(operand.keys()) - {"const"})
        if extra:
            raise SpecValidationError(
                f"{path} constant operand has unknown keys: {extra}",
                error_code="unknown_operand_key",
            )
        if not _is_finite_number(operand["const"]):
            raise SpecValidationError(
                f"{path}.const must be finite", error_code="non_finite_constant"
            )
        return 0

    if "quantile" in operand:
        raise SpecValidationError(
            f"{path} uses invalid key 'quantile'; use explicit 'q' for rolling_quantile",
            error_code="unknown_operand_key",
        )
    unknown = sorted(set(operand.keys()) - {"feature", "transform", "lag", "window", "q"})
    if unknown:
        raise SpecValidationError(
            f"{path} has unknown operand keys: {unknown}",
            error_code="unknown_operand_key",
        )

    feature = operand.get("feature")
    if not isinstance(feature, str) or feature not in approved_features:
        raise SpecValidationError(
            f"{path}.feature '{feature}' is not in approved observable columns",
            error_code="unknown_feature",
        )
    referenced_features.add(feature)

    transform = operand.get("transform", "raw")
    if not isinstance(transform, str) or transform not in APPROVED_TRANSFORMS:
        raise SpecValidationError(
            f"{path}.transform '{transform}' is not in approved transforms",
            error_code="unknown_transform",
        )

    lag = operand.get("lag", 0)
    if isinstance(lag, bool) or not isinstance(lag, int):
        raise SpecValidationError(f"{path}.lag must be an integer", error_code="invalid_lag")
    if lag < 0:
        raise SpecValidationError(
            f"{path}.lag={lag} is negative (future lookahead forbidden)",
            error_code="future_lookahead",
        )
    if lag > MAX_LOOKBACK:
        raise SpecValidationError(
            f"{path}.lag={lag} exceeds MAX_LOOKBACK={MAX_LOOKBACK}",
            error_code="lookback_exceeded",
        )

    if transform in WINDOWED_TRANSFORMS:
        if "window" not in operand or operand["window"] is None:
            raise SpecValidationError(
                f"{path} transform '{transform}' requires explicit positive integer 'window'",
                error_code="missing_window",
            )
        window = operand["window"]
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise SpecValidationError(
                f"{path}.window must be a positive integer (>= 1)", error_code="invalid_window"
            )
        if window > MAX_LOOKBACK:
            raise SpecValidationError(
                f"{path}.window={window} exceeds MAX_LOOKBACK={MAX_LOOKBACK}",
                error_code="lookback_exceeded",
            )
        effective_lookback = int(lag) + int(window)
    else:
        if "window" in operand:
            raise SpecValidationError(
                f"{path} non-windowed transform '{transform}' forbids 'window'",
                error_code="unexpected_window_param",
            )
        effective_lookback = int(lag)

    if effective_lookback > MAX_LOOKBACK:
        raise SpecValidationError(
            f"{path} total lookback {effective_lookback} exceeds MAX_LOOKBACK={MAX_LOOKBACK}",
            error_code="lookback_exceeded",
        )

    if transform == "rolling_quantile":
        if "q" not in operand or operand["q"] is None:
            raise SpecValidationError(
                f"{path} rolling_quantile requires explicit 'q' in [0.0, 1.0]",
                error_code="missing_quantile_q",
            )
        q = operand["q"]
        if not _is_finite_number(q) or float(q) < 0.0 or float(q) > 1.0:
            raise SpecValidationError(
                f"{path}.q must be in [0.0, 1.0]", error_code="invalid_quantile"
            )
    elif "q" in operand:
        raise SpecValidationError(
            f"{path} transform '{transform}' forbids parameter 'q'",
            error_code="unexpected_quantile_param",
        )

    max_lookback_seen.append(max(1, effective_lookback))
    return effective_lookback


def _validate_condition_node(
    node: Any,
    *,
    path: str,
    depth: int,
    approved_features: frozenset[str],
    referenced_features: set[str],
    max_lookback_seen: list[int],
    node_counter: list[int],
) -> int:
    if depth > MAX_AST_DEPTH:
        raise SpecValidationError(
            f"{path} depth {depth} exceeds MAX_AST_DEPTH={MAX_AST_DEPTH}",
            error_code="ast_depth_exceeded",
        )
    if not isinstance(node, dict):
        raise SpecValidationError(f"{path} must be a dict node", error_code="invalid_node")

    node_counter[0] += 1
    if node_counter[0] > MAX_TOTAL_NODES:
        raise SpecValidationError(
            f"Total AST nodes exceed MAX_TOTAL_NODES={MAX_TOTAL_NODES}",
            error_code="ast_size_exceeded",
        )

    kind = node.get("type", "compare")
    if kind == "compare":
        unknown = sorted(set(node.keys()) - {"type", "left", "op", "right", "within_bars"})
        if unknown:
            raise SpecValidationError(
                f"{path} compare node has unknown keys: {unknown}",
                error_code="unknown_node_key",
            )
        op = node.get("op")
        if not isinstance(op, str) or op not in APPROVED_OPS:
            raise SpecValidationError(
                f"{path}.op '{op}' not in {sorted(APPROVED_OPS)}",
                error_code="unknown_operator",
            )
        if "left" not in node or "right" not in node:
            raise SpecValidationError(
                f"{path} compare node requires both 'left' and 'right'",
                error_code="missing_operand",
            )
        left_op = node["left"]
        right_op = node["right"]
        if not (isinstance(left_op, dict) and "feature" in left_op) and not (
            isinstance(right_op, dict) and "feature" in right_op
        ):
            raise SpecValidationError(
                f"{path} compare node must reference at least one observable feature",
                error_code="constant_only_comparison",
            )
        lb_left = _validate_operand(
            left_op,
            path=f"{path}.left",
            approved_features=approved_features,
            referenced_features=referenced_features,
            max_lookback_seen=max_lookback_seen,
        )
        lb_right = _validate_operand(
            right_op,
            path=f"{path}.right",
            approved_features=approved_features,
            referenced_features=referenced_features,
            max_lookback_seen=max_lookback_seen,
        )
        within_bars = node.get("within_bars", 1)
        if (
            isinstance(within_bars, bool)
            or not isinstance(within_bars, int)
            or within_bars < 1
            or within_bars > MAX_LOOKBACK
        ):
            raise SpecValidationError(
                f"{path}.within_bars must be in 1..{MAX_LOOKBACK}",
                error_code="invalid_within_bars",
            )
        combined_lb = max(lb_left, lb_right) + (int(within_bars) - 1)
        if combined_lb > MAX_LOOKBACK:
            raise SpecValidationError(
                f"{path} combined lookback {combined_lb} exceeds MAX_LOOKBACK={MAX_LOOKBACK}",
                error_code="lookback_exceeded",
            )
        max_lookback_seen.append(max(1, combined_lb))
        return combined_lb

    if kind in ("all", "any"):
        unknown = sorted(set(node.keys()) - {"type", "clauses"})
        if unknown:
            raise SpecValidationError(
                f"{path} {kind} node has unknown keys: {unknown}",
                error_code="unknown_node_key",
            )
        clauses = node.get("clauses")
        if not isinstance(clauses, list) or not clauses:
            raise SpecValidationError(
                f"{path}.clauses must be a non-empty list", error_code="empty_clauses"
            )
        if len(clauses) > MAX_CLAUSES_PER_COMPONENT:
            raise SpecValidationError(
                f"{path}.clauses count {len(clauses)} exceeds {MAX_CLAUSES_PER_COMPONENT}",
                error_code="too_many_clauses",
            )
        child_lbs = [
            _validate_condition_node(
                c,
                path=f"{path}.clauses[{idx}]",
                depth=depth + 1,
                approved_features=approved_features,
                referenced_features=referenced_features,
                max_lookback_seen=max_lookback_seen,
                node_counter=node_counter,
            )
            for idx, c in enumerate(clauses)
        ]
        return max(child_lbs, default=1)

    if kind == "sequence":
        unknown = sorted(set(node.keys()) - {"type", "max_span_bars", "steps"})
        if unknown:
            raise SpecValidationError(
                f"{path} sequence node has unknown keys: {unknown}",
                error_code="unknown_node_key",
            )
        steps = node.get("steps")
        max_span = node.get("max_span_bars", 5)
        if not isinstance(steps, list) or len(steps) < 2 or len(steps) > MAX_SEQUENCE_STEPS:
            raise SpecValidationError(
                f"{path}.steps length must be in 2..{MAX_SEQUENCE_STEPS}",
                error_code="invalid_sequence_steps",
            )
        if isinstance(max_span, bool) or not isinstance(max_span, int) or max_span < len(steps) or max_span > 20:
            raise SpecValidationError(
                f"{path}.max_span_bars must be in {len(steps)}..20",
                error_code="invalid_sequence_span",
            )
        step_lbs = [
            _validate_condition_node(
                step,
                path=f"{path}.steps[{idx}]",
                depth=depth + 1,
                approved_features=approved_features,
                referenced_features=referenced_features,
                max_lookback_seen=max_lookback_seen,
                node_counter=node_counter,
            )
            for idx, step in enumerate(steps)
        ]
        seq_lb = max(step_lbs, default=1) + (int(max_span) - 1)
        if seq_lb > MAX_LOOKBACK:
            raise SpecValidationError(
                f"{path} sequence lookback {seq_lb} exceeds MAX_LOOKBACK={MAX_LOOKBACK}",
                error_code="lookback_exceeded",
            )
        max_lookback_seen.append(max(1, seq_lb))
        return seq_lb

    raise SpecValidationError(
        f"{path}.type '{kind}' not in ('compare', 'all', 'any', 'sequence')",
        error_code="unknown_node_type",
    )


def invert_condition_node(node: dict[str, Any]) -> dict[str, Any]:
    """Invert directional comparison operators to build an opposing control condition."""
    if not isinstance(node, dict):
        return {}
    out = copy.deepcopy(node)
    kind = out.get("type", "compare")
    if kind == "compare":
        op = out.get("op")
        if op in INVERT_OP_MAP:
            out["op"] = INVERT_OP_MAP[op]
        return out
    if kind in ("all", "any") and isinstance(out.get("clauses"), list):
        out["clauses"] = [invert_condition_node(c) for c in out["clauses"]]
        return out
    if kind == "sequence" and isinstance(out.get("steps"), list):
        out["steps"] = [invert_condition_node(s) for s in out["steps"]]
        return out
    return out


def _canonicalize_operand(operand: Any) -> Any:
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return {"const": round(float(operand), 6)}
    if isinstance(operand, dict):
        if "const" in operand:
            return {"const": round(float(operand["const"]), 6)}
        out: dict[str, Any] = {
            "feature": str(operand.get("feature", "")),
            "transform": str(operand.get("transform", "raw")),
            "lag": int(operand.get("lag", 0)),
        }
        if out["transform"] in WINDOWED_TRANSFORMS and "window" in operand:
            out["window"] = int(operand["window"])
        if out["transform"] == "rolling_quantile" and "q" in operand:
            out["q"] = round(float(operand["q"]), 6)
        return out
    return operand


def _canonicalize_node(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    kind = node.get("type", "compare")
    if kind == "compare":
        return {
            "type": "compare",
            "left": _canonicalize_operand(node.get("left")),
            "op": str(node.get("op", "")),
            "right": _canonicalize_operand(node.get("right")),
            "within_bars": int(node.get("within_bars", 1)),
        }
    if kind in ("all", "any"):
        clauses = [_canonicalize_node(c) for c in (node.get("clauses") or [])]
        clauses_sorted = sorted(clauses, key=lambda item: json.dumps(item, sort_keys=True))
        return {"type": kind, "clauses": clauses_sorted}
    if kind == "sequence":
        return {
            "type": "sequence",
            "max_span_bars": int(node.get("max_span_bars", 5)),
            "steps": [_canonicalize_node(s) for s in (node.get("steps") or [])],
        }
    return node


def _extract_const(operand: Any) -> float | None:
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return float(operand)
    if isinstance(operand, dict) and "const" in operand:
        return float(operand["const"])
    return None


def _collect_conjunction_atoms(node: Any, out: list[dict[str, Any]]) -> None:
    if not isinstance(node, dict):
        return
    kind = node.get("type", "compare")
    if kind == "compare" and int(node.get("within_bars", 1)) == 1:
        out.append(node)
    elif kind == "all":
        for c in node.get("clauses") or []:
            _collect_conjunction_atoms(c, out)


def _check_pure_conjunction_contradictions(nodes: list[dict[str, Any]], *, arm_label: str) -> None:
    """Reject statically unsatisfiable bounds on the same feature operand in pure conjunctions."""
    atoms: list[dict[str, Any]] = []
    for n in nodes:
        _collect_conjunction_atoms(n, atoms)

    # Map operand key -> (lower_val, lower_strict, upper_val, upper_strict)
    bounds: dict[str, list[Any]] = {}
    flip = {">": "<", ">=": "<=", "<": ">", "<=": ">=", "==": "=="}

    for atom in atoms:
        left_c = _extract_const(atom.get("left"))
        right_c = _extract_const(atom.get("right"))
        op = str(atom.get("op", ""))
        if left_c is None and right_c is not None:
            key = json.dumps(_canonicalize_operand(atom["left"]), sort_keys=True)
            val = right_c
        elif right_c is None and left_c is not None:
            key = json.dumps(_canonicalize_operand(atom["right"]), sort_keys=True)
            val = left_c
            op = flip[op]
        else:
            continue

        lo, lo_strict, hi, hi_strict = bounds.get(key, [-math.inf, False, math.inf, False])
        if op == ">":
            if val > lo or (val == lo and not lo_strict):
                lo, lo_strict = val, True
        elif op == ">=":
            if val > lo:
                lo, lo_strict = val, False
        elif op == "<":
            if val < hi or (val == hi and not hi_strict):
                hi, hi_strict = val, True
        elif op == "<=":
            if val < hi:
                hi, hi_strict = val, False
        elif op == "==":
            if val > lo:
                lo, lo_strict = val, False
            if val < hi:
                hi, hi_strict = val, False

        if lo > hi or (lo == hi and (lo_strict or hi_strict)):
            raise SpecValidationError(
                f"Static logical contradiction in {arm_label}: unsatisfiable bounds on {key}",
                error_code="static_contradiction",
            )
        bounds[key] = [lo, lo_strict, hi, hi_strict]


def spec_fingerprint(spec: dict[str, Any]) -> str:
    """Canonical SHA-256 over executable 4-arm logic, ablation target, and exit policy."""
    exit_policy = dict(SHARED_DEFAULT_EXIT_POLICY)
    if isinstance(spec.get("exit_policy"), dict):
        exit_policy.update(spec["exit_policy"])
    ablation = spec.get("ablation") if isinstance(spec.get("ablation"), dict) else {}
    canonical = {
        "information_time": str(spec.get("information_time", REQUIRED_INFORMATION_TIME)),
        "context": _canonicalize_node(spec.get("context")),
        "setup": _canonicalize_node(spec.get("setup")),
        "trigger": _canonicalize_node(spec.get("trigger")),
        "reverse_trigger": _canonicalize_node(spec.get("reverse_trigger")),
        "ablation_remove": str(ablation.get("remove_component", "setup")),
        "exit_policy": exit_policy,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def summarize_condition_node(node: Any) -> str:
    """Deterministically render a condition AST into a readable formula string."""
    if not isinstance(node, dict):
        return "?"
    kind = node.get("type", "compare")
    if kind == "compare":
        left = _fmt_operand(node.get("left"))
        right = _fmt_operand(node.get("right"))
        expr = f"{left} {node.get('op', '?')} {right}"
        wb = int(node.get("within_bars", 1) or 1)
        return f"within({wb}b, {expr})" if wb > 1 else expr
    if kind == "all":
        return "(" + " AND ".join(summarize_condition_node(c) for c in (node.get("clauses") or [])) + ")"
    if kind == "any":
        return "(" + " OR ".join(summarize_condition_node(c) for c in (node.get("clauses") or [])) + ")"
    if kind == "sequence":
        steps = " -> ".join(summarize_condition_node(s) for s in (node.get("steps") or []))
        return f"seq[{node.get('max_span_bars', 5)}b]({steps})"
    return "?"


def _fmt_operand(op: Any) -> str:
    if isinstance(op, (int, float)) and not isinstance(op, bool):
        return f"{op:g}"
    if isinstance(op, dict):
        if "const" in op:
            return f"{op['const']:g}"
        feat = op.get("feature", "?")
        tf = op.get("transform", "raw")
        lag = int(op.get("lag", 0) or 0)
        win = op.get("window")
        q = op.get("q")
        base = feat if tf == "raw" else (f"{tf}({feat}, w={win}, q={q})" if q is not None else (f"{tf}({feat}, w={win})" if win else f"{tf}({feat})"))
        return f"{base}[t-{lag}]" if lag > 0 else base
    return str(op)


def validate_spec(
    spec: dict[str, Any],
    *,
    available_columns: Iterable[str] | None = None,
    approved_features: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate bounded grammar, causality, 4-arm falsifiability, and data availability."""
    if not isinstance(spec, dict):
        raise SpecValidationError("Spec must be a JSON object", error_code="invalid_spec")
    _check_no_forbidden_keys(spec)

    spec_id = str(spec.get("spec_id") or "").strip()
    if not _SPEC_ID_RE.match(spec_id):
        raise SpecValidationError(
            f"Invalid spec_id '{spec_id}' (must match ^[a-z][a-z0-9_]{{2,63}}$)",
            error_code="invalid_spec_id",
        )

    source = str(spec.get("source") or "ai").strip().lower()
    if source not in VALID_SOURCES:
        raise SpecValidationError(
            f"Invalid source '{source}'; must be one of {VALID_SOURCES}",
            error_code="invalid_source",
        )

    info_time = str(spec.get("information_time") or "").strip()
    if info_time != REQUIRED_INFORMATION_TIME:
        raise SpecValidationError(
            f"information_time must be '{REQUIRED_INFORMATION_TIME}'",
            error_code="invalid_information_time",
        )

    for text_field in ("title", "hypothesis", "prediction", "falsifier"):
        val = str(spec.get(text_field) or "").strip()
        if len(val) < 8:
            raise SpecValidationError(
                f"Required scientific field '{text_field}' must be at least 8 characters",
                error_code="missing_scientific_field",
            )

    ablation = spec.get("ablation")
    if not isinstance(ablation, dict) or ablation.get("remove_component") not in ("context", "setup"):
        raise SpecValidationError(
            "ablation.remove_component must be 'context' or 'setup'",
            error_code="invalid_ablation",
        )

    base_approved = (
        frozenset(approved_features)
        if approved_features is not None
        else (frozenset(CORE_OBSERVABLE_COLUMNS) | (frozenset(available_columns) if available_columns else frozenset()))
    )

    referenced: set[str] = set()
    max_lookback_seen: list[int] = [1]
    node_counter = [0]

    for comp in ("context", "setup", "trigger", "reverse_trigger"):
        if comp not in spec or not isinstance(spec[comp], dict):
            raise SpecValidationError(
                f"Missing required condition component '{comp}'",
                error_code="missing_component",
            )
        _validate_condition_node(
            spec[comp],
            path=comp,
            depth=1,
            approved_features=base_approved,
            referenced_features=referenced,
            max_lookback_seen=max_lookback_seen,
            node_counter=node_counter,
        )

    if _canonicalize_node(spec["trigger"]) == _canonicalize_node(spec["reverse_trigger"]):
        raise SpecValidationError(
            "reverse_trigger cannot be identical to trigger",
            error_code="identical_reverse_trigger",
        )

    _check_pure_conjunction_contradictions(
        [spec["context"], spec["setup"], spec["trigger"]], arm_label="full"
    )
    _check_pure_conjunction_contradictions(
        [spec["context"], spec["setup"], spec["reverse_trigger"]], arm_label="reverse_control"
    )

    if available_columns is not None:
        avail_set = set(available_columns)
        missing = sorted(referenced - avail_set)
        if missing:
            raise SpecValidationError(
                f"Spec references columns with zero dataset coverage: {missing}",
                error_code="missing_data_spec",
            )

    normalized = copy.deepcopy(spec)
    normalized["spec_id"] = spec_id
    normalized["source"] = source
    normalized["information_time"] = REQUIRED_INFORMATION_TIME
    normalized.setdefault("causal_disclaimer", CAUSAL_DISCLAIMER_DEFAULT)
    exit_pol = dict(SHARED_DEFAULT_EXIT_POLICY)
    if isinstance(normalized.get("exit_policy"), dict):
        exit_pol.update(normalized["exit_policy"])
    normalized["exit_policy"] = exit_pol
    normalized["fingerprint"] = spec_fingerprint(normalized)
    normalized["referenced_features"] = sorted(referenced)
    normalized["max_lookback_bars"] = max(max_lookback_seen)
    normalized["summary"] = {
        "context": summarize_condition_node(normalized["context"]),
        "setup": summarize_condition_node(normalized["setup"]),
        "trigger": summarize_condition_node(normalized["trigger"]),
        "reverse_trigger": summarize_condition_node(normalized["reverse_trigger"]),
    }
    return normalized


def evaluate_operand(df: pd.DataFrame, operand: Any) -> pd.Series:
    """Safely evaluate a validated operand without lookahead; missing values stay NaN."""
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return pd.Series(float(operand), index=df.index, dtype="float64")
    if isinstance(operand, dict) and "const" in operand:
        return pd.Series(float(operand["const"]), index=df.index, dtype="float64")

    feature = operand["feature"]
    if feature not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")

    s = pd.to_numeric(df[feature], errors="coerce").astype("float64")
    s = s.where(np.isfinite(s), np.nan)
    tf = operand.get("transform", "raw")
    lag = int(operand.get("lag", 0))
    window = operand.get("window")

    if tf == "raw":
        out = s
    elif tf == "lag":
        out = s
    elif tf == "sign":
        out = np.sign(s)
    elif tf == "diff":
        out = s.diff(int(window))
    elif tf == "pct_change":
        prev = s.shift(int(window))
        out = ((s / prev) - 1.0) * 100.0
        out = out.where(prev.abs() > 1e-12, np.nan)
    elif tf == "rolling_mean":
        out = s.rolling(int(window), min_periods=int(window)).mean()
    elif tf == "rolling_std":
        out = s.rolling(int(window), min_periods=int(window)).std(ddof=1)
    elif tf == "rolling_max":
        out = s.rolling(int(window), min_periods=int(window)).max()
    elif tf == "rolling_min":
        out = s.rolling(int(window), min_periods=int(window)).min()
    elif tf == "rolling_sum":
        out = s.rolling(int(window), min_periods=int(window)).sum()
    elif tf == "rolling_zscore":
        w = int(window)
        mu = s.rolling(w, min_periods=w).mean()
        sd = s.rolling(w, min_periods=w).std(ddof=1)
        out = (s - mu) / sd
        out = out.where(sd > 1e-12, np.nan)
    elif tf == "rolling_quantile":
        w = int(window)
        q = float(operand["q"])
        out = s.rolling(w, min_periods=w).quantile(q)
    elif tf == "ratio_to_rolling_mean":
        w = int(window)
        mu = s.rolling(w, min_periods=w).mean()
        out = s / mu
        out = out.where(mu.abs() > 1e-12, np.nan)
    else:
        raise SpecValidationError(f"Unsupported transform '{tf}'", error_code="unknown_transform")

    if lag > 0:
        out = out.shift(lag)
    out = out.astype("float64")
    return out.where(np.isfinite(out), np.nan)


def evaluate_condition_node(df: pd.DataFrame, node: dict[str, Any]) -> pd.Series:
    """Evaluate a condition node; any comparison involving NaN strictly returns False."""
    kind = node.get("type", "compare")
    if kind == "compare":
        left = evaluate_operand(df, node["left"])
        right = evaluate_operand(df, node["right"])
        valid = left.notna() & right.notna()
        op = node["op"]
        if op == ">":
            res = valid & (left > right)
        elif op == ">=":
            res = valid & (left >= right)
        elif op == "<":
            res = valid & (left < right)
        elif op == "<=":
            res = valid & (left <= right)
        elif op == "==":
            res = valid & (np.isclose(left, right, rtol=1e-7, atol=1e-9))
        else:
            raise SpecValidationError(f"Unknown operator '{op}'", error_code="unknown_operator")

        wb = int(node.get("within_bars", 1))
        if wb > 1:
            res = res.astype("float64").rolling(wb, min_periods=1).max().fillna(0.0) > 0.5
        return res.fillna(False).astype(bool)

    if kind == "all":
        res = pd.Series(True, index=df.index, dtype=bool)
        for clause in node["clauses"]:
            res &= evaluate_condition_node(df, clause)
        return res

    if kind == "any":
        res = pd.Series(False, index=df.index, dtype=bool)
        for clause in node["clauses"]:
            res |= evaluate_condition_node(df, clause)
        return res

    if kind == "sequence":
        steps = [evaluate_condition_node(df, s).to_numpy(dtype=bool) for s in node["steps"]]
        max_span = int(node.get("max_span_bars", 5))
        n = len(df)
        out = np.zeros(n, dtype=bool)
        k = len(steps)
        for i in range(n):
            if not steps[-1][i]:
                continue
            earliest = max(0, i - max_span + 1)
            # Match step 0 .. k-2 strictly in ascending bar order ending at i
            pos = i
            matched = True
            for step_idx in range(k - 2, -1, -1):
                found = -1
                for j in range(pos - 1, earliest - 1, -1):
                    if steps[step_idx][j]:
                        found = j
                        break
                if found == -1:
                    matched = False
                    break
                pos = found
            out[i] = matched
        return pd.Series(out, index=df.index, dtype=bool)

    raise SpecValidationError(f"Unknown node type '{kind}'", error_code="unknown_node_type")


def compute_condition_observability_mask(df: pd.DataFrame, node: dict[str, Any]) -> pd.Series:
    """Return True on rows where every operand required by `node` is finite (non-NaN)."""
    kind = node.get("type", "compare")
    if kind == "compare":
        left = evaluate_operand(df, node["left"])
        right = evaluate_operand(df, node["right"])
        mask = left.notna() & right.notna()
        wb = int(node.get("within_bars", 1))
        if wb > 1:
            mask = mask.astype("float64").rolling(wb, min_periods=wb).min().fillna(0.0) > 0.5
        return mask.astype(bool)
    if kind in ("all", "any"):
        mask = pd.Series(True, index=df.index, dtype=bool)
        for c in node["clauses"]:
            mask &= compute_condition_observability_mask(df, c)
        return mask
    if kind == "sequence":
        mask = pd.Series(True, index=df.index, dtype=bool)
        for s in node["steps"]:
            mask &= compute_condition_observability_mask(df, s)
        max_span = int(node.get("max_span_bars", 5))
        mask = mask.astype("float64").rolling(max_span, min_periods=max_span).min().fillna(0.0) > 0.5
        return mask.astype(bool)
    return pd.Series(False, index=df.index, dtype=bool)


def compute_spec_observability_mask(df: pd.DataFrame, spec: dict[str, Any]) -> pd.Series:
    """Shared observable universe across all four arms (context, setup, trigger, reverse_trigger)."""
    mask = pd.Series(True, index=df.index, dtype=bool)
    for comp in ("context", "setup", "trigger", "reverse_trigger"):
        mask &= compute_condition_observability_mask(df, spec[comp])
    mask &= df["open"].notna() & df["high"].notna() & df["low"].notna() & df["close"].notna()
    return mask.astype(bool)


def evaluate_spec_arms(df: pd.DataFrame, spec: dict[str, Any]) -> dict[str, pd.Series]:
    """Evaluate all four falsification arms on the exact same shared observable mask."""
    shared = compute_spec_observability_mask(df, spec)
    ctx = evaluate_condition_node(df, spec["context"]) & shared
    setup = evaluate_condition_node(df, spec["setup"]) & shared
    trig = evaluate_condition_node(df, spec["trigger"]) & shared
    rev = evaluate_condition_node(df, spec["reverse_trigger"]) & shared

    remove_comp = str((spec.get("ablation") or {}).get("remove_component", "setup"))
    if remove_comp == "context":
        ablation = setup & trig
    else:
        ablation = ctx & trig

    return {
        "full": (ctx & setup & trig),
        "baseline": ctx,
        "ablation": ablation,
        "reverse_control": (ctx & setup & rev),
        "shared_observable": shared,
    }


def extract_structural_tokens(spec: dict[str, Any]) -> set[str]:
    """Extract threshold-invariant structural AST tokens for novelty comparison."""
    tokens: set[str] = set()

    def _walk(node: Any, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        kind = node.get("type", "compare")
        tokens.add(f"{prefix}:kind:{kind}")
        if kind == "compare":
            for side in ("left", "right"):
                opnd = node.get(side)
                if isinstance(opnd, dict) and "feature" in opnd:
                    tokens.add(f"{prefix}:{opnd['feature']}:{opnd.get('transform', 'raw')}")
            tokens.add(f"{prefix}:op:{node.get('op')}")
        elif kind in ("all", "any"):
            for c in node.get("clauses") or []:
                _walk(c, prefix)
        elif kind == "sequence":
            for s in node.get("steps") or []:
                _walk(s, prefix)

    for comp in ("context", "setup", "trigger"):
        _walk(spec.get(comp), comp)
    return tokens


def build_default_seed_and_control_specs() -> list[dict[str, Any]]:
    """Return 3 diverse market-agnostic OHLCV seed hypotheses + 1 control benchmark."""
    raw_specs: list[dict[str, Any]] = [
        {
            "spec_id": "seed_vol_compression_breakout",
            "title": "Volatility Compression Above MA20 Followed by Intraday Expansion",
            "source": "seed",
            "information_time": REQUIRED_INFORMATION_TIME,
            "hypothesis": (
                "Assets trading near or above their 20-day moving average after a 5-day "
                "volatility compression that expand upward intraday exhibit positive drift."
            ),
            "prediction": (
                "Full mechanism outperforms context-only baseline, setup-ablated trigger, "
                "and downward intraday reverse control over a 10-day shared exit policy."
            ),
            "falsifier": (
                "Falsified if paired daily portfolio return difference vs baseline, ablation, "
                "or reverse_control fails to remain positive after costs."
            ),
            "baseline": {"description": "Close >= 0.98 * 20-day rolling mean"},
            "ablation": {
                "remove_component": "setup",
                "description": "Remove 5-day range compression filter to test trigger alone",
            },
            "reverse_control": {
                "description": "Same trend and compression, inverted to negative intraday return",
            },
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
                        "right": 2.4,
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
                        "right": 0.35,
                    },
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": ">=",
                        "right": 0.60,
                    },
                ],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "intraday_ret", "transform": "raw", "lag": 0},
                        "op": "<",
                        "right": -0.35,
                    },
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": "<=",
                        "right": 0.40,
                    },
                ],
            },
        },
        {
            "spec_id": "seed_pullback_reclaim_in_uptrend",
            "title": "Short-Term Pullback Reclaim Within 20-Day Uptrend",
            "source": "seed",
            "information_time": REQUIRED_INFORMATION_TIME,
            "hypothesis": (
                "Assets above their 20-day average that experience a brief 3-day pullback "
                "and reclaim strength with strong close position resume trend."
            ),
            "prediction": (
                "Full pullback-reclaim mechanism outperforms baseline trend, unconditioned "
                "reclaim, and failed-reclaim reverse control."
            ),
            "falsifier": (
                "Falsified if paired excess return over baseline, ablation, or reverse_control "
                "is non-positive or fails cost stress."
            ),
            "baseline": {"description": "Close >= 1.00 * 20-day rolling mean"},
            "ablation": {
                "remove_component": "setup",
                "description": "Remove prior pullback setup to test strong close alone",
            },
            "reverse_control": {
                "description": "Same uptrend and prior pullback, inverted to weak close breakdown",
            },
            "context": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close", "transform": "ratio_to_rolling_mean", "window": 20, "lag": 0},
                        "op": ">=",
                        "right": 1.0,
                    }
                ],
            },
            "setup": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "ret_1d", "transform": "rolling_sum", "window": 3, "lag": 1},
                        "op": "<",
                        "right": 0.0,
                    }
                ],
            },
            "trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "ret_1d", "transform": "raw", "lag": 0},
                        "op": ">",
                        "right": 0.4,
                    },
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": ">=",
                        "right": 0.65,
                    },
                ],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "ret_1d", "transform": "raw", "lag": 0},
                        "op": "<",
                        "right": -0.4,
                    },
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": "<=",
                        "right": 0.35,
                    },
                ],
            },
        },
        {
            "spec_id": "seed_volume_surge_mean_reversion",
            "title": "High-Volume Oversold Exhaustion Rebound",
            "source": "seed",
            "information_time": REQUIRED_INFORMATION_TIME,
            "hypothesis": (
                "Oversold assets trading below their 10-day average with elevated volume "
                "and high intraday recovery close signal short-term selling exhaustion."
            ),
            "prediction": (
                "Full exhaustion rebound beats generic oversold baseline, low-volume "
                "ablation, and weak-close continuation reverse control."
            ),
            "falsifier": (
                "Falsified if rebound fails to beat baseline, ablation, or reverse control "
                "after execution friction."
            ),
            "baseline": {"description": "Close <= 0.99 * 10-day rolling mean"},
            "ablation": {
                "remove_component": "setup",
                "description": "Remove elevated volume surge requirement",
            },
            "reverse_control": {
                "description": "Same oversold high-volume bar, inverted to closing near the low",
            },
            "context": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close", "transform": "ratio_to_rolling_mean", "window": 10, "lag": 0},
                        "op": "<=",
                        "right": 0.99,
                    }
                ],
            },
            "setup": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "volume", "transform": "ratio_to_rolling_mean", "window": 10, "lag": 0},
                        "op": ">=",
                        "right": 1.15,
                    }
                ],
            },
            "trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": ">=",
                        "right": 0.65,
                    }
                ],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close_pos_in_range", "transform": "raw", "lag": 0},
                        "op": "<=",
                        "right": 0.35,
                    }
                ],
            },
        },
        {
            "spec_id": "control_simple_trend_volume",
            "title": "Control Reference: Trend + Above-Average Volume Breakout",
            "source": "control",
            "information_time": REQUIRED_INFORMATION_TIME,
            "hypothesis": (
                "Standard reference benchmark combining 20-day trend with above-average "
                "volume expansion; used solely as a behavioral overlap control."
            ),
            "prediction": "Serves as fixed control benchmark for overlap and excess-return calibration.",
            "falsifier": "Control reference; never promoted as a novel discovery.",
            "baseline": {"description": "Close >= 1.00 * 20-day rolling mean"},
            "ablation": {
                "remove_component": "setup",
                "description": "Remove volume filter",
            },
            "reverse_control": {"description": "Negative daily return under same trend/volume"},
            "context": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "close", "transform": "ratio_to_rolling_mean", "window": 20, "lag": 0},
                        "op": ">=",
                        "right": 1.0,
                    }
                ],
            },
            "setup": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "volume", "transform": "ratio_to_rolling_mean", "window": 20, "lag": 0},
                        "op": ">=",
                        "right": 1.1,
                    }
                ],
            },
            "trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "ret_1d", "transform": "raw", "lag": 0},
                        "op": ">",
                        "right": 0.5,
                    }
                ],
            },
            "reverse_trigger": {
                "type": "all",
                "clauses": [
                    {
                        "type": "compare",
                        "left": {"feature": "ret_1d", "transform": "raw", "lag": 0},
                        "op": "<",
                        "right": -0.5,
                    }
                ],
            },
        },
    ]
    return [validate_spec(s) for s in raw_specs]
