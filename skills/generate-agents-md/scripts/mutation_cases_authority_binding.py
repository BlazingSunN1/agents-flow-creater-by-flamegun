from __future__ import annotations


AUTHORITY_BINDING_MUTANT_CASES = (
    (
        "context-authority-locator-required-check-disabled",
        "scripts/validate_context_manifest.py",
        '    "Authority matrix locator",\n    "Authority matrix SHA-256",\n',
        '    "Authority matrix SHA-256",\n',
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_authority_locator_and_sha_are_required",
    ),
    (
        "trace-authority-locator-required-check-disabled",
        "scripts/traceability_common.py",
        '    "Authority matrix locator", "Authority matrix SHA-256", "Code version",\n',
        '    "Authority matrix SHA-256", "Code version",\n',
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_authority_binding_is_required_and_exact",
    ),
    (
        "context-authority-locator-cache-binding-disabled",
        "scripts/context_cache_validation.py",
        '        metadata.get("Authority matrix locator", ""),\n',
        "",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_authority_binding_is_part_of_evidence_cache_key",
    ),
    (
        "context-authority-sha-cache-binding-disabled",
        "scripts/context_cache_validation.py",
        '        metadata.get("Authority matrix SHA-256", "").casefold(),\n',
        "",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_authority_binding_is_part_of_evidence_cache_key",
    ),
    (
        "authority-sha-drift-check-disabled",
        "scripts/authority_binding_validation.py",
        '        and metadata.get("Authority matrix SHA-256", "").strip().casefold() == AUTHORITY_MATRIX_SHA256\n',
        "        and True\n",
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_authority_binding_is_required_and_exact",
    ),
    (
        "authority-root-symlink-check-disabled",
        "scripts/authority_binding_validation.py",
        "    if agents.is_symlink():\n",
        "    if False:\n",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_root_authority_matrix_drift_and_symlink_fail_closed",
    ),
    (
        "authority-effective-hardlink-alias-check-disabled",
        "scripts/authority_binding_validation.py",
        "            if identity in identities:\n",
        "            if False:\n",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_effective_agents_hardlink_alias_fails_closed",
    ),
    (
        "reuse-context-authority-binding-disabled",
        "scripts/reuse_source_run_validation.py",
        '        "Authority matrix locator": AUTHORITY_MATRIX_LOCATOR,\n',
        "",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_compact_reuse_context_cannot_omit_or_drift_authority_binding",
    ),
)
