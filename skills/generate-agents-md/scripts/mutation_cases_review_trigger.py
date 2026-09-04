from __future__ import annotations


REVIEW_TRIGGER_MUTANT_CASES = (
    (
        "swimlane-record-gate-plan-binding-disabled", "scripts/delivery_record_validation.py",
        '    return "swimlane_evidence" in _planned_swimlane_gates(planned_command_ids)',
        "    return True",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_non_applicable_swimlane_does_not_require_evidence",
    ),
    (
        "swimlane-evidence-path-gate-plan-binding-disabled", "scripts/validate_delivery_bundle.py",
        '    if planned_command_ids is not None and "swimlane_evidence" not in planned_command_ids:\n        return []',
        "    if False:\n        return []",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_non_applicable_swimlane_does_not_require_evidence",
    ),
    (
        "swimlane-rerun-gate-plan-binding-disabled", "scripts/delivery_record_validation.py",
        "    return set(SWIMLANE_GATE_IDS & planned_command_ids)",
        '    return {"swimlane_evidence"}',
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_swimlane_freshness_gate_drives_review_without_evidence_path",
    ),
    (
        "review-trigger-binding-disabled", "scripts/delivery_record_validation.py",
        "if (not _review_scope_valid(fields, planned_command_ids) or not _review_trigger_valid(fields)",
        "if (not _review_scope_valid(fields, planned_command_ids) or False",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_review_trigger_must_be_closure_candidate_or_bound_human_request",
    ),
    (
        "per-change-review-trigger-rejection-disabled", "scripts/agents_policy_validation.py",
        "if _has_forbidden_per_change_review_trigger(section):", "if False:",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_per_change_automated_review_trigger_fails",
    ),
)
