from __future__ import annotations


DELIVERY_QUESTION_MUTANT_CASES = (
    (
        "delivery-questions-hash-binding-disabled", "scripts/delivery_contract_bundle_validation.py",
        "or hashlib.sha256(path.read_bytes()).hexdigest() != declared_sha:",
        "or False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_requirement_questions_hash_drift_fails",
    ),
    (
        "delivery-questions-baseline-binding-disabled", "scripts/delivery_contract_bundle_validation.py",
        "issues = [] if expected == actual == traced else [Finding(",
        "issues = [] if True else [Finding(",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_requirement_questions_baseline_must_match_delivery_and_trace",
    ),
    (
        "delivery-questions-authoritative-validator-disabled", "scripts/delivery_contract_bundle_validation.py",
        "    issues.extend(Finding(item.severity, f\"questions-{item.code}\", item.message, source) for item in found)\n",
        "    issues.extend(())\n",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_requirement_questions_real_blocker_fails_delivery",
    ),
    (
        "delivery-questions-host-proof-forwarding-disabled", "scripts/delivery_contract_bundle_validation.py",
        "        if verifier is None else _test_only_validate_requirement_questions(\n",
        "        if True else _test_only_validate_requirement_questions(\n",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_answered_questions_require_bound_evidence_and_host_receipt",
    ),
)
