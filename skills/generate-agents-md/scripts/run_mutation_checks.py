from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mutation_cases_records import ADDITIONAL_MUTANT_CASES
from mutation_cases_module_closure import MODULE_CLOSURE_MUTANT_CASES
from mutation_cases_review_fixes import REVIEW_FIX_MUTANT_CASES
from mutation_cases_review_trigger import REVIEW_TRIGGER_MUTANT_CASES
from mutation_cases_strict import STRICT_MUTANT_CASES
from mutation_cases_stability import STABILITY_MUTANT_CASES
from mutation_cases_authority_binding import AUTHORITY_BINDING_MUTANT_CASES
from mutation_cases_native_review import NATIVE_REVIEW_MUTANT_CASES
from mutation_cases_requirement_questions import REQUIREMENT_QUESTION_MUTANT_CASES
from mutation_cases_delivery_questions import DELIVERY_QUESTION_MUTANT_CASES
from mutation_cases_delivery_contract_bundle import DELIVERY_CONTRACT_BUNDLE_MUTANT_CASES
from mutation_cases_write_authority import WRITE_AUTHORITY_MUTANT_CASES
from mutation_cases_local_trust import LOCAL_TRUST_MUTANT_CASES
from mutation_cases_module_lease import MODULE_LEASE_MUTANT_CASES


SKILL_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutant:
    name: str
    relative_path: str
    original: str
    replacement: str
    test: str


CORE_MUTANTS = (
    Mutant(
        "machine-policy-comparison-disabled",
        "scripts/agents_policy_validation.py",
        "if actual != expected:\n            issues.append(\n                Issue(\n                    \"error\",\n                    \"invalid-machine-policy\",",
        "if False:\n            issues.append(\n                Issue(\n                    \"error\",\n                    \"invalid-machine-policy\",",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_machine_policy_is_required_and_fail_closed",
    ),
    Mutant(
        "machine-policy-unknown-key-check-disabled",
        "scripts/agents_policy_validation.py",
        "for key in sorted(set(values) - set(REQUIRED_MACHINE_POLICY)):",
        "for key in ():",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_machine_policy_rejects_unknown_override_keys",
    ),
    Mutant(
        "machine-policy-yaml-entry-parser-narrowed",
        "scripts/agents_policy_validation.py",
        'match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*)\\s*:\\s*([A-Za-z0-9_./#-]+)", stripped)',
        'match = re.fullmatch(r"([a-z][a-z0-9_]*)\\s*:\\s*([a-z0-9_]+)", stripped)',
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_machine_policy_rejects_unknown_override_keys",
    ),
    Mutant(
        "malformed-row-check-disabled",
        "scripts/traceability_parsing.py",
        "if len(values) != len(headers):",
        "if False:",
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_malformed_trace_row_fails_closed",
    ),
    Mutant(
        "trace-nul-byte-check-disabled",
        "scripts/validate_traceability.py",
        'if b"\\x00" in payload:',
        "if False:",
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_real_nul_byte_fails_closed",
    ),
    Mutant(
        "trace-cli-parser-disabled",
        "scripts/validate_traceability.py",
        "def build_parser() -> argparse.ArgumentParser:",
        "def disabled_build_parser() -> argparse.ArgumentParser:",
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_cli_help_is_executable",
    ),
    Mutant(
        "context-fingerprint-comparison-disabled",
        "scripts/validate_context_manifest.py",
        "if SHA256_RE.fullmatch(metadata[field]) and metadata[field].casefold() != actual:",
        "if False:",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_changed_code_invalidates_code_fingerprint",
    ),
    Mutant(
        "bundle-binding-comparison-disabled",
        "scripts/validate_delivery_bundle.py",
        "if trace_value and context_value and trace_value != context_value:",
        "if False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_cross_artifact_code_version_drift_fails",
    ),
    Mutant(
        "bundle-missing-command-manifest-guard-disabled",
        "scripts/validate_delivery_bundle.py",
        "manifest_payload = command_manifest_path.read_bytes()",
        "manifest_payload = b\"\" if not command_manifest_path.exists() else command_manifest_path.read_bytes()",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_missing_command_manifest_returns_structured_errors",
    ),
    Mutant(
        "bundle-plan-missing-check-disabled",
        "scripts/delivery_record_io.py",
        "if candidate.is_absolute() or _has_symlink_component(resolved_root, candidate) or not resolved.is_file():",
        "if candidate.is_absolute() or _has_symlink_component(resolved_root, candidate):",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_missing_development_plan_blocks_delivery",
    ),
    Mutant(
        "bundle-progress-stale-check-disabled",
        "scripts/delivery_record_io.py",
        'return [Issue("error", f"bundle-{label}-stale", "记录未绑定当前基线、run、代码或模块", raw_path or "")]',
        "return []",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_stale_progress_record_blocks_delivery",
    ),
    Mutant(
        "command-declaration-binding-disabled",
        "scripts/validate_project_commands.py",
        "if declared_argv != argv or source_command not in source.read_text(encoding=\"utf-8\", errors=\"replace\"):",
        "if False:",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_argv_must_equal_complete_declared_command",
    ),
    Mutant(
        "multi-agent-extra-role-check-disabled",
        "scripts/validate_multi_agent_evidence.py",
        "for role in set(role_map) - required:\n        issues.append(Issue(\"error\", \"nonapplicable-agent-role\", f\"当前阶段和风险不应启动独立 Agent：{role}\"))",
        "for role in ():\n        issues.append(Issue(\"error\", \"nonapplicable-agent-role\", f\"当前阶段和风险不应启动独立 Agent：{role}\"))",
        "scripts.test_validate_multi_agent_evidence.MultiAgentEvidenceValidatorTests.test_nonapplicable_extra_role_is_rejected",
    ),
    Mutant(
        "frontend-containment-check-disabled",
        "scripts/validate_frontend_evidence.py",
        "resolved.relative_to(root)",
        "root.relative_to(root)",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_symlinked_evidence_cannot_escape_project",
    ),
    Mutant(
        "delivery-frontend-applicability-disabled",
        "scripts/validate_delivery_bundle.py",
        "if trace_applicable and not command_applicable:",
        "if False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_ui_trace_cannot_disable_frontend_applicability",
    ),
    Mutant(
        "frontend-report-semantic-check-disabled",
        "scripts/validate_frontend_evidence.py",
        'if counts != (value.get("passed"), value.get("failed")):',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_e2e_report_content_must_match_summary",
    ),
    Mutant(
        "combined-inline-code-check-disabled",
        "scripts/validate_project_commands.py",
        'any(value == "-c" or value.startswith("-c") for value in argv[1:])',
        'any(value == "-c" for value in argv[1:])',
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_combined_inline_code_argument_is_rejected",
    ),
    Mutant(
        "frontend-real-runner-check-weakened",
        "scripts/validate_frontend_evidence.py",
        'valid_runner = _runner_framework_for_argv(argv) is not None',
        'valid_runner = any("playwright" in str(token) or "cypress" in str(token) for token in argv)',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_keyword_only_command_cannot_masquerade_as_e2e_runner",
    ),
    Mutant(
        "agents-workset-fingerprint-comparison-disabled",
        "scripts/validate_context_manifest.py",
        'if SHA256_RE.fullmatch(metadata[field]) and metadata[field].casefold() != actual:',
        'if field != "Effective AGENTS fingerprint" and SHA256_RE.fullmatch(metadata[field]) and metadata[field].casefold() != actual:',
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_changed_agents_invalidates_agents_fingerprint",
    ),
    Mutant(
        "bundle-agents-binding-disabled",
        "scripts/validate_delivery_bundle.py",
        "if expected_agents and expected_agents != actual_agents:",
        "if False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_agents_content_drift_breaks_bundle_binding",
    ),
    Mutant(
        "atomic-root-identity-check-disabled",
        "scripts/update_project_record.py",
        "    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)\n    try:\n        opened_root = os.fstat(root_fd)\n        if (opened_root.st_dev, opened_root.st_ino) != (expected_root.st_dev, expected_root.st_ino):",
        "    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)\n    try:\n        opened_root = os.fstat(root_fd)\n        if False:",
        "scripts.test_update_project_record.AtomicProjectRecordTests.test_project_root_swap_cannot_redirect_write_outside_project",
    ),
    Mutant(
        "effective-agents-chain-check-disabled",
        "scripts/validate_context_manifest.py",
        "if declared_agents != discovered_agents:",
        "if False:",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_new_scoped_agents_invalidates_declared_effective_chain",
    ),
    Mutant(
        "swimlane-delivery-gate-disabled",
        "scripts/validate_delivery_bundle.py",
        'return [Issue("error", "missing-swimlane-evidence", "代码交付缺少系统/模块泳道同步证据", "delivery-bundle")]',
        "return []",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_missing_swimlane_evidence_blocks_delivery",
    ),
    Mutant(
        "screenshot-structural-validation-disabled",
        "scripts/validate_frontend_evidence.py",
        'if label.endswith("screenshot") and not _is_structurally_valid_image(resolved.read_bytes()):',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_png_signature_without_decodable_image_is_rejected",
    ),
    Mutant(
        "browser-transcript-action-check-disabled",
        "scripts/validate_frontend_evidence.py",
        'if not {"navigate", "click", "assert", "screenshot"} <= action_names:',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_browser_transcript_hash_and_actions_are_required",
    ),
    Mutant(
        "frontend-independent-black-box-binding-disabled",
        "scripts/validate_delivery_bundle.py",
        'if black_box is None or any(verifier != black_box.get("run_id") for verifier in verifiers):',
        "if False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_frontend_browser_must_bind_independent_black_box_run",
    ),
    Mutant(
        "e2e-runner-framework-binding-disabled",
        "scripts/validate_frontend_evidence.py",
        'if value.get("framework") != runner_framework:',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_runner_framework_must_match_evidence_framework",
    ),
    Mutant(
        "effective-agents-symlink-check-disabled",
        "scripts/validate_context_manifest.py",
        "if resolved.is_symlink():\n                issues.append(Issue(\"error\", \"unsafe-effective-agents-symlink\"",
        "if False:\n                issues.append(Issue(\"error\", \"unsafe-effective-agents-symlink\"",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_symlinked_scoped_agents_fails_closed",
    ),
    Mutant(
        "swimlane-all-changed-files-coverage-disabled",
        "scripts/validate_swimlane_evidence.py",
        "for uncovered in changed - covered_changed:",
        "for uncovered in ():",
        "scripts.test_validate_swimlane_evidence.SwimlaneEvidenceValidatorTests.test_every_changed_file_must_be_covered_by_swimlanes",
    ),
    Mutant(
        "frontend-time-order-check-disabled",
        "scripts/validate_frontend_evidence.py",
        "if start > end:\n            raise ValueError(\"order\")",
        "if False:\n            raise ValueError(\"order\")",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_invalid_or_reversed_times_are_rejected",
    ),
    Mutant(
        "playwright-empty-tree-check-disabled",
        "scripts/frontend_report_validation.py",
        'observed = _playwright_report_counts(report["suites"])',
        "observed = (expected, unexpected)",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_empty_playwright_test_tree_cannot_pass_from_summary_counts",
    ),
    Mutant(
        "local-e2e-runner-path-check-disabled",
        "scripts/validate_frontend_evidence.py",
        'if basename in {"playwright", "playwright.cmd", "cypress", "cypress.cmd"} and ("/" in executable or "\\\\" in executable):',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_project_local_file_named_playwright_cannot_masquerade_as_runner",
    ),
    Mutant(
        "env-shell-wrapper-check-disabled",
        "scripts/validate_project_commands.py",
        'FORBIDDEN_EXECUTABLES = {"true", "echo", "printf", "env", "command", "xargs", "bash", "sh", "zsh", "cmd", "powershell", "pwsh"}',
        'FORBIDDEN_EXECUTABLES = {"true", "echo", "printf", "bash", "sh", "zsh", "cmd", "powershell", "pwsh"}',
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_env_cannot_indirectly_launch_shell_or_swallow_failure",
    ),
    Mutant(
        "findings-none-exclusive-content-check-disabled",
        "scripts/traceability_parsing.py",
        "return has_none and has_other_content",
        "return False",
        "scripts.test_validate_traceability.TraceabilityValidatorTests.test_none_must_be_the_only_open_findings_content",
    ),
    Mutant(
        "cypress-results-semantic-check-disabled",
        "scripts/frontend_report_validation.py",
        'observed = _cypress_results_counts(report["results"])',
        "observed = (passes, failures)",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_placeholder_cypress_results_cannot_pass_from_summary_counts",
    ),
    Mutant(
        "mobile-desktop-evidence-reuse-check-disabled",
        "scripts/validate_frontend_evidence.py",
        "if reused_identity or reused_transcript or reused_screenshot:",
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_mobile_evidence_cannot_reuse_run_or_artifact_content_under_new_paths",
    ),
    Mutant(
        "browser-transcript-artifact-binding-disabled",
        "scripts/validate_frontend_evidence.py",
        'if data.get("viewport") != value.get("viewport") or data.get("screenshots") != value.get("screenshots"):',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_transcript_must_bind_viewport_and_screenshots",
    ),
    Mutant(
        "cypress-mocha-identity-binding-disabled",
        "scripts/frontend_report_validation.py",
        'observed = _mocha_report_counts(report, stats)',
        "observed = (passes, failures)",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_placeholder_cypress_mocha_json_cannot_pass",
    ),
    Mutant(
        "playwright-spec-identity-binding-disabled",
        "scripts/frontend_report_validation.py",
        'if (not isinstance(identity, str) or not identity.strip()\n                        or not isinstance(tests, list) or not tests):',
        "if False:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_anonymous_playwright_spec_cannot_pass",
    ),
    Mutant(
        "playwright-terminal-state-binding-disabled",
        "scripts/frontend_report_validation.py",
        'if actual_status in {"passed", "failed"} and actual_status == expected_status:',
        "if True:",
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_playwright_failed_terminal_state_must_match_unexpected_stats",
    ),
    Mutant(
        "playwright-exact-count-binding-disabled",
        "scripts/frontend_report_validation.py",
        'and expected + unexpected > 0 and observed == (expected, unexpected)',
        'and expected + unexpected > 0 and observed is not None',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_playwright_terminal_test_count_must_equal_stats",
    ),
    Mutant(
        "playwright-global-errors-check-disabled",
        "scripts/frontend_report_validation.py",
        'and isinstance(report.get("suites"), list) and report.get("errors") == []):',
        'and isinstance(report.get("suites"), list)):',
        "scripts.test_validate_frontend_evidence.FrontendEvidenceValidatorTests.test_playwright_global_errors_block_completion",
    ),
    Mutant(
        "indirect-shell-token-check-disabled",
        "scripts/validate_project_commands.py",
        "or shell_syntax or indirect_shell:",
        "or shell_syntax:",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_wrapper_cannot_indirectly_launch_shell_pipeline",
    ),
    Mutant(
        "single-pipe-shell-syntax-check-disabled",
        "scripts/validate_project_commands.py",
        'SHELL_OPERATOR_RE = re.compile(r"(?:\\||&&|[;\\r\\n])")',
        'SHELL_OPERATOR_RE = re.compile(r"(?:\\|\\||&&|[;\\r\\n])")',
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_single_pipe_shell_syntax_is_rejected",
    ),
    Mutant(
        "workset-parent-symlink-check-disabled",
        "scripts/validate_context_manifest.py",
        "if directory.is_symlink():",
        "if False:",
        "scripts.test_validate_context_manifest.ContextManifestValidatorTests.test_symlinked_workset_parent_fails_closed",
    ),
    Mutant(
        "mobile-black-box-binding-disabled",
        "scripts/validate_delivery_bundle.py",
        'if isinstance(frontend, dict) and isinstance(frontend.get("mobile"), dict):',
        "if False:",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_mobile_browser_must_bind_independent_black_box_run",
    ),
    Mutant(
        "password-document-authorization-auto-detection-disabled",
        "scripts/validate_agents_md.py",
        "        allow_passwords=document_authorized,\n",
        "        allow_passwords=allow_passwords and mode == \"project\",\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_valid_document_authorization_needs_no_cli_allowance",
    ),
    Mutant(
        "password-endpoint-scheme-binding-disabled",
        "scripts/password_authorization_validation.py",
        "    if rule.scheme != endpoint.scheme:\n        return False\n",
        "    if False:\n        return False\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_password_authorization_rejects_scheme_mismatch",
    ),
    Mutant(
        "password-endpoint-port-binding-disabled",
        "scripts/password_authorization_validation.py",
        "    if (rule.host, rule.port) != (endpoint.host, endpoint.port):\n",
        "    if rule.host != endpoint.host:\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_password_authorization_rejects_explicit_port_mismatch",
    ),
    Mutant(
        "password-endpoint-path-boundary-disabled",
        "scripts/password_authorization_validation.py",
        '    return rule.path == "/" or endpoint.path == rule.path or endpoint.path.startswith(f"{rule.path}/")\n',
        "    return True\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_password_authorization_path_prefix_rejects_sibling",
    ),
    Mutant(
        "password-default-port-normalization-disabled",
        "scripts/password_authorization_validation.py",
        "    effective_port = port if port is not None else DEFAULT_PORTS.get(scheme)\n",
        "    effective_port = port\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_password_authorization_normalizes_default_port",
    ),
    Mutant(
        "password-query-path-binding-disabled",
        "scripts/password_authorization_validation.py",
        "    if not allow_userinfo and (parsed.query or parsed.fragment):\n",
        "    if parsed.query or parsed.fragment:\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_password_authorization_path_binding_survives_query_string",
    ),
    Mutant(
        "malformed-password-uri-fail-closed-disabled",
        "scripts/password_authorization_validation.py",
        "    if any(scope is None for scope in actual):\n",
        "    if False:\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_malformed_password_uri_endpoint_fails_closed",
    ),
    Mutant(
        "encoded-password-path-check-disabled",
        "scripts/password_authorization_validation.py",
        '    if "\\\\" in parsed.path or re.search(r"%(?:2e|2f|5c)", parsed.path, re.IGNORECASE):\n',
        "    if False:\n",
        "scripts.test_validate_agents_md.ValidatorRegressionTests.test_encoded_password_uri_path_fails_closed",
    ),
)

MUTANTS = (
    *CORE_MUTANTS,
    *(Mutant(*case) for case in (
        *ADDITIONAL_MUTANT_CASES, *STRICT_MUTANT_CASES, *REVIEW_FIX_MUTANT_CASES,
        *STABILITY_MUTANT_CASES, *MODULE_CLOSURE_MUTANT_CASES,
        *AUTHORITY_BINDING_MUTANT_CASES,
        *NATIVE_REVIEW_MUTANT_CASES,
        *REVIEW_TRIGGER_MUTANT_CASES,
        *REQUIREMENT_QUESTION_MUTANT_CASES,
        *DELIVERY_QUESTION_MUTANT_CASES,
        *DELIVERY_CONTRACT_BUNDLE_MUTANT_CASES,
        *WRITE_AUTHORITY_MUTANT_CASES,
        *LOCAL_TRUST_MUTANT_CASES,
        *MODULE_LEASE_MUTANT_CASES,
    )),
)


def main() -> int:
    survivors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="generate-agents-md-mutation-") as temporary:
        temporary_root = Path(temporary)
        for mutant in MUTANTS:
            target_root = temporary_root / mutant.name
            shutil.copytree(SKILL_ROOT, target_root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            target = target_root / mutant.relative_path
            source = target.read_text(encoding="utf-8")
            if source.count(mutant.original) != 1:
                print(f"ERROR mutation-anchor {mutant.name} expected exactly one source anchor")
                return 1
            target.write_text(source.replace(mutant.original, mutant.replacement), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "unittest", mutant.test],
                cwd=target_root,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                survivors.append(mutant.name)
                print(f"SURVIVED {mutant.name}")
            else:
                print(f"KILLED {mutant.name}")
    if survivors:
        print(f"mutation_survivors={len(survivors)} valid=false")
        return 1
    print(f"mutation_survivors=0 mutants={len(MUTANTS)} valid=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
