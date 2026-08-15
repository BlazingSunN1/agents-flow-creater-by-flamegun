# Optional AGENTS.md Sections

<!-- Copy only sections supported by verified project facts. -->

## Architecture and Data Flow

```text
{{INPUT}} -> {{COMPONENT}} -> {{OUTPUT}}
```

- {{COMPONENT_RESPONSIBILITY}}
- {{DEPENDENCY_DIRECTION_OR_MESSAGE_FLOW_RULE}}
- {{RETRY_IDEMPOTENCY_OR_DEGRADATION_RULE}}

## Logging and Observability

- Log {{REQUIRED_EVENTS_OR_STATE_TRANSITIONS}} using {{LOG_FORMAT}}.
- Required fields: {{REQUIRED_LOG_FIELDS}}.
- Never log sensitive connection values, raw sensitive payloads or unnecessary personal data.
- Validate changes with {{METRICS_OR_TRACE_COMMAND}}.

## Debugging

1. Reproduce the issue with {{MINIMAL_REPRODUCTION_INPUT}}.
2. Inspect {{LOGS_STATE_AND_EXTERNAL_DEPENDENCIES}} before changing code.
3. Confirm the actual input shape, version, ordering and failing call chain.
4. Add or update the smallest regression test that reproduces the failure.
5. Verify the fix and adjacent boundary conditions; do not patch third-party source without explicit justification.

## Runtime and Deployment

- Runtime: {{OS_AND_RUNTIME_VERSION}}
- Deployment: {{DEPLOYMENT_METHOD}}
- Configuration: {{CONFIG_FILES_ENVIRONMENT_VARIABLES_OR_CLI}}
- Resource limits: {{CPU_MEMORY_GPU_OR_STORAGE_LIMITS}}
- Start, stop and rollback: {{VERIFIED_OPERATIONS}}
- Do not depend on developer-specific drive letters, home directories or interactive sessions.

## Data, Security and Compliance

- Data classification: {{DATA_CLASSIFICATION}}
- Retention and deletion: {{RETENTION_POLICY}}
- Sensitive values normally come from {{SECRET_MANAGEMENT_MECHANISM}}. Project-scoped exceptions require explicit user authorization and must define {{SENSITIVE_VALUE_SCOPE_STORAGE_AND_ACCESS_BOUNDARY}}; unrelated value types remain in the configured management mechanism.
- {{LICENSE_PRIVACY_OR_AUDIT_RULE}}

## Development Plan and Completion Progress

- Development plan: `{{DEVELOPMENT_PLAN_PATH}}`.
- Completion progress: `{{PROGRESS_RECORD_PATH}}`.
- Before implementation, update the plan with scope, ordered work, acceptance criteria, dependencies, and risks.
- After verification, append or update the completion record with the date, result, validation evidence, and remaining work.
- Use `pending`, `in_progress`, `completed`, or `blocked`; do not report planned or unverified work as completed.
- {{PROJECT_SPECIFIC_PROGRESS_FORMAT_OR_OWNERSHIP_RULE}}

## Modular Execution Log Layout

```text
{{EXECUTION_LOG_ROOT}}/
├── index.md
├── system/
│   └── run-<run_id>.md
└── modules/
    └── <module>/
        ├── latest.md
        └── run-<run_id>.md
```

- Module key source: {{MODULE_KEY_SOURCE}}.
- `run_id` format: {{RUN_ID_FORMAT}}.
- `code_version` source: {{CODE_VERSION_SOURCE}}.
- Keep `index.md` and `latest.md` concise; store immutable per-run evidence in `run-<run_id>.md` and reference large artifacts by path.

## Documentation Synchronization

- Update {{DOCUMENTATION_FILES}} when changing {{PUBLIC_BEHAVIOR_OR_CONTRACTS}}.
- Documentation must describe the current implementation; remove or label future work explicitly.

## Expanded Swimlane Diagram Structure

- System overview entry: `{{SWIMLANE_OVERVIEW_PATH}}`.
- Module diagram directory: `{{MODULE_SWIMLANE_DIRECTORY}}`.
- Keep stable module identifiers between the overview and module diagrams so overview cards can open the correct module flow.
- Each module diagram must show actors or components as lane headers, ordered steps, decisions, cross-lane handoffs, asynchronous events, exception recovery, and final outcomes when present in code.
- For interactive HTML, verify desktop viewport behavior with `{{SWIMLANE_BROWSER_TEST_COMMAND}}`; manually click the affected module path from overview to detail and back. Add mobile viewport verification only when mobile, touch, or responsive behavior is in the approved scope.
