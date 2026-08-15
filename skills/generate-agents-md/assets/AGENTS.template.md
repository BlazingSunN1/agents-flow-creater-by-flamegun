# Agent Instructions

<!-- PUBLIC TEMPLATE: replace placeholders and remove this comment in project mode. -->

## Project Context

- Purpose: {{PROJECT_PURPOSE}}
- Primary stack: {{PRIMARY_STACK}}
- Supported environment: {{SUPPORTED_ENVIRONMENT}}

## Machine-Enforced Policy

This block is authoritative. Other project instructions may add detail but must not weaken or contradict it.

```yaml
schema_version: 1
automated_review: required_after_code_module_change
context_manifest_validation: required_before_expansion_or_reuse
traceability_validation: required_before_handoff_and_completion
delivery_bundle_validation: required_before_handoff_and_completion
project_command_validation: required_before_command_execution
frontend_evidence_validation: required_after_frontend_change
multi_agent_evidence_validation: required_before_handoff_and_completion
swimlane_evidence_validation: required_at_stage_completion_or_flow_change
atomic_record_updates: required_for_shared_mutable_records
single_writer_model: implementation_agent_only
swimlane_sync: required_at_stage_completion_or_flow_change
frontend_click_verification: required_after_frontend_change
local_browser_preview: http_or_https_only
mobile_verification: conditional_on_approved_scope
ui_ux_agent: conditional_on_ui_or_user_visible_change
sensitive_connection_values: explicit_project_authorization_only
```

## Project Constraints

- {{ARCHITECTURAL_BOUNDARY}}
- {{DATA_OR_COMPATIBILITY_CONSTRAINT}}
- {{SECURITY_OR_PRIVACY_CONSTRAINT}}
- Fix root causes; do not hide failures by swallowing errors, fabricating results, or disabling validation.
- Keep changes focused and consistent with existing code; report unrelated problems without fixing them unless requested.

## Repository Layout

```text
{{KEY_REPOSITORY_TREE}}
```

- `{{PATH}}`: {{RESPONSIBILITY}}
- `{{PATH}}`: {{RESPONSIBILITY}}

## Verification

- Start with the tests closest to the changed behavior, then expand validation according to risk.
- Add tests for new behavior when the repository already has an applicable test structure.
- Do not claim tests passed unless the listed command was actually executed successfully.
- Treat `{{PROJECT_COMMAND_MANIFEST_PATH}}` as the executable command registry. Before running a required project command, validate it with `{{PROJECT_COMMAND_VALIDATION_COMMAND}}`; a missing, fabricated, constant-success, shell-wrapped, indirect `env`/command wrapper, undeclared, or invalid command blocks execution and completion.

```bash
{{TARGETED_TEST_COMMAND}}
{{FULL_TEST_OR_BUILD_COMMAND}}
{{FORMAT_OR_STATIC_CHECK_COMMAND}}
```

## Change Boundaries

- Preserve public APIs, data contracts and compatibility unless the task explicitly requires a breaking change.
- Update affected documentation when changing public behavior, configuration, CLI, schemas or deployment requirements.
- {{PROJECT_SPECIFIC_CHANGE_RULE}}

## Development Plan and Progress

- Maintain the development plan in `{{DEVELOPMENT_PLAN_PATH}}` and the compact completion index in `{{PROGRESS_RECORD_PATH}}`.
- Bind the plan to `Baseline version` and `Baseline SHA-256`, and include non-empty `Objective`, `Scope`, `Ordered steps`, `Verification criteria`, and `Known risks`. Bind progress to the current `Run ID` and `Code version`; completion additionally requires `Completion date`, `Delivered result`, `Validation performed`, closed `Remaining work`, and `Status: completed`.
- Before substantial implementation, record the objective, scope, ordered steps, verification criteria, and known risks.
- After completing verified work, record the completion date, delivered result, validation performed, and remaining work.
- Use explicit states such as `pending`, `in_progress`, `completed`, and `blocked`; never mark unexecuted or unverified work as completed.
- Keep sensitive connection values out of these records unless the user explicitly authorizes their project-scoped handling.
- Update shared plan, progress, trace, context and evidence indexes through `{{ATOMIC_RECORD_UPDATE_COMMAND}}`, using a file lock, the expected current SHA-256, and atomic replacement. A stale write must fail and be reread; never let concurrent Agents overwrite each other.

## Requirement Traceability and Delivery Gates

- Maintain the delivery traceability matrix at `{{REQUIREMENT_TRACEABILITY_PATH}}`. Assign stable `REQ-*`, `FLOW-*`, `FEAT-*`, `UI-*`, `UT-*`, `AT-*`, `MOD-*`, and `BB-*` identifiers, and link every downstream artifact back to its originating requirement.
- Bind each trace column to a role-appropriate artifact; one file, symlink or hard link must not impersonate different Requirement, Flow, Feature, UI, Unit-test, Acceptance, Code-module or Black-box roles.
- Before implementation, baseline the objective, scope, non-goals, constraints, and measurable acceptance criteria. Record the baseline artifact, immutable version and SHA-256; bind final black-box evidence to the exact code version, build ID, acceptance environment and timezone-aware verification time. An unresolved ambiguity must return to the requirement baseline and blocks implementation; no Agent may silently invent product behavior.
- For standard and high-risk work, follow this order: solution design → system and module swimlanes → feature points → independent UI/UX prototype review when UI is affected → test points and unit cases → independently authored complete acceptance cases → implementation → continuous code checks → independent black-box acceptance.
- When the user explicitly enables external multi-model review, invoke `$multi-model-review-loop` as a parallel advisory channel: use isolated `spawn_external_agent.py` runs for Kimi to author every complete design/revision and DeepSeek to author complete observable black-box cases plus a defect review for that exact version, then let the active Codex GPT independently adjudicate, verify case coverage, and request a complete Kimi revision. Bind the immutable scope and redacted context, criteria, candidate, DeepSeek review, version, fixed prompts, raw provider response/model/response ID/usage, normalized output, and structured native GPT input/check/output evidence with the final same-candidate hash loop-bundle machine gate. Bound the loop to six rounds; if the same candidate has not passed both DeepSeek and GPT by then, emit machine-validated `incomplete`, never passed. DeepSeek-authored cases are not execution evidence; the real independent black-box gate must still run. External models never replace Codex native sub-Agents, the sole writer, runtime tests, independent acceptance, or black-box execution; do not change Codex's model, login, proxy, global environment, or workspace authority, and never place sensitive values in prompts, artifacts, logs, or evidence.
- Classify each change as small, standard, or high-risk and record the reason and change surfaces. `behavior-change`, `user-visible`, `ui`, or `api` is at least standard; `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, or `data-schema` is high-risk; unknown impact remains high-risk until disproved. A small change may skip an inapplicable prototype or independent design gate only when it does not alter the corresponding behavior and the run records the explicit reason; it never skips relevant tests, traceability, swimlane synchronization, or final verification.
- Give the independent UI/UX Agent the approved requirement baseline, solution, swimlanes, and feature points. It may produce or review the prototype and UI states, but it must report ambiguity instead of expanding requirements or modifying implementation code.
- Define test points and applicable unit test cases before implementation. Give a separate acceptance Agent the approved baseline, feature points, UI states, and test points so it authors complete success, rejection, failure, retry, recovery, permission, and boundary cases before implementation begins.
- Implement only approved `REQ-*` and `FEAT-*` items. Any new or changed behavior requires a new or updated identifier and synchronized design, swimlane, UI, test, and acceptance artifacts before code continues.
- Enforce code standards continuously before and during implementation with `{{FORMAT_OR_STATIC_CHECK_COMMAND}}`; do not postpone formatting, type, lint, complexity, security, or architectural checks until the end.
- After implementation, give an independent black-box Agent the approved acceptance cases and a release-like interface, without asking it to modify code or accept the implementation Agent's self-report. Record reproducible evidence for every `BB-*` result.
- Record distinct implementation and applicable UI/UX, acceptance-case, and black-box Agent run IDs, plus a minimal input manifest and output evidence for each applicable independent gate; a non-UI, non-user-visible change marks UI/UX `N/A` with a verified reason and does not start that Agent. An applicable independent run ID must not equal the implementation run ID or another independent gate run ID.
- Use one implementation Agent as the sole code and shared-record writer. All independent Agents are read-only for code and shared records and receive no full chat, other Agent reasoning, or implementation self-report as proof. At implementation handoff do not start or require black-box acceptance; completion requires it. Small work uses only acceptance-case and stage-applicable black-box Agents; standard work adds a change-review Agent; high-risk work adds requirement-consistency and domain-specialist Agents. UI/UX remains conditional on UI or user-visible scope. Do not start an extra role without an approved escalation reason.
- Validate `{{MULTI_AGENT_EVIDENCE_PATH}}` with `{{MULTI_AGENT_EVIDENCE_VALIDATION_COMMAND}}` using the same `implementation` or `completion` stage as the delivery gate. Bind every applicable role to a unique run ID, unique minimum input/output paths, hashed evidence and current baseline/code/build; the paths must match the trace matrix. Any missing or extra role, reused identity or artifact, writable reviewer, open finding or unresolved disagreement is `blocked`; never resolve conflicts by majority vote.
- Store each independent input as strict structured JSON bound to role, run ID, baseline, the current affected requirement IDs, the exact minimum role-specific artifact set, and the current SHA-256 of every artifact, plus boolean-false full-chat/other-reasoning/implementation-self-report flags. Store each output as strict structured JSON bound to that input manifest SHA-256, role, run ID, baseline, code version, verdict, and findings. Reject missing, extra or drifted input artifacts, duplicate or unknown fields, boolean/integer aliases, symlink or hard-link aliases, normalized-content reuse, output reuse of changed/configuration/input files, and reuse across independent roles.
- Classify every failure before retrying: route `implementation_defect` to implementation, `requirement_ambiguity` to the requirement baseline, `acceptance_case_defect` to acceptance cases, `environment_blocker` to blocked, and `approved_requirement_change` to a new baseline. Never edit requirements merely to make an implementation defect pass.
- Run the fail-closed semantic trace validator `{{TRACEABILITY_VALIDATION_COMMAND}}` before implementation handoff and again before marking any row or run `completed`. If the validator is missing, cannot run, or reports any error, the gate is `blocked`; do not substitute manual judgment.
- At the same two stages run the aggregate delivery-bundle validator `{{DELIVERY_BUNDLE_VALIDATION_COMMAND}}` so AGENTS.md, the traceability matrix, context manifest, command registry, plan/progress, automated-review evidence, current module run, completion-stage `latest.md`, multi-Agent evidence, and applicable frontend evidence bind the same baseline version/hash, code version, build, and implementation run ID. Any missing artifact or cross-artifact mismatch is `blocked`.
- If an independent Agent cannot be started, record the gate as `blocked`; the implementation Agent must not self-certify an independent gate. Do not mark work `completed` until the current baseline hash, code/build binding, artifact paths and trace close, required tests and independent acceptance pass, artifacts are synchronized, and no relevant bug, open finding or unexplained error remains.

## Automated Code Review

- After every code module change, automatically run `{{AUTOMATED_REVIEW_COMMAND}}` after targeted tests and before black-box acceptance. If the command is missing, cannot run, or reports an error, mark the review `blocked`; do not silently skip it.
- Review the actual changed files and their affected callers, callees, public interfaces, configuration, persistence or asynchronous boundaries, tests, requirement trace, and swimlane diagrams. A diff summary or implementation self-report is not sufficient evidence.
- Record every actionable finding with severity, exact file and line, trigger, impact, and executable reproduction or verification. Classify requirement ambiguity separately from implementation defects.
- Route implementation defects back to implementation, add a failing regression test when applicable, make the smallest root-cause fix, and automatically rerun targeted tests, code standards, trace validation, this review, and—when a stage completes or the fix changes a flow—swimlane validation.
- Store the implementation run ID, review scope, changed files, code version, commands and results, findings, rerun results, and verdict at `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}`; bind this record through the aggregate delivery validator. Do not enter black-box acceptance or mark the run `completed` while any actionable finding, unexplained error, or blocked review remains.

## Context and Token Budget

- Maintain the current workset manifest at `{{CONTEXT_MANIFEST_PATH}}`. Record the baseline version and hash, code version, Build ID, risk/expansion reason, affected requirement IDs, modules, an explicit module-to-changed-files map, changed files, direct dependency boundaries, required commands, the exact effective root-to-scope AGENTS chain and combined hash, complete command-manifest hash, and evidence paths/hashes. Build ID, risk/expansion reason, dependency boundaries, and the exact module map are part of the evidence cache key.
- Read in this order: the compact progress index, the affected modules' `latest.md`, the current run, the workset's requirement rows, then only directly affected code, tests, configuration, and diagrams. Do not scan the whole repository, all historical runs, complete logs, or unrelated artifacts by default.
- Expand the workset only when the change is high-risk, cross-module, changes a public contract, has unknown impact, or when targeted review or tests expose an unresolved dependency. Record the expansion reason in the manifest.
- Reuse prior verification evidence only when a structured successful-run reuse record binds a run ID different from the current run, the exact module, immutable completed source-run record path/hash, current evidence cache key, and every reusable evidence path/hash. A singular source-run record may serve only a one-module workset; multi-module worksets must rerun. The source run must declare the same module, Build ID, acceptance environment, cache key, and exact verification-evidence set. The matching fingerprint must include code version, Build ID, complete command and command-manifest hash, configuration hash, environment ID, and relevant input hashes. Adding, changing, moving, or deleting an applicable scoped AGENTS file invalidates reuse; a symlinked AGENTS file, symlinked workset parent, or symlinked workset leaf is invalid rather than silently ignored. Directories cannot stand in for required files. Treat missing, failed, current-run, unknown-run, or mismatched provenance as stale and rerun the gate.
- Before expanding the workset or reusing evidence, run the fail-closed manifest validator `{{CONTEXT_MANIFEST_VALIDATION_COMMAND}}`. A missing command, validation error, stale cache key, or missing evidence path is `blocked`; do not replace it with manual judgment.
- Store raw command output, screenshots, diffs, and generated files at project paths. In prompts and run summaries record only the command, exit status, concise result counts, fingerprint, and evidence path; do not paste unchanged bulk output.
- Give each independent Agent only its role-specific input manifest and directly linked artifacts; do not send the full chat, all repository documentation, unrelated module logs, or another Agent's reasoning.
- Do not rerun an identical command when its complete fingerprint and successful evidence remain valid. Token or context limits never justify skipping a required correctness, security, traceability, review, swimlane, or acceptance gate.

## Modular Execution Logs

- Keep the compact execution index at `{{PROGRESS_RECORD_PATH}}`; it contains only current module status and links to detailed records.
- Store immutable module runs under `{{MODULE_EXECUTION_LOG_DIRECTORY}}/<module>/run-<run_id>.md`. Store cross-module runs under `{{SYSTEM_EXECUTION_LOG_DIRECTORY}}/`.
- Assign every run a distinct `run_id` and `code_version`. Use `run_id` for the Agent execution and `code_version` for a Git commit, tag, or build version; never treat them as the same identifier.
- Each run record must include the run ID, module, status, code version, risk level, traceability IDs, changed files, delivered result, automated code review, verification and independent review evidence, swimlane diagram paths, and remaining risks.
- After verified completion, update the module's compressed `latest.md` summary and the compact execution index. Do not rewrite immutable historical run records.
- Do not mark a run `completed` until its run record, module `latest.md`, and compact index are synchronized.
- To limit context use, read the compact index first, then only the affected module's `latest.md` and the current `run_id`. Read older runs only for regression, conflict, or historical-decision investigation; never scan all history by default.
- Reference project paths for raw test output, screenshots, diffs, and generated diagrams instead of pasting large artifacts into execution logs.

## Swimlane Diagram Synchronization

- At each defined stage or task milestone completion, generate a missing affected module swimlane or synchronize the existing diagram at `{{MODULE_SWIMLANE_PATH}}` before handoff. Between milestones, update it immediately only when the code change alters an entry point, user or system flow, branch, cross-module handoff, external dependency, persistence, asynchronous event, recovery path, or final output; a flow-neutral internal edit does not trigger a redraw.
- Derive the flow from implementation code, entry points, call chains, interfaces, configuration, and tests; documentation alone is not sufficient evidence.
- If a change affects module boundaries, entry points, cross-module calls, system boundaries, external dependencies, persistence, asynchronous events, or final outputs, update the complete system overview at `{{SWIMLANE_OVERVIEW_PATH}}` first, then update every affected module diagram.
- After a stage synchronization or a flow-triggered diagram change, open the interactive HTML in a browser and click through the affected modules. Verify that lane headers, connectors, module drill-down, and return-to-overview behavior are visible and complete.
- For local HTML or frontend pages, start the registered preview server on a loopback address, verify its HTTP health URL, and open that `http://` or `https://` URL in the application browser. Require a loopback host and bind the URL path to the current system-diagram path relative to its preview root, the diagram's actual SHA-256, and the browser-observed HTTP response-body SHA-256; never use `file://` or an unrelated HTTP page for automated browser evidence.
- Record the affected modules, diagram paths, reviewed code evidence, and browser verification result in the current module run, then update the compact completion progress record at `{{PROGRESS_RECORD_PATH}}`.
- Save that structured binding at `{{SWIMLANE_EVIDENCE_PATH}}` and run `{{SWIMLANE_EVIDENCE_VALIDATION_COMMAND}}`; the system diagram, every changed module, diagram hashes, exact module-owned Changed-file coverage, path/inode uniqueness, visible and enabled `href` controls to visible matching module target ids, a visible working return-to-overview target, and browser transcript must all validate before delivery.
- A stage or task milestone is not complete and must not be marked `completed` until its affected swimlanes are synchronized and verified; do not force intermediate redraws for flow-neutral edits.

## Frontend Interaction Verification

- After every frontend code change, use `browser:control-in-app-browser` to exercise the affected user flow with human-like clicks in a desktop PC browser viewport.
- For local pages, use the project's registered development server or a loopback-only static preview command. Register the authoritative entry URL, preview root, and served entry artifact in the project command manifest; browser evidence must match them exactly. Confirm the HTTP endpoint is ready and require the validator's same-run live GET body SHA-256 to equal the entry artifact and recorded response hash; a stopped service, displayed `file://`, decoy file, redirected response, or unrelated HTTP page is not valid automated browser evidence.
- Run the project's Playwright or Cypress end-to-end command `{{FRONTEND_E2E_COMMAND}}` for the affected flow; if no applicable suite exists, add the smallest maintainable test path or record the missing suite as a blocker.
- Use human-like clicks from the real user entry point through state or data changes to the visible result, completing the full interaction closure including applicable validation, failure, retry, and recovery branches. Save a hashed UTF-8 DOM snapshot whose bytes equal the live served entry response; express navigation, click, and assertion targets as CSS id selectors. Every action transcript entry must include browser-computed `visible: true` and `enabled: true`; every declared click and assertion target must appear in the executed action set. Cross-check click selectors against DOM, document-ordered inline/linked CSS cascade including `!important`, ARIA, inert and disabled state. Bind each click to hashed before/after UTF-8 DOM snapshots that prove the declared assertion node itself changed and remains visible. Every screenshot must be a fully decodable PNG whose scanlines and dimensions cover the declared viewport.
- Only when the approved requirement baseline, supported environment, or affected change scope explicitly includes mobile, touch, or responsive behavior, repeat the closure in applicable mobile browser viewports and run the corresponding mobile end-to-end cases. Otherwise mobile adaptation and mobile verification are not required and must not block completion.
- Confirm there are no console errors, failed required requests, broken controls, clipped critical content, or page-level horizontal overflow in every required viewport; record viewport sizes, click path, assertions, and evidence in the current run.
- The completion-stage application-browser transcript must be executed or independently replayed by the current read-only BLACK_BOX Agent; bind its distinct Agent run ID as the verifier rather than accepting the implementation Agent's self-report.
- Save the structured browser, served entry-artifact identity, hashed DOM snapshot, viewport-sized decodable screenshot, hashed tool-action transcript, and native Playwright/Cypress report at `{{FRONTEND_EVIDENCE_PATH}}`, then validate it with `{{FRONTEND_EVIDENCE_VALIDATION_COMMAND}}`; bind browser/E2E run IDs, the independent verifier run ID, parseable ordered timezone-aware start/end times, page URL/preview root/entry path/hash, DOM selectors, transcript viewport plus screenshot paths/hashes, exact E2E argv hash, runner framework, and nonempty identified native tests with terminal states. Resolve inline and project-relative linked CSS in document cascade order, reject unreplayable CSS imports, require every declared action in its exact order and multiplicity, and bind every click to actual before/after DOM artifact hashes whose declared assertion node changes and is visible. Apply the same rules to mobile evidence when mobile is in scope, but require a distinct mobile run ID and distinct transcript/screenshot content hashes. Stale hashes, unrelated pages, missing/non-interactive DOM targets, undersized or structurally invalid screenshots, incomplete/reordered/deduplicated click paths, missing state transitions, failed requests, console errors, fabricated image bytes, summary-only or placeholder reports, reused desktop evidence, or mismatched baseline/code/build block completion.
- If any bug or unexplained error remains, the frontend change is not complete and must not be marked `completed` or passed.

## Project-Specific Rules

- {{STABLE_PROJECT_RULE}}
