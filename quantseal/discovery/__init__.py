"""Bounded autonomous strategy discovery engine."""
from __future__ import annotations

from quantseal.discovery.campaign import (
    CampaignBudget,
    CampaignConfig,
    CampaignError,
    CampaignImmutableMismatchError,
    compute_code_hash,
    compute_config_hash,
    run_or_resume_campaign,
)
from quantseal.discovery.evaluator import (
    ARMS,
    EvaluatorConfig,
    evaluate_batch_validation_once,
    evaluate_spec_development,
    moving_block_bootstrap_ci,
)
from quantseal.discovery.llm import LLMConfig, complete_text, sanitize_text_no_secrets
from quantseal.discovery.novelty import assess_candidate_novelty, build_reference_library
from quantseal.discovery.proposer import build_discovery_evidence_cards, propose_autonomous_specs
from quantseal.discovery.spec import (
    APPROVED_OPS,
    APPROVED_TRANSFORMS,
    MAX_AST_DEPTH,
    MAX_LOOKBACK,
    REQUIRED_INFORMATION_TIME,
    SHARED_DEFAULT_EXIT_POLICY,
    SpecValidationError,
    build_default_seed_and_control_specs,
    evaluate_condition_node,
    evaluate_operand,
    evaluate_spec_arms,
    extract_structural_tokens,
    spec_fingerprint,
    validate_spec,
)

__all__ = [
    "APPROVED_OPS",
    "APPROVED_TRANSFORMS",
    "ARMS",
    "CampaignBudget",
    "CampaignConfig",
    "CampaignError",
    "CampaignImmutableMismatchError",
    "EvaluatorConfig",
    "LLMConfig",
    "MAX_AST_DEPTH",
    "MAX_LOOKBACK",
    "REQUIRED_INFORMATION_TIME",
    "SHARED_DEFAULT_EXIT_POLICY",
    "SpecValidationError",
    "assess_candidate_novelty",
    "build_default_seed_and_control_specs",
    "build_discovery_evidence_cards",
    "build_reference_library",
    "complete_text",
    "compute_code_hash",
    "compute_config_hash",
    "evaluate_batch_validation_once",
    "evaluate_condition_node",
    "evaluate_operand",
    "evaluate_spec_arms",
    "evaluate_spec_development",
    "extract_structural_tokens",
    "moving_block_bootstrap_ci",
    "propose_autonomous_specs",
    "run_or_resume_campaign",
    "sanitize_text_no_secrets",
    "spec_fingerprint",
    "validate_spec",
]
