# Agent Instructions

<!-- PUBLIC TEMPLATE: replace placeholders and remove this comment in project mode. -->

## Project Context

- Purpose: {{PROJECT_PURPOSE}}
- Primary stack: {{PRIMARY_STACK}}
- Supported environment: {{SUPPORTED_ENVIRONMENT}}

## Machine-Enforced Policy

This block is authoritative. Project instructions may add detail but must not weaken or contradict it.

```yaml
schema_version: 1
delivery_sequence: result_candidate_then_affected_checks_then_freeze_then_mapped_hardening
pre_result_gate_policy: correctness_and_irreversible_only
post_freeze_regression_replay: required
security_gate_policy: mapped_surface_or_explicit_only
automated_review: required_at_module_closure_candidate_or_human_trigger
context_manifest_validation: required_before_expansion_or_reuse
traceability_validation: required_before_handoff_and_completion
delivery_bundle_validation: required_before_handoff_and_completion
documentation_after_black_box: required
project_command_validation: required_before_evidenced_gate_or_completion
frontend_evidence_validation: required_after_frontend_change
multi_agent_evidence_validation: required_before_handoff_and_completion
swimlane_evidence_validation: required_before_downstream_use_and_stage_completion
atomic_record_updates: required_for_shared_mutable_records
single_writer_model: implementation_agent_only
authorization_mode: delivery-first-local-coordination
strict_security_mode: explicit_or_mapped_high_risk_only
requirement_questions: non_blocking_p2
major_module_closure: required
maintainer_self_acceptance: forbidden
affected_module_aggregation: required_before_system_completion
module_ownership_binding: required_before_handoff_and_completion
swimlane_sync: required_for_verified_flow_change
frontend_click_verification: required_after_frontend_change
local_browser_preview: http_or_https_only
mobile_verification: conditional_on_approved_scope
ui_ux_agent: conditional_on_mapped_high_risk_ui
sensitive_connection_values: explicit_project_authorization_only
authority_matrix_path: AGENTS.md#machine-enforced-authority-matrix
authority_matrix_sha256: aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643
authority_matrix_validation: required_before_delegation_and_completion
```

## Machine-Enforced Authority Matrix

This declaration expands to canonical `expanded-authority-matrix-v1`; unlisted actor/action pairs are denied. Prose cannot override it. Local receipts bind coordination; only strict-security receipts attest the host.

```json
{
  "schema_version":2,
  "contract":"expanded-authority-matrix-v1",
  "scope_binding":"effective-root-agents",
  "module_binding":"registered-module-key-and-owned-paths",
  "run_binding":"local-coordination-or-host-attested-receipts",
  "independent_gate_proof":{"agent_identity":"distinct-from-writer-and-other-gates","run_identity":"distinct-current-coordination-run","status":"completed","verdict":"pass","receipt_path":"required-project-relative-path","receipt_sha256":"required-sha256","candidate_sha256":"required-sha256","code_version":"required","build_id":"required","host_verifier":"optional-strict-security"},
  "default":{"policy":"deny","scope":"repository","module_binding":"registered-module-key","run_binding":"local-coordination-or-host-attested-receipt"},
  "actions":{"route":"module-delivery","write":"project-record","design":"module-delivery","implement":"module-delivery","review":"module-delivery","black-box":"module-delivery","accept":"module-delivery","release":"module-delivery","close":"module-delivery","aggregate":"system-delivery","issue_independent_verdict":"gate-verdict","write_module_artifacts":"module-artifacts","record_completion_after_verified_gates":"module-delivery","write_system_manifest":"system-manifest","orchestrate_read_validate":"system-delivery","bootstrap_system_governance":"system-governance"},
  "policy_overrides":{"dispatcher":{"route":"allow","orchestrate_read_validate":"allow"},"module-maintainer":{"write":"allow","design":"allow","implement":"allow","write_module_artifacts":"allow","record_completion_after_verified_gates":"independent-only"},"independent-reviewer":{"review":"allow","black-box":"allow","accept":"allow","issue_independent_verdict":"allow"},"system-aggregation":{"aggregate":"allow","write_system_manifest":"allow"},"implementation":{"write":"allow","design":"allow","implement":"allow","write_module_artifacts":"allow"},"system-governance-bootstrap":{"bootstrap_system_governance":"external-explicit-only"}},
  "binding_overrides":{"system-governance-bootstrap.bootstrap_system_governance":{"scope":"exact-external-authorized-targets","module_binding":"pending-stable-module-registration","run_binding":"local-coordination-or-host-attested-or-explicit-local-controlled-bootstrap-receipt"}}
}
```

- `independent-only` requires a distinct Agent/run, `completed`/`pass`, receipt/candidate hashes, code version and Build ID; strict mode also requires host verification.
- Bind matrix locator/SHA-256 to caches, trace, bundles, system candidate and receipts. Drift, stale/missing proof, failure or identity reuse blocks completion.
- Each module has one maintainer and non-overlapping paths. Only `allow` writes; writers never self-review, accept, release, close or aggregate.
- Local coordination does not attest the host. Strict security is explicit or mapped high-risk/compliance only; bootstrap is one-time, external, replay/path-bound and grants no business gate authority.

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

## Module Agent Ownership and Dispatcher

Stable Agent titles are ownership names; thread/session/run IDs are runtime evidence and must not enter this AGENTS.md.

| Module | Stable scope | Owned project-relative paths | Long-term maintenance Agent title |
| --- | --- | --- | --- |
| {{MODULE_KEY}} | {{MODULE_SCOPE}} | {{MODULE_OWNED_BOUNDARY}} | {{MODULE_AGENT_TITLE}} |

Ownership cells contain backticked project-relative paths separated only by commas, for example `src/module-a/`, `tests/module-a/`; put API/protocol descriptions in `Stable scope`.

- A major functional module is a stable business capability with an independently testable entry/output contract and non-overlapping ownership boundary; helpers/temporary slices stay inside it and do not create Agents.
- Every major functional module has one independent long-term maintenance Agent closing requirement → design/flow → implementation → targeted tests → independent black-box acceptance → evidence/log and gate-planned swimlane artifacts before completion. `record_completion_after_verified_gates` only records another read-only Agent's passed gates.
- Main, parent, and child placement grants no inherent write authority. The sole writer holds the matching unique active module write lease for module, title, paths and policy hashes. Strict host attestation is explicit or mapped high-risk/compliance only.
- The module maintenance Agent is the sole writer but must not self-certify review/acceptance; a different independent read-only Agent validates the same code/build identity.
- Before cross-module/system completion, every affected module binds current requirement IDs, code/build, targeted tests, independent acceptance, run/latest, applicable mapped swimlane evidence and no open findings. A distinct native GPT-6 `SYSTEM_AGGREGATION` writer emits the system manifest/receipt; Dispatcher only invokes its read-only validator.
- Dispatcher is the user's only entry point for decomposition, routing, orchestration, context transfer, full-flow validation, summaries and new module creation; Dispatcher must not edit business code or shared records.
- Each task has exactly one implementation Agent as writer; all other Agents are read-only. Single-module work uses its leased maintainer; a former Dispatcher uses a different Agent/run and never reuses Dispatcher IDs.
- Update shared plan/progress/trace/context/evidence only through `scripts/update_project_record.py`, bound to writer, lease, target and policy hashes; reject wrong/duplicate identities, drift, cross-module targets and stale CAS.
- A project task may write only inside the canonical project root or its assigned isolated worktree and only within owned paths. Before writing, validate each declared canonical target with `task_write_scope`; a realpath outside that boundary, including symlink escape, fails before mutation.
- For project tasks, global Skill/plugin source roots, caches and direct Skill installs are read-only. Editing requires a dedicated Skill-maintainer task, explicit authorization in the current user request and one exact canonical maintenance source root; hierarchy or a project lease grants nothing.
- Plugin caches and direct Skill installs are derived outputs: update authorized source, validate, use cachebuster/reinstall, and never edit those copies directly.
- The write-scope validator checks declared canonical targets and does not intercept a same-user shell that bypasses it. Claim filesystem-level isolation only when the host enforces a workspace write sandbox, isolated worktree, container, or OS permissions.
- Use distinct Codex-native `gpt-6-astra` Agent/runs: writer `medium`, independent acceptance `high`. Local receipts bind role/module/hashes/output for coordination but do not prove host identity; strict mode adds host verification. Drift, identity reuse or failed evidence blocks completion.
- Dispatcher context packet: user goal, approved requirements/constraints, affected modules/boundaries, input/output contracts, dependencies/risks, verification/acceptance, paths/evidence. Users need not repeat requests; it must not contain full chat, unrelated history or Agent reasoning.
- Dispatcher orchestrates independent read-only gates for full-flow validation, remains read-only and must not self-certify.
- Before implementation, Dispatcher gives each stable new module a unique module key/name, non-overlapping ownership boundary and long-term maintenance Agent/session, registers them, then delegates initialization.

## Verification

- Run nearest tests first. Before explicit or automatically escalated full, create the signed current-candidate freeze proof; run full + mutation at most once per frozen release candidate.
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

- Development plan path: `{{DEVELOPMENT_PLAN_PATH}}`
- Completion progress path: `{{PROGRESS_RECORD_PATH}}`
- Bind the plan to `Baseline version` and `Baseline SHA-256`, and include non-empty `Objective`, `Scope`, `Ordered steps`, `Verification criteria`, and `Known risks`. Bind progress to the current `Run ID` and `Code version`; completion additionally requires `Completion date`, `Delivered result`, `Validation performed`, closed `Remaining work`, and `Status: completed`.
- Before substantial implementation, record the objective, scope, ordered steps, verification criteria, and known risks.
- After completing verified work, record the completion date, delivered result, validation performed, and remaining work.
- Use explicit states such as `pending`, `in_progress`, `completed`, and `blocked`; never mark unexecuted or unverified work as completed.
- Keep sensitive connection values out of these records unless the user explicitly authorizes their project-scoped handling.
- Update shared plan, progress, trace, context and evidence indexes through `{{ATOMIC_RECORD_UPDATE_COMMAND}}`, using a file lock, the expected current SHA-256, and atomic replacement. A stale write must fail and be reread; never let concurrent Agents overwrite each other.

## Requirement Traceability and Delivery Gates

- Stable delivery is the only purpose of process complexity. Before adding an Agent, artifact, gate, context expansion or record, bind verified risk/failure, factual evidence, affected acceptance, observable signal and removal condition. If that mapping is absent, do not add or run it; a hypothetical concern, generic best practice, or one-off anecdote is not enough to create a permanent hard gate.
- `{{DELIVERY_CONTRACT_PATH}}` is the machine decision index. Generate its plan with read-only `{{DELIVERY_GATE_PLANNER_COMMAND}}`, merge only through the leased writer and `{{ATOMIC_RECORD_UPDATE_COMMAND}}`, then run `{{DELIVERY_CONTRACT_VALIDATION_COMMAND}}`. Never hand-edit derived risk/gates or reuse stale receipts; each receipt binds command, input fingerprint, run, verdict and output hash.
- Every task closes the minimum reliable loop: approved objective, scope, non-goals and measurable acceptance → smallest implementation → affected tests and relevant static checks → acceptance evidence. Load extra stages only when mapped; use one verifiable `N/A` reason instead of an empty artifact.
- First prove the smallest end-to-end business flow through a real entry and observable result. Follow `result_candidate -> affected_checks_passed -> baseline_frozen -> hardening -> closure_candidate`; bind the frozen result to code/build, acceptance command/result and evidence hash. Before freeze run only correctness/core-acceptance/irreversible-harm checks; afterward add only mapped hardening. Governance alone is not delivery.
- Hardening preserves the frozen behavior/result. If any later optimization regresses it, stop that optimization, restore or repair the minimum business flow, and rerun the frozen acceptance command before continuing; never weaken requirements or checks to pass.
- Maintain the delivery traceability matrix at `{{REQUIREMENT_TRACEABILITY_PATH}}` with stable `REQ-*`, `FLOW-*`, `FEAT-*`, `UI-*`, `UT-*`, `AT-*`, `MOD-*`, and `BB-*` IDs linking every downstream artifact to its requirement.
- Each trace role has a distinct artifact; files, symlinks or hard links cannot impersonate Requirement, Flow, Feature, UI, Unit-test, Acceptance, Code-module or Black-box roles.
- Before implementation baseline objective, scope, non-goals, constraints and measurable acceptance. Record the baseline artifact, immutable version and SHA-256; bind final black-box evidence to code version, build ID, environment and timezone-aware time.
- Keep `docs/requirements/questions.json` fields `question_id`, `impact_scope`, `risk`, `proposed_default`, `safe_fallback`, `answer_status`, `delivery_disposition`, `assumption`, `owner`, and `review_due`. `NOT_PROVIDED` is reversible, asynchronous `P2 pending` and never blocks continued implementation, verification, acceptance or closure; legal, security, destructive/irreversible or permission risk changes the safe action, not this disposition. On `ANSWERED`, correct the requirement/objective baseline and rerun only affected `impact_scope` gates.
- When requirements/risk make stages applicable, preserve: solution design → system/module swimlanes → feature points → independent UI/UX prototype review for interaction/design changes → test points/unit cases → independently authored complete acceptance cases → implementation → continuous code checks → independent black-box acceptance. Omit inapplicable stages; do not create placeholders.
- Keep Kimi and DeepSeek disabled. Standard work uses `gpt-6-astra`: one assigned writer at `reasoning_effort=medium` and one read-only BLACK_BOX Agent at `reasoning_effort=high`, the sole independent gate on the same candidate hash, combining change/acceptance review and black-box execution. Parent GPT/Dispatcher relays only, with no standard gate. Only mapped high-risk uses `$native-gpt-review-loop` and adds solution-author/adjudication roles. Self-report is not evidence. Six candidate versions without pass are `incomplete` or `blocked`; no secrets or full chat.
- The implementation Agent is the sole code writer; independent Agents stay read-only and receive no full chat, reasoning or self-report as proof.
- Classify and justify `small`, `standard`, or `high-risk`. Behavior/UI/API/mobile/touch/responsive surfaces are at least standard; public API, auth, security, privacy, migration, persistence, async, cross-module and schema are high-risk; unknown stays high-risk until investigated. Small work has known non-observable impact and one registered writer with targeted checks only. Standard work has at most that writer plus one read-only BLACK_BOX acceptance Agent, which combines change review, acceptance-case review and black-box execution. High-risk may add separately mapped specialist roles. Mobile Web/touch/responsive runs browser mobile E2E only when explicitly in scope; native mobile uses its native command; unrelated work does not require mobile adaptation.
- For mapped high-risk UI work, a read-only UI/UX Agent reviews the approved baseline, solution, swimlanes, feature points and prototype without expanding requirements. Define test points/unit cases before implementation; the independent acceptance role covers success, rejection, failure, retry, recovery, permission and boundaries.
- Implement only approved `REQ-*` and `FEAT-*` items. Any new or changed behavior requires a new or updated identifier; before code continues, synchronize only applicable and mapped design, swimlane, UI, test, and acceptance artifacts selected by the gate plan.
- After baseline freeze, run mapped `{{FORMAT_OR_STATIC_CHECK_COMMAND}}` checks before closure; unrelated quality gates must not block the first usable result.
- After implementation, give an independent black-box Agent the approved acceptance cases and a release-like interface, without asking it to modify code or accept the implementation Agent's self-report. Record reproducible evidence for every `BB-*` result.
- Record writer and applicable independent Agent/run IDs plus minimum hashed inputs/outputs. Validate multi-Agent evidence at `{{MULTI_AGENT_EVIDENCE_PATH}}` with `{{MULTI_AGENT_EVIDENCE_VALIDATION_COMMAND}}`; missing/extra roles, reused identities/artifacts, writable reviewers, open defects, failed gates, disagreement or majority vote block closure. Unanswered questions remain non-blocking P2.
- Classify every failure before retrying: route `implementation_defect` to implementation, `requirement_ambiguity` to the requirement baseline, `acceptance_case_defect` to acceptance cases, `environment_blocker` to blocked, and `approved_requirement_change` to a new baseline. Never edit requirements merely to make an implementation defect pass.
- Run the fail-closed semantic trace validator `{{TRACEABILITY_VALIDATION_COMMAND}}` before implementation handoff and again before marking any row or run `completed`. If the validator is missing, cannot run, or reports any error, the gate is `blocked`; do not substitute manual judgment.
- At handoff/completion run `{{DELIVERY_BUNDLE_VALIDATION_COMMAND}}`; contract, trace, questions, plan/progress, commands, AGENTS, current run/latest index, baseline/code/build and automated-review/frontend evidence must agree or remain `blocked`.
- If an independent Agent cannot start, its gate is `blocked` and implementation must not self-certify. Do not mark `completed` until trace, tests, independent acceptance and zero relevant bugs agree.
- Write or update delivery/completion documentation only after all required tests, including independent black-box acceptance, pass for the same candidate.

## Automated Code Review

- Automated review evidence path: `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}`
- Run `{{AUTOMATED_REVIEW_COMMAND}}` only at a module closure candidate or explicit human trigger. Intermediate edits only accumulate current-run deltas. Missing/failed closure review blocks acceptance; a human-triggered snapshot does not stop unrelated implementation.
- Review the actual changed files and their affected callers, callees, public interfaces, configuration, persistence or asynchronous boundaries, tests, requirement trace, and gate-plan-mapped swimlane diagrams. A diff summary or implementation self-report is not sufficient evidence.
- Record every actionable finding with severity, exact file and line, trigger, impact, and executable reproduction or verification. Classify requirement ambiguity separately from implementation defects.
- Route implementation defects to the writer; add a failing regression when applicable, make the smallest root-cause fix, and rerun affected checks. Limit auto-repair to three rounds and two repeats of one failure fingerprint; never edit approved requirements/authority or weaken gates to pass.
- Any code/config change stales a prior review. Store trigger, candidate fingerprint, scope, findings, commands/results and verdict in the declared automated review evidence record; actionable findings, unexplained errors or stale/blocked closure review prevent completion.

## Context and Token Budget

- Default only loads: the effective root-to-scope `AGENTS.md` chain, compact progress index, affected module's current run, and related traceability rows. Then read only directly affected code/tests/configuration/diagrams; `latest.md`, old runs, whole-repository scans and raw logs are not default context.
- Keep `{{CONTEXT_MANIFEST_PATH}}` on disk with baseline/code/build, affected requirements/modules/files/dependencies/commands, effective AGENTS hash and evidence hashes. Validators may read it without placing it in the model prompt.
- Expand the workset only when the change is high-risk, cross-module, changes a public contract, has unknown impact, or when targeted review or tests expose an unresolved dependency. Record the expansion reason in the manifest.
- Reuse evidence only when a completed different run has the same fingerprint: module, code/build, command, configuration hash, environment ID, input hashes and evidence hashes. AGENTS drift, aliases, missing provenance or multi-module worksets make it stale and require rerun. Before expansion/reuse run fail-closed manifest validator `{{CONTEXT_MANIFEST_VALIDATION_COMMAND}}`; failure is `blocked`.
- Store raw command output, screenshots, diffs, and generated files at project paths. In prompts and run summaries record only the command, exit status, concise result counts, fingerprint, and evidence path; do not paste unchanged bulk output.
- Give each independent Agent only its role-specific input manifest and directly linked artifacts; do not send the full chat, all repository documentation, unrelated module logs, or another Agent's reasoning.
- Do not rerun an identical valid fingerprint. Token limits never excuse a required correctness or acceptance gate.

## Modular Execution Logs

- Keep the compact execution index at `{{PROGRESS_RECORD_PATH}}`; it contains only current module status and links to detailed records.
- For cross-module aggregation, configure that progress path and `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}` with literal `<module>` and `<run_id>` so every module run resolves to a different file; single-module projects may use static paths.
- Immutable module run template path: `{{MODULE_EXECUTION_LOG_DIRECTORY}}/<module>/run-<run_id>.md`
- Cross-module runs: `{{SYSTEM_EXECUTION_LOG_DIRECTORY}}/`.
- Assign every run a distinct `run_id` and `code_version`. Use `run_id` for the Agent execution and `code_version` for a Git commit, tag, or build version; never treat them as the same identifier.
- Each run record must include the run ID, module, status, code version, risk level, traceability IDs, changed files, delivered result, automated code review, verification and independent review evidence, remaining risks, and only swimlane records/paths selected by the gate plan.
- After verified completion, update the module's compressed `latest.md` summary and the compact execution index. Do not rewrite immutable historical run records.
- Do not mark a run `completed` until its run record, module `latest.md`, and compact index are synchronized.
- Read the index first; it points to the current immutable run. `latest.md` is a derived completion summary, not default input; read it or older runs only for regression, conflict or historical-decision investigation.
- Reference project paths for raw test output, screenshots, diffs, and generated diagrams instead of pasting large artifacts into execution logs.

## Swimlane Diagram Synchronization

- Classify `swimlane_applicable` and `flow_impact` (`none`, `changed`, or `uncertain`) in current-run evidence from implementation entry/call/interface/config/test facts, not documentation alone. Do not create a separate classification artifact or empty diagram.
- If `swimlane_applicable=true` and `flow_impact=none`, do not rewrite the diagram file and preserve its content and SHA-256. At stage or milestone close, run the registered lightweight `swimlane_freshness` command against the current code/diagram binding and store its gate receipt; do not require the full diagram-redraw/browser evidence path when no diagram changed.
- If `changed`, batch a stabilized candidate and update each affected module diagram at most once per stage/candidate, before its first downstream consumer or handoff. Update sooner only for active safety/security/irreversible/public-contract risk.
- If `flow_impact=uncertain`, perform the minimum entry-point, call-chain, interface, configuration, and test investigation needed to resolve it to `none` or `changed` before downstream use or stage close; must not redraw just in case and must not complete with unresolved impact.
- Update the system overview at `{{SWIMLANE_OVERVIEW_PATH}}` only for verified system/cross-module boundaries, ownership, top-level entry/exit or external dependencies; otherwise update only the module diagram at `{{MODULE_SWIMLANE_PATH}}`. Do not diagram helpers or temporary/test-only slices.
- After an actual diagram write, open the interactive HTML in a browser and click through the affected modules. Verify that lane headers, connectors, module drill-down, and return-to-overview behavior are visible and complete.
- Serve local HTML from a registered loopback `http://`/`https://` preview, bind URL/path and actual/browser body hashes, and never use `file://` or an unrelated page as evidence.
- Record the affected modules, diagram paths, reviewed code evidence, and browser verification result in the current module run, then update the compact completion progress record at `{{PROGRESS_RECORD_PATH}}`.
- Save code/diagram/hash/click binding at `{{SWIMLANE_EVIDENCE_PATH}}` and run `{{SWIMLANE_EVIDENCE_VALIDATION_COMMAND}}`; changed-module coverage, unique paths, visible enabled links/targets, return control and browser transcript must pass.
- A stage or task milestone is not complete and must not be marked `completed` until every `uncertain` impact is resolved, each `changed` diagram is synchronized and verified, and each `none` result has a recorded freshness check without rewriting the diagram.

## Frontend Interaction Verification

- After every frontend code change, use `browser:control-in-app-browser` to exercise the affected user flow with human-like clicks in a desktop PC browser viewport.
- For local pages use the registered server or loopback `http://` preview. Bind entry URL/root/artifact and same-run live response hash; stopped services, `file://`, redirects, decoys and unrelated pages are invalid.
- Run the project's Playwright or Cypress end-to-end command `{{FRONTEND_E2E_COMMAND}}` for the affected flow; if no applicable suite exists, add the smallest maintainable test path or record the missing suite as a blocker.
- Click from the real entry through visible outcome, including applicable failure/retry/recovery. Bind ordered CSS-id actions, browser-computed visibility/enabled state, before/after DOM hashes proving the assertion node changed, and a decodable viewport-sized PNG.
- Only when the approved requirement baseline, supported environment, or affected change scope explicitly includes mobile Web, touch, or responsive browser behavior, repeat the closure in applicable mobile browser viewports and run the corresponding mobile end-to-end cases. Native mobile scope uses the registered native mobile test command instead of browser automation. Otherwise mobile adaptation and mobile verification are not required and must not block completion.
- Confirm there are no console errors, failed required requests, broken controls, clipped critical content, or page-level horizontal overflow in every required viewport; record viewport sizes, click path, assertions, and evidence in the current run.
- The completion-stage application-browser transcript must be executed or independently replayed by the current read-only BLACK_BOX Agent; bind its distinct Agent run ID as the verifier rather than accepting the implementation Agent's self-report.
- Save browser/entry/DOM/screenshot/action/E2E bindings at `{{FRONTEND_EVIDENCE_PATH}}`, then run `{{FRONTEND_EVIDENCE_VALIDATION_COMMAND}}`. Bind candidate, times, URL/root/path/hashes, ordered selectors, viewport, screenshots, exact E2E argv/framework/tests and independent verifier. Stale/missing/reused/fabricated evidence, broken action order/state transition, console/network failures or baseline/code/build mismatch blocks completion.
- If any bug or unexplained error remains, the frontend change is not complete and must not be marked `completed` or passed.

## Project-Specific Rules

- {{STABLE_PROJECT_RULE}}
