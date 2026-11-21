"""Immutable Campaign Runner with SHA-256 sealing, single-shot validation, and contamination tracking.

Core guarantees:
1. Immutable Seal (`config_hash`, `data_hash`, `code_hash`):
   Every campaign locks all three hashes at creation time. Resuming with any
   altered config, dataset, or engine code raises `CampaignImmutableMismatchError`.
2. Single-Batch Frozen Validation (`validation_evaluated_once = True`):
   The validation partition can be unlocked and evaluated AT MOST ONCE in a
   campaign's lifetime. Subsequent calls return the sealed result immediately
   without re-proposing or re-testing.
3. Prior-Revision Contamination Tracking (`prior_campaign_id`):
   When creating a new revision referencing a parent campaign whose validation
   partition was already exposed, overlapping validation dates are permanently
   labeled `contaminated_development_from_prior_revision` — never fresh holdout.
4. Atomic persistence (`tempfile` + `os.fsync` + `os.replace`) and advisory
   file locking (`fcntl.flock`).
5. Honest 0-pass completion: a campaign with 0 passing strategies completes
   cleanly without relaxing gates or fabricating winners.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantseal.data.base import (
    LoadedDiscoveryDataset,
    LoaderConfig,
    load_frozen_dataset_snapshot,
    save_frozen_dataset_snapshot,
)
from quantseal.data.market_sources import load_dataset_by_source
from quantseal.discovery.evaluator import (
    EvaluatorConfig,
    evaluate_batch_validation_once,
    evaluate_spec_development,
)
from quantseal.discovery.llm import LLMConfig
from quantseal.discovery.novelty import assess_candidate_novelty, build_reference_library
from quantseal.discovery.proposer import build_discovery_evidence_cards, propose_autonomous_specs
from quantseal.discovery.spec import build_default_seed_and_control_specs, validate_spec

_CAMPAIGN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{1,63}$")


class CampaignError(RuntimeError):
    """Base campaign runtime error."""


class CampaignImmutableMismatchError(CampaignError):
    """Raised when resuming a campaign whose config_hash, data_hash, or code_hash changed."""


@dataclass(frozen=True)
class CampaignBudget:
    max_proposal_calls: int = 1
    max_ai_variants: int = 3
    max_total_variants: int = 8
    max_assets: int = 30
    max_days: int = 240
    warmup_days: int = 60
    walltime_seconds: float = 180.0

    def validate(self) -> None:
        if not (0 <= int(self.max_proposal_calls) <= 5):
            raise CampaignError("max_proposal_calls must be in 0..5")
        if not (0 <= int(self.max_ai_variants) <= 20):
            raise CampaignError("max_ai_variants must be in 0..20")
        if not (1 <= int(self.max_total_variants) <= 30):
            raise CampaignError("max_total_variants must be in 1..30")
        if not (1 <= int(self.max_assets) <= 200):
            raise CampaignError("max_assets must be in 1..200")
        if not (20 <= int(self.max_days) <= 2000):
            raise CampaignError("max_days must be in 20..2000")
        if not (10 <= int(self.warmup_days) <= 250):
            raise CampaignError("warmup_days must be in 10..250")
        if not (1.0 <= float(self.walltime_seconds) <= 1800.0):
            raise CampaignError("walltime_seconds must be in [1, 1800]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_proposal_calls": int(self.max_proposal_calls),
            "max_ai_variants": int(self.max_ai_variants),
            "max_total_variants": int(self.max_total_variants),
            "max_assets": int(self.max_assets),
            "max_days": int(self.max_days),
            "warmup_days": int(self.warmup_days),
            "walltime_seconds": float(self.walltime_seconds),
        }


@dataclass(frozen=True)
class CampaignConfig:
    campaign_id: str
    budget: CampaignBudget = field(default_factory=CampaignBudget)
    loader: LoaderConfig | None = None
    evaluator: EvaluatorConfig = field(default_factory=EvaluatorConfig)
    prior_campaign_id: str | None = None
    custom_seed_specs: list[dict[str, Any]] | None = None
    development_only: bool = False

    def resolved_loader(self) -> LoaderConfig:
        if self.loader is not None:
            return self.loader
        return LoaderConfig(
            source="demo",
            max_assets=self.budget.max_assets,
            max_days=self.budget.max_days,
            warmup_days=self.budget.warmup_days,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "prior_campaign_id": self.prior_campaign_id,
            "development_only": bool(self.development_only),
            "budget": self.budget.to_dict(),
            "loader": self.resolved_loader().to_dict(),
            "evaluator": self.evaluator.to_dict(),
            "custom_seed_specs": (
                json.loads(json.dumps(self.custom_seed_specs, sort_keys=True))
                if self.custom_seed_specs is not None
                else None
            ),
        }


def compute_code_hash() -> str:
    """Compute SHA-256 fingerprint across all core engine & discovery source files."""
    disc_dir = Path(__file__).resolve().parent
    core_dir = disc_dir.parent / "core"
    hasher = hashlib.sha256()
    for folder, names in (
        (disc_dir, ("spec.py", "evaluator.py", "novelty.py", "proposer.py", "campaign.py")),
        (core_dir, ("costs.py", "split.py", "gates.py", "evalue.py")),
    ):
        for fname in sorted(names):
            fp = folder / fname
            if fp.exists():
                hasher.update(f"{folder.name}/{fname}".encode())
                hasher.update(fp.read_bytes())
    return hasher.hexdigest()[:16]


def compute_config_hash(config: CampaignConfig) -> str:
    payload = json.dumps(config.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _validate_campaign_id(cid: str) -> str:
    clean = str(cid or "").strip()
    if not _CAMPAIGN_ID_RE.match(clean):
        raise CampaignError(
            f"Invalid campaign_id '{clean}' (must be 2..64 chars: alphanumeric, _, -, .)"
        )
    return clean


@contextmanager
def _campaign_lock(campaign_dir: Path):
    campaign_dir.mkdir(parents=True, exist_ok=True)
    lock_path = campaign_dir / ".lock"
    with open(lock_path, "w", encoding="utf-8") as lf:
        try:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CampaignError(f"Campaign '{campaign_dir.name}' is currently locked") from exc
        try:
            yield
        finally:
            try:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def _atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CampaignError(f"Corrupted JSON state file: {path.name}")
    return data


def _synthesize_outcome(
    spec: dict[str, Any],
    dev_eval: dict[str, Any],
    novelty_eval: dict[str, Any],
    val_eval: dict[str, Any] | None,
    *,
    validation_contaminated: bool,
    development_only: bool,
) -> dict[str, Any]:
    source = str(spec.get("source") or "seed")
    dev_v = str(dev_eval.get("verdict") or "inconclusive")
    nov_state = str(novelty_eval.get("state") or "inconclusive")
    val_v = str((val_eval or {}).get("verdict") or "not_evaluated")

    if source == "control":
        return {
            "final_status": "control_reference",
            "qualified_candidate": False,
            "reason": "Fixed control reference used solely for overlap calibration.",
            "next_step": "Keep as benchmark reference; never promoted.",
        }
    if dev_v == "inconclusive":
        return {
            "final_status": "inconclusive",
            "qualified_candidate": False,
            "reason": str(dev_eval.get("reason") or "Sparse sample on discovery."),
            "next_step": "Gather more observations before making a decision.",
        }
    if dev_v != "passed_development":
        return {
            "final_status": "rejected_in_development",
            "qualified_candidate": False,
            "reason": str(dev_eval.get("reason") or "Failed discovery falsification arms."),
            "next_step": "Archive failure memory; excluded from validation.",
        }
    if nov_state == "duplicate_existing":
        return {
            "final_status": "rejected_duplicate",
            "qualified_candidate": False,
            "reason": str(novelty_eval.get("explanation")),
            "next_step": "Duplicate of existing reference; excluded from validation.",
        }
    if development_only:
        return {
            "final_status": "development_passed_pending_validation",
            "qualified_candidate": False,
            "reason": "Passed discovery 4-arm falsification; awaiting single-shot frozen validation.",
            "next_step": "Inspect discovery results, then trigger single-shot validation once.",
        }
    if validation_contaminated:
        return {
            "final_status": "contaminated_development_from_prior_revision",
            "qualified_candidate": False,
            "reason": (
                "Parent campaign already revealed this validation window; "
                "results cannot be claimed as clean out-of-sample validation."
            ),
            "next_step": "Wait for new forward calendar dates or enroll in shadow ladder.",
        }
    if val_v == "passed_historical_validation":
        return {
            "final_status": "qualified_for_shadow",
            "qualified_candidate": True,
            "reason": str((val_eval or {}).get("reason")),
            "next_step": "Enroll into forward-only Shadow Ladder to accumulate anytime-valid E-value proof.",
        }
    if val_v == "inconclusive":
        return {
            "final_status": "validation_inconclusive",
            "qualified_candidate": False,
            "reason": str((val_eval or {}).get("reason")),
            "next_step": "Validation sample too sparse; do not promote.",
        }
    return {
        "final_status": "rejected_in_validation",
        "qualified_candidate": False,
        "reason": str((val_eval or {}).get("reason") or "Failed frozen validation."),
        "next_step": "Falsified on frozen validation; do not re-tune on this window.",
    }


def _check_prior_contamination(
    storage_root: Path,
    prior_campaign_id: str | None,
    dataset: LoadedDiscoveryDataset,
) -> tuple[bool, list[dict[str, Any]]]:
    """Detect whether prior campaign already revealed overlapping validation dates."""
    if not prior_campaign_id:
        return False, []
    prior_state_path = storage_root / prior_campaign_id / "state.json"
    if not prior_state_path.exists():
        raise CampaignError(f"Prior campaign '{prior_campaign_id}' not found in {storage_root}")

    prior = _read_json(prior_state_path)
    prior_dev_feedback: list[dict[str, Any]] = []
    for exp in prior.get("experiments") or []:
        dev = exp.get("development") or {}
        prior_dev_feedback.append(
            {
                "spec_id": exp.get("spec_id"),
                "dev_verdict": dev.get("verdict"),
                "dev_reason": dev.get("reason"),
            }
        )

    contaminated = False
    if prior.get("validation_evaluated_once"):
        p_dates = prior.get("partitions") or {}
        p_val_start = p_dates.get("validation_start")
        p_val_end = p_dates.get("validation_end")
        if p_val_start and p_val_end:
            ps = dt.date.fromisoformat(p_val_start)
            pe = dt.date.fromisoformat(p_val_end)
            # Any overlap with previously revealed validation dates contaminates holdout
            if not (dataset.validation_end < ps or dataset.validation_start > pe):
                contaminated = True
    return contaminated, prior_dev_feedback


def run_or_resume_campaign(
    config: CampaignConfig,
    *,
    storage_root: str | Path,
    llm_config: LLMConfig | None = None,
    dataset_override: LoadedDiscoveryDataset | None = None,
    llm_caller: Callable[[str, LLMConfig], dict[str, Any]] | None = None,
    external_mcp_evidence: list[dict[str, Any]] | None = None,
    unlock_validation: bool = False,
) -> dict[str, Any]:
    """Run a new immutable campaign, resume an existing one, or execute single-shot validation."""
    cid = _validate_campaign_id(config.campaign_id)
    config.budget.validate()
    root = Path(storage_root).resolve()
    cdir = root / cid
    state_path = cdir / "state.json"
    snap_path = cdir / "frozen_dataset.json.gz"

    code_hash = compute_code_hash()
    config_hash = compute_config_hash(config)

    with _campaign_lock(cdir):
        if state_path.exists():
            state = _read_json(state_path)
            if state.get("code_hash") != code_hash:
                raise CampaignImmutableMismatchError(
                    f"code_hash mismatch on resume: sealed={state.get('code_hash')}, current={code_hash}"
                )
            # Allow explicit unlock_validation transition from a development_only campaign
            if not unlock_validation and state.get("config_hash") != config_hash:
                raise CampaignImmutableMismatchError(
                    f"config_hash mismatch on resume: sealed={state.get('config_hash')}, current={config_hash}"
                )
            if state.get("validation_evaluated_once"):
                # Single-batch frozen validation seal: never re-propose or re-evaluate
                return state
            if not unlock_validation and state.get("status") == "completed_development_only":
                return state

            if not snap_path.exists():
                raise CampaignError("Frozen dataset snapshot missing; refusing to reload fresh data")
            dataset = load_frozen_dataset_snapshot(snap_path)
            if dataset.data_hash != state.get("data_hash"):
                raise CampaignImmutableMismatchError(
                    f"data_hash mismatch: sealed={state.get('data_hash')}, snapshot={dataset.data_hash}"
                )
            # Execute the single-shot frozen validation on dev-eligible specs
            return _execute_single_shot_validation(
                state=state,
                dataset=dataset,
                evaluator_cfg=config.evaluator,
                state_path=state_path,
            )

        # Fresh campaign creation
        started_mono = time.monotonic()
        dataset = dataset_override or load_dataset_by_source(config.resolved_loader())
        save_frozen_dataset_snapshot(dataset, snap_path)

        contaminated, prior_feedback = _check_prior_contamination(
            root, config.prior_campaign_id, dataset
        )

        # 1. Seed & control specs
        raw_seeds = (
            [validate_spec(s, available_columns=dataset.available_columns) for s in config.custom_seed_specs]
            if config.custom_seed_specs
            else [
                validate_spec(s, available_columns=dataset.available_columns)
                for s in build_default_seed_and_control_specs()
            ]
        )

        specs: list[dict[str, Any]] = list(raw_seeds[: config.budget.max_total_variants])
        seen_ids = [s["spec_id"] for s in specs]
        seen_fps = {s["fingerprint"] for s in specs}

        # 2. Discovery-only evidence cards & optional BYOK LLM proposal (with pre-call reservation)
        evidence_cards = build_discovery_evidence_cards(
            dataset,
            prior_dev_summary=prior_feedback or None,
            external_mcp_evidence=external_mcp_evidence or None,
        )
        proposal_audits: list[dict[str, Any]] = []
        reservations: list[dict[str, Any]] = []
        eff_llm = llm_config or LLMConfig(provider="none")

        state: dict[str, Any] = {
            "campaign_id": cid,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "updated_at": dt.datetime.now(dt.UTC).isoformat(),
            "status": "running",
            "config_hash": config_hash,
            "data_hash": dataset.data_hash,
            "code_hash": code_hash,
            "prior_campaign_id": config.prior_campaign_id,
            "validation_holdout_contaminated": contaminated,
            "contamination_label": (
                "contaminated_development_from_prior_revision"
                if contaminated
                else "single_shot_historical_validation"
            ),
            "validation_evaluated_once": False,
            "development_only": bool(config.development_only),
            "config": config.to_dict(),
            "source_meta": dataset.source_meta,
            "partitions": {
                "warmup_end": dataset.warmup_end.isoformat(),
                "discovery_start": dataset.discovery_start.isoformat(),
                "discovery_end": dataset.discovery_end.isoformat(),
                "validation_start": dataset.validation_start.isoformat(),
                "validation_end": dataset.validation_end.isoformat(),
                "sealed_start": dataset.sealed_start.isoformat() if dataset.sealed_start else None,
                "sealed_end": dataset.sealed_end.isoformat() if dataset.sealed_end else None,
            },
            "coverage_report": dataset.coverage_report,
            "evidence_cards": evidence_cards,
            "proposal_reservations": reservations,
            "proposal_audits": proposal_audits,
            "experiments": [],
            "summary": {},
        }
        _atomic_write_json(state_path, state)

        remaining_slots = max(0, config.budget.max_total_variants - len(specs))
        ai_cap = min(config.budget.max_ai_variants, remaining_slots)
        if config.budget.max_proposal_calls > 0 and ai_cap > 0 and eff_llm.is_configured():
            def _reserve(rec: dict[str, Any]) -> None:
                reservations.append(rec)
                state["proposal_reservations"] = reservations
                state["updated_at"] = dt.datetime.now(dt.UTC).isoformat()
                _atomic_write_json(state_path, state)

            ai_specs, p_audit = propose_autonomous_specs(
                evidence_cards,
                llm_config=eff_llm,
                available_columns=dataset.available_columns,
                existing_spec_ids=seen_ids,
                existing_fingerprints=seen_fps,
                max_variants=ai_cap,
                on_before_call=_reserve,
                llm_caller=llm_caller,
            )
            proposal_audits.append(p_audit)
            specs.extend(ai_specs)
        else:
            proposal_audits.append(
                {
                    "called": False,
                    "provider": eff_llm.provider,
                    "status": "skipped_unconfigured" if not eff_llm.is_configured() else "skipped_budget",
                    "accepted_count": 0,
                    "rejected": [],
                }
            )

        # 3. Discovery evaluation + zero-exec novelty audit
        control_refs = [s for s in specs if s.get("source") == "control"]
        ref_library = build_reference_library(dataset, control_refs or specs[:1])

        experiments: list[dict[str, Any]] = []
        for spec in specs:
            if (time.monotonic() - started_mono) > config.budget.walltime_seconds:
                break
            dev_eval = evaluate_spec_development(dataset, spec, config.evaluator)
            nov_eval = assess_candidate_novelty(dataset, spec, ref_library, dev_eval=dev_eval)
            outcome = _synthesize_outcome(
                spec,
                dev_eval,
                nov_eval,
                None,
                validation_contaminated=contaminated,
                development_only=True,
            )
            experiments.append(
                {
                    "spec_id": spec["spec_id"],
                    "title": spec["title"],
                    "source": spec["source"],
                    "fingerprint": spec["fingerprint"],
                    "spec": spec,
                    "development": dev_eval,
                    "novelty": nov_eval,
                    "validation": None,
                    "outcome": outcome,
                }
            )

        state["experiments"] = experiments
        state["proposal_audits"] = proposal_audits
        state["updated_at"] = dt.datetime.now(dt.UTC).isoformat()

        if config.development_only:
            state["status"] = "completed_development_only"
            state["summary"] = _build_summary(state)
            _atomic_write_json(state_path, state)
            return state

        return _execute_single_shot_validation(
            state=state,
            dataset=dataset,
            evaluator_cfg=config.evaluator,
            state_path=state_path,
        )


def _execute_single_shot_validation(
    *,
    state: dict[str, Any],
    dataset: LoadedDiscoveryDataset,
    evaluator_cfg: EvaluatorConfig,
    state_path: Path,
) -> dict[str, Any]:
    """Claim single-shot validation atomically BEFORE evaluating so crashes cannot re-peek."""
    state["validation_evaluated_once"] = True
    state["validation_claimed_at"] = dt.datetime.now(dt.UTC).isoformat()
    state["development_only"] = False
    _atomic_write_json(state_path, state)

    contaminated = bool(state.get("validation_holdout_contaminated"))
    eligible_specs = [
        exp["spec"]
        for exp in state["experiments"]
        if exp["source"] != "control"
        and (exp.get("development") or {}).get("verdict") == "passed_development"
        and (exp.get("novelty") or {}).get("state") != "duplicate_existing"
    ]

    val_results = evaluate_batch_validation_once(dataset, eligible_specs, evaluator_cfg)

    for exp in state["experiments"]:
        sid = exp["spec_id"]
        val_eval = val_results.get(sid)
        exp["validation"] = val_eval
        exp["outcome"] = _synthesize_outcome(
            exp["spec"],
            exp["development"],
            exp["novelty"],
            val_eval,
            validation_contaminated=contaminated,
            development_only=False,
        )

    state["status"] = "completed_sealed"
    state["updated_at"] = dt.datetime.now(dt.UTC).isoformat()
    state["summary"] = _build_summary(state)
    _atomic_write_json(state_path, state)
    return state


def _build_summary(state: dict[str, Any]) -> dict[str, Any]:
    exps = state.get("experiments") or []
    dev_passed = sum(1 for e in exps if (e.get("development") or {}).get("verdict") == "passed_development")
    val_evaluated = sum(1 for e in exps if e.get("validation") is not None)
    qualified = sum(1 for e in exps if (e.get("outcome") or {}).get("qualified_candidate"))
    rejected = sum(
        1
        for e in exps
        if str((e.get("outcome") or {}).get("final_status", "")).startswith("rejected")
    )
    return {
        "total_candidates": len(exps),
        "dev_passed": dev_passed,
        "validation_evaluated": val_evaluated,
        "qualified_for_shadow": qualified,
        "rejected": rejected,
        "zero_pass_honest_completion": qualified == 0 and bool(state.get("validation_evaluated_once")),
    }
