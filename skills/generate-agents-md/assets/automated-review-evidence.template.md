# Automated Review Evidence

- Run ID: {{IMPLEMENTATION_RUN_ID}}
- Code version: {{CODE_VERSION}}
- Code fingerprint: {{CONTEXT_CODE_FINGERPRINT}}
- Command manifest fingerprint: {{CONTEXT_COMMAND_MANIFEST_FINGERPRINT}}
- Review trigger: {{MODULE_CLOSURE_CANDIDATE_OR_HUMAN_REQUESTED}}
- Human trigger reference: {{N_A_OR_HUMAN_REQUEST_LOCATOR}}
- Scope: {{CHANGED_FILE_PATHS}}; callers; callees; interfaces; configuration; tests; traceability{{GATE_PLAN_SWIMLANE_SCOPE_SUFFIX_OR_EMPTY}}
- Changed files: {{CHANGED_FILE_PATHS}}
- Review command ID: automated_review
- Review command argv SHA-256: {{NULL_SEPARATED_ARGV_SHA256}}
- Review exit code: {{ZERO_ONLY_FOR_PASS}}
- Review evidence path: {{PROJECT_RELATIVE_RAW_REVIEW_OUTPUT_PATH}}
- Review evidence SHA-256: {{RAW_REVIEW_OUTPUT_SHA256}}
- Findings: {{NONE_OR_CLOSED_FINDING_IDS}}
- Rerun command IDs: {{TARGETED_TESTS_CODE_STANDARDS_TRACEABILITY_AUTOMATED_REVIEW_AND_GATE_PLAN_SWIMLANE_IDS}}
- Rerun exit codes: {{COMMAND_ID_EQUALS_ZERO_PAIRS}}
- Verdict: {{PASS_OR_BLOCKED}}
