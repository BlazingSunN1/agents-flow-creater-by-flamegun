from __future__ import annotations


COMMAND_EXECUTION_MUTANT_CASES = (
    (
        "gate-output-overwrite-restored", "scripts/gate_output_files.py",
        "output.open('xb')", "output.open('wb')",
        "scripts.test_gate_closure_repairs.GateClosureRepairTests.test_gate_cannot_overwrite_contract_or_existing_receipt",
    ),
    (
        "gate-receipt-overwrite-restored", "scripts/gate_output_files.py",
        "receipt.open('xb')", "receipt.open('wb')",
        "scripts.test_gate_closure_repairs.GateClosureRepairTests.test_gate_cannot_overwrite_contract_or_existing_receipt",
    ),
    (
        "command-file-fingerprint-disabled", "scripts/delivery_gate_planner.py",
        '"files": _command_files(item, project_root.resolve())', '"files": []',
        "scripts.test_gate_closure_repairs.GateClosureRepairTests.test_script_content_changes_command_fingerprint",
    ),
    (
        "zero-test-native-summary-accepted", "scripts/gate_test_results.py",
        "int(runs[0].group(1)) > 0", "int(runs[0].group(1)) >= 0",
        "scripts.test_gate_test_results.GateTestResultsTests.test_unittest_report_requires_nonzero_all_passed",
    ),
    (
        "receipt-native-test-result-check-disabled", "scripts/validate_delivery_contract.py",
        "elif output is not None and not test_result_passes(\n"
        "            command_id, expected_argv, output.read_bytes(), result_kind=command.get('result_kind', 'tests')):",
        "elif False:",
        "scripts.test_gate_closure_repairs.GateClosureRepairTests.test_zero_test_output_is_rejected_by_contract_validator",
    ),
    (
        "cypress-pending-acceptance-restored", "scripts/frontend_report_validation.py",
        "    if pending_ids:\n", "    if False:\n",
        "scripts.test_gate_closure_repairs.CypressPendingRepairTests.test_pending_acceptance_fails_complete_frontend_validation",
    ),
    (
        "always-enabled-project-command-check-disabled", "scripts/validate_project_commands.py",
        "    for command_id in ALWAYS_ENABLED_COMMANDS:\n",
        "    for command_id in ():\n",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_always_enabled_commands_cannot_be_marked_na",
    ),
    (
        "python-command-entrypoint-check-disabled", "scripts/validate_project_commands.py",
        "    _validate_command_entrypoint(argv, working_directory, root, command_id, issues)\n",
        "",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_python_script_entrypoint_must_exist_and_comment_is_not_provenance",
    ),
    (
        "command-html-comment-view-disabled", "scripts/validate_project_commands.py",
        "    return markdown_without_html_comments(text)\n",
        "    return text\n",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_python_script_entrypoint_must_exist_and_comment_is_not_provenance",
    ),
    (
        "command-fenced-markdown-view-disabled", "scripts/validate_project_commands.py",
        "        return normative_markdown_view(text)\n",
        "        return text\n",
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_fenced_markdown_command_is_not_provenance",
    ),
    (
        "literal-argv-shell-false-positive-restored", "scripts/validate_project_commands.py",
        "    shell_syntax = any(value in FORBIDDEN_ARGUMENTS for value in argv[1:])\n",
        '    shell_syntax = any(value in FORBIDDEN_ARGUMENTS or "|" in value for value in argv[1:])\n',
        "scripts.test_validate_project_commands.ProjectCommandValidatorTests.test_literal_pipe_inside_argv_value_is_not_shell_operator",
    ),
    (
        "wrapped-full-test-bypass-restored", "scripts/gate_test_results.py",
        "command_id == 'full_test_or_build' and (\n"
        "            result_kind != 'build' or invokes_test_framework(argv) or _looks_like_test_report(payload))",
        "False",
        "scripts.test_gate_review_repairs.GateReviewRepairTests.test_wrapped_zero_test_full_gate_fails_runner_and_validator",
    ),
    (
        "output-argv-fingerprint-feedback-restored", "scripts/delivery_gate_planner.py",
        "candidates = _command_entrypoints(argv, base)",
        "candidates = [base / token for token in argv if not token.startswith('-')]",
        "scripts.test_gate_review_repairs.GateReviewRepairTests.test_generated_output_does_not_invalidate_gate",
    ),
    (
        "mutation-load-errors-counted-as-killed", "scripts/mutation_execution.py",
        "\n    return 'invalid'\n",
        "\n    return 'fail'\n",
        "scripts.test_mutation_execution.MutationExecutionTests.test_mutated_import_error_is_invalid_not_killed",
    ),
    (
        "build-wrapper-test-report-bypass-restored", "scripts/gate_test_results.py",
        " or _looks_like_test_report(payload)", "",
        "scripts.test_gate_review_repairs.GateReviewRepairTests.test_build_wrapper_cannot_hide_zero_test_report",
    ),
)
