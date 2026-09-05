from __future__ import annotations


STRICT_MUTANT_CASES = (
    (
        "strict-json-duplicate-key-check-disabled", "scripts/strict_json.py",
        "if key in result:",
        "if False:",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_duplicate_or_unknown_command_fields_fail_closed",
    ),
    (
        "commands-exact-entry-fields-check-disabled", "scripts/validate_project_commands.py",
        "    if set(item) - {'result_kind'} != COMMAND_FIELDS:",
        "    if False:",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_duplicate_or_unknown_command_fields_fail_closed",
    ),
    (
        "swimlane-exact-transcript-fields-check-disabled", "scripts/validate_swimlane_evidence.py",
        "if set(data) != TRANSCRIPT_FIELDS:", "if False:",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_duplicate_or_unknown_browser_transcript_fields_fail_closed",
    ),
    (
        "frontend-exact-transcript-fields-check-disabled", "scripts/validate_frontend_evidence.py",
        "if set(data) != TRANSCRIPT_FIELDS:", "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_duplicate_or_unknown_browser_transcript_fields_fail_closed",
    ),
    (
        "multi-agent-top-level-type-check-disabled", "scripts/validate_multi_agent_evidence.py",
        'if any(type(data.get(field)) is not str or not data.get(field, "").strip() for field in identity_fields):',
        "if False:",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_top_level_identity_fields_must_be_nonempty_strings",
    ),
    (
        "frontend-browser-run-string-check-disabled", "scripts/validate_frontend_evidence.py",
        'run_id = raw_run_id.strip() if type(raw_run_id) is str else ""',
        'run_id = str(raw_run_id or "").strip()',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_and_e2e_run_identities_must_be_strings",
    ),
    (
        "frontend-verifier-run-string-check-disabled", "scripts/validate_frontend_evidence.py",
        'verifier_run_id = raw_verifier.strip() if type(raw_verifier) is str else ""',
        'verifier_run_id = str(raw_verifier or "").strip()',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_and_e2e_run_identities_must_be_strings",
    ),
    (
        "frontend-e2e-run-string-check-disabled", "scripts/validate_frontend_evidence.py",
        'if type(execution_run) is not str or not execution_run.strip():',
        'if not str(execution_run or "").strip():',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_and_e2e_run_identities_must_be_strings",
    ),
    (
        "strict-json-nonstandard-constant-check-disabled", "scripts/strict_json.py",
        "return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)",
        "return json.loads(text, object_pairs_hook=_unique_object)",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_actions_require_exact_order_target_and_standard_json",
    ),
    (
        "swimlane-top-identity-type-check-disabled", "scripts/validate_swimlane_evidence.py",
        'if any(type(data.get(field)) is not str or not data.get(field, "").strip() for field in identities):',
        "if False:",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_identity_and_actions_are_strictly_typed_and_ordered",
    ),
    (
        "swimlane-browser-run-string-check-disabled", "scripts/validate_swimlane_evidence.py",
        'run_id = raw_run_id.strip() if type(raw_run_id) is str else ""',
        'run_id = str(raw_run_id or "").strip()',
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_identity_and_actions_are_strictly_typed_and_ordered",
    ),
    (
        "frontend-exact-action-fields-check-disabled", "scripts/validate_frontend_evidence.py",
        "elif any(set(item) != ACTION_FIELDS for item in actions):",
        "elif False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_actions_require_exact_order_target_and_standard_json",
    ),
    (
        "swimlane-exact-action-fields-check-disabled", "scripts/validate_swimlane_evidence.py",
        "elif any(set(item) != ACTION_FIELDS for item in actions):",
        "elif False:",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_identity_and_actions_are_strictly_typed_and_ordered",
    ),
    (
        "command-provenance-string-type-check-disabled", "scripts/validate_project_commands.py",
        'if any(type(item.get(field)) is not str or not item.get(field, "").strip() for field in string_fields):',
        "if False:",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_command_provenance_fields_must_be_strings",
    ),
    (
        "multi-agent-artifact-path-string-check-disabled", "scripts/validate_multi_agent_evidence.py",
        'if type(path_value) is not str or type(hash_value) is not str:',
        "if False:",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_agent_artifact_path_must_be_a_json_string",
    ),
    (
        "frontend-artifact-path-string-check-disabled", "scripts/validate_frontend_evidence.py",
        'if type(value.get("path")) is not str or type(value.get("sha256")) is not str:',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_frontend_artifact_path_must_be_a_json_string",
    ),
    (
        "swimlane-artifact-path-string-check-disabled", "scripts/validate_swimlane_evidence.py",
        "if type(raw_path) is not str or type(raw_hash) is not str:",
        "if False:",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_artifact_path_must_be_a_json_string",
    ),
    (
        "frontend-action-semantic-binding-disabled", "scripts/validate_frontend_evidence.py",
        "elif not _ordered_actions(actions, evidence):", "elif False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_action_semantics_reject_reverse_unknown_and_unbound_targets",
    ),
    (
        "swimlane-action-semantic-binding-disabled", "scripts/validate_swimlane_evidence.py",
        "elif not _ordered_actions(actions, modules):", "elif False:",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_actions_reject_reverse_unknown_and_unbound_targets",
    ),
    (
        "swimlane-module-string-check-disabled", "scripts/validate_swimlane_evidence.py",
        'module = raw_module.strip() if type(raw_module) is str else ""',
        'module = str(raw_module or "").strip()',
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_diagram_module_and_code_evidence_must_be_strings",
    ),
    (
        "swimlane-code-evidence-string-check-disabled", "scripts/validate_swimlane_evidence.py",
        "and all(type(item) is str and bool(item.strip()) for item in code_evidence)",
        "and all(bool(str(item).strip()) for item in code_evidence)",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_swimlane_diagram_module_and_code_evidence_must_be_strings",
    ),
)
