from __future__ import annotations


MODULE_LEASE_MUTANT_CASES = (
    (
        "module-lease-registry-binding-disabled",
        "scripts/local_controlled_module_lease_validation.py",
        'def activate_signed_module_lease(\n    payload: dict[str, object], registry_path: Path, now: datetime,\n) -> dict[str, object]:\n    require(payload.get("registry_path") == str(registry_path), "registry-path-mismatch")',
        'def activate_signed_module_lease(\n    payload: dict[str, object], registry_path: Path, now: datetime,\n) -> dict[str, object]:\n    require(True, "registry-path-mismatch")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_cross_registry_fails_before_creating_or_touching_other_registry",
    ),
    (
        "module-lease-candidate-binding-disabled",
        "scripts/local_controlled_module_lease_validation.py",
        'require(\n        payload.get("base_candidate_sha256") == _target_candidate(targets, "pre")\n        and payload.get("post_candidate_sha256") == _target_candidate(targets, "post"),\n        "candidate-binding-mismatch",\n    )',
        'require(True, "candidate-binding-mismatch")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_candidate_code_and_build_bindings_are_exact",
    ),
    (
        "module-lease-global-id-independence-disabled",
        "scripts/local_controlled_module_lease_registry.py",
        'for field in ("receipt_id", "nonce", "lease_id"):',
        'for field in ("receipt_id",):',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_receipt_nonce_and_lease_ids_are_independently_global",
    ),
    (
        "module-lease-active-conflict-disabled",
        "scripts/local_controlled_module_lease_registry.py",
        'require(not (same_module or same_identity), "active-lease-conflict")',
        'require(True, "active-lease-conflict")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_unique_active_and_cross_module_agent_run_reuse_fail",
    ),
    (
        "module-lease-role-deny-disabled",
        "scripts/local_controlled_module_lease_validation.py",
        'require(payload.get("role") in {"implementation", "module-maintainer"},\n            "invalid-module-lease")',
        'require(True, "invalid-module-lease")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_ttl_role_boolean_and_base64_are_strict",
    ),
    (
        "module-lease-ttl-maximum-relaxed",
        "scripts/local_controlled_module_lease_validation.py",
        'require(type(ttl) is int and 60 <= int(ttl) <= 900, "invalid-module-lease")',
        'require(type(ttl) is int and 60 <= int(ttl) <= 9000, "invalid-module-lease")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_ttl_role_boolean_and_base64_are_strict",
    ),
    (
        "module-lease-policy-recheck-disabled",
        "scripts/local_controlled_guarded_write.py",
        'require(hashlib.sha256(agents).hexdigest() == payload.get("policy_sha256"),\n            "policy-drift")',
        'require(True, "policy-drift")',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_guarded_apply_rechecks_drift_overreach_and_active_lease",
    ),
    (
        "module-write-partial-report-disabled",
        "scripts/local_controlled_guarded_write.py",
        'return {"status": "PARTIAL", "complete": False, "error": str(error)}',
        'return {"status": "APPLIED", "complete": True, "error": str(error)}',
        "scripts.test_local_controlled_module_lease_runtime.LocalControlledModuleLeaseRuntimeTests.test_registry_failure_after_file_write_reports_partial",
    ),
    (
        "bootstrap-v2-candidate-binding-disabled",
        "scripts/local_controlled_bootstrap_v2.py",
        'require(candidate == payload.get("bootstrap_candidate_sha256"), "candidate-drift")',
        'require(True, "candidate-drift")',
        "scripts.test_local_controlled_bootstrap_v2_runtime.BootstrapV2RuntimeTests.test_post_policy_authority_registration_and_candidate_are_bound",
    ),
    (
        "bootstrap-v2-owned-overlap-check-disabled",
        "scripts/local_controlled_bootstrap_v2.py",
        'require(all(not _paths_overlap(item, other) for other in existing),\n                "owned-path-overlap")',
        'require(True, "owned-path-overlap")',
        "scripts.test_local_controlled_bootstrap_v2_runtime.BootstrapV2RuntimeTests.test_overlap_symlink_and_missing_target_fail_before_replay",
    ),
)
