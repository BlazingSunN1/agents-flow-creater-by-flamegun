from __future__ import annotations


NATIVE_REVIEW_MUTANT_CASES = (
    (
        "multi-agent-candidate-hash-check-disabled",
        "scripts/validate_multi_agent_evidence.py",
        '        issues.append(Issue("error", "invalid-candidate-sha256", "candidate_sha256 必须是 64 位 SHA-256"))',
        "        pass",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_candidate_hash_is_required_and_strict_sha256",
    ),
    (
        "native-loop-reasoning-effort-check-disabled",
        "scripts/validate_native_review_loop.py",
        '    if raw.get("agent_reasoning_effort") != "xhigh":',
        "    if False:",
        "scripts.test_validate_native_review_loop.NativeReviewLoopValidatorTests.test_project_receipts_cannot_self_grant_host_trust",
    ),
    (
        "native-loop-checkpoint-chain-check-disabled",
        "scripts/validate_native_review_loop.py",
        "    issues.extend(_convert(validate_checkpoint_chain(data, root, verifier)))",
        "    pass",
        "scripts.test_validate_native_review_loop.NativeReviewLoopValidatorTests.test_checkpoint_chain_is_mandatory",
    ),
    (
        "native-loop-recovery-host-proof-check-disabled",
        "scripts/native_review_checkpoint_validation.py",
        "    if recovery_required is True:\n        _validate_recovery_receipt(checkpoint, wrapper, bundle, root, verifier, issues)",
        "    if False:\n        _validate_recovery_receipt(checkpoint, wrapper, bundle, root, verifier, issues)",
        "scripts.test_validate_native_review_loop.NativeReviewLoopValidatorTests.test_recovery_receipt_is_chain_bound_and_host_verified",
    ),
    (
        "independent-input-requirement-questions-hash-check-disabled",
        "scripts/multi_agent_input_validation.py",
        "    if path is None:\n        return [Issue(\"error\", \"stale-requirement-questions\", \"Requirement Questions locator/SHA 缺失或漂移\")]",
        "    if False:\n        return [Issue(\"error\", \"stale-requirement-questions\", \"Requirement Questions locator/SHA 缺失或漂移\")]",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_requirement_questions_hash_drift_fails_closed",
    ),
    (
        "independent-input-requirement-baseline-check-disabled",
        "scripts/multi_agent_input_validation.py",
        '            or questions.get("baseline_version") != evidence.get("baseline_version")',
        "            or False",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_requirement_questions_must_match_current_baseline",
    ),
    (
        "independent-input-canonical-questions-identity-check-disabled",
        "scripts/multi_agent_input_validation.py",
        '    if (data.get("requirement_questions_locator") != expected_locator\n            or str(data.get("requirement_questions_sha256", "")).casefold() != expected_sha256.casefold()):',
        "    if False:",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_same_baseline_alternate_questions_cannot_replace_canonical_input",
    ),
)
