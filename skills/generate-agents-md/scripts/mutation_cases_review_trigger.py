from __future__ import annotations


REVIEW_TRIGGER_MUTANT_CASES = (
    (
        "review-trigger-binding-disabled", "scripts/delivery_record_validation.py",
        "if (not _review_scope_valid(fields) or not _review_trigger_valid(fields)",
        "if (not _review_scope_valid(fields) or False",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_review_trigger_must_be_closure_candidate_or_bound_human_request",
    ),
    (
        "per-change-review-trigger-rejection-disabled", "scripts/agents_policy_validation.py",
        "if _has_forbidden_per_change_review_trigger(section):", "if False:",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_per_change_automated_review_trigger_fails",
    ),
)
