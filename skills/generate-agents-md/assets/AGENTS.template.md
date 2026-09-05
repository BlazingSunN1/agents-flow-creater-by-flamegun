# Agent Instructions

<!-- PUBLIC TEMPLATE: replace placeholders and remove this comment in project mode. -->

## Project Context

- Purpose: {{PROJECT_PURPOSE}}
- Primary stack: {{PRIMARY_STACK}}
- Supported environment: {{SUPPORTED_ENVIRONMENT}}

## Machine-Enforced Policy

Authoritative policy; project instructions may add detail but must not weaken or contradict it.

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

Expand to canonical `expanded-authority-matrix-v1`; unlisted actor/action pairs are denied. Prose cannot override it.

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

- `independent-only`: distinct Agent/run, `completed`/`pass`, receipt/candidate hashes, code version and Build ID; strict mode requires host verification.
- Bind matrix locator/SHA-256 to caches, trace, bundles, system candidate and receipts. Drift, stale/missing proof, failure or identity reuse blocks completion.
- Only `allow` writes; writers never self-review, accept, release, close or aggregate.
- Local coordination does not attest the host. Strict security is explicit or mapped high-risk/compliance only; bootstrap is one-time, external, replay/path-bound and grants no business gate authority.

## Project Constraints

- {{ARCHITECTURAL_BOUNDARY}}
- {{DATA_OR_COMPATIBILITY_CONSTRAINT}}
- {{SECURITY_OR_PRIVACY_CONSTRAINT}}
- Fix root causes; never hide errors, fabricate results or disable validation.
- Follow existing code; report unrelated problems, fix only when requested.

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

Ownership cells: backticked project-relative paths, comma-separated (`src/module-a/`, `tests/module-a/`); API/protocol details go in `Stable scope`.

- A major functional module is a stable business capability with an independently testable entry/output contract and non-overlapping ownership boundary; helpers/temporary slices stay inside it and do not create Agents.
- Every major functional module has one independent long-term maintenance Agent closing requirement → design/flow → implementation → targeted tests → independent black-box acceptance → evidence/log and gate-planned swimlane artifacts before completion. `record_completion_after_verified_gates` only records another read-only Agent's passed gates.
- Main, parent, and child placement grants no inherent write authority. The writer holds the matching unique active module write lease for module, title, paths and policy hashes.
- The module maintenance Agent is the sole writer but must not self-certify review/acceptance; if gate-planned, a different independent read-only Agent validates the same code/build identity.
- Before cross-module/system completion, every affected module binds current requirement IDs, code/build, targeted tests, independent acceptance, run/latest, applicable mapped swimlane evidence and no open findings. A distinct native GPT-6 `SYSTEM_AGGREGATION` writer emits the system manifest/receipt; Dispatcher only invokes its read-only validator.
- Dispatcher is the user's only entry point for decomposition, routing, orchestration, summaries and new module creation; Dispatcher must not edit business code or shared records.
- Each task has exactly one implementation Agent as sole code writer; all other Agents are read-only. Single-module work uses its leased maintainer; a former Dispatcher uses a different Agent/run and never reuses Dispatcher IDs.
- Shared record updates bind writer, lease, target and policy hashes; reject wrong/duplicate identities, drift and cross-module targets. Use the atomic command under Development Plan and Progress.
- A project task may write only inside the canonical project root or its assigned isolated worktree and only within owned paths. Before writing, validate each declared canonical target with `task_write_scope`; a realpath outside that boundary, including symlink escape, fails before mutation.
- For project tasks, global Skill/plugin source roots, caches and direct Skill installs are read-only. Editing requires a dedicated Skill-maintainer task, explicit authorization in the current user request and one exact canonical maintenance source root; hierarchy or a project lease grants nothing.
- Plugin caches and direct Skill installs are derived outputs: update authorized source, validate, use cachebuster/reinstall, and never edit those copies directly.
- The write-scope validator checks declared canonical targets and does not intercept a same-user shell that bypasses it. Claim filesystem-level isolation only when the host enforces a workspace write sandbox, isolated worktree, container, or OS permissions.
- Local receipts bind role/module/hashes/output, not host identity; strict mode verifies hosts. Models/evidence: Delivery Gates.
- Dispatcher context packet: user goal, approved requirements/constraints, affected modules/boundaries, input/output contracts, dependencies/risks, verification/acceptance, paths/evidence. Users need not repeat requests; it must not contain full chat, unrelated history or Agent reasoning.
- Dispatcher orchestrates independent read-only gates for full-flow validation, remains read-only and must not self-certify.
- Before implementation, Dispatcher registers each stable new module's unique module key/name, non-overlapping ownership boundary and long-term maintenance Agent/session, then delegates initialization.

## Verification

- Run nearest tests first. Before explicit/escalated full, create signed current-candidate freeze proof; run full + mutation at most once per frozen release candidate.
- Test new behavior using applicable repository test structures.
- Claim tests passed only after successful execution of the listed command.
- Command registry: `{{PROJECT_COMMAND_MANIFEST_PATH}}`. Before running evidenced gates, validate with `{{PROJECT_COMMAND_VALIDATION_COMMAND}}`; missing/fabricated/constant-success/shell-wrapped/indirect `env` or command wrappers/undeclared/invalid commands block gates and completion.
- First result only: verified in-scope non-destructive entry may run before registration; provisional, never a passing gate. Before freeze register/validate/rerun for receipts.

```bash
{{TARGETED_TEST_COMMAND}}
{{FULL_TEST_OR_BUILD_COMMAND}}
{{FORMAT_OR_STATIC_CHECK_COMMAND}}
```

## Change Boundaries

- Preserve public APIs, data contracts and compatibility unless explicitly tasked otherwise.
- Update affected docs for public behavior/config/CLI/schema/deployment changes.
- {{PROJECT_SPECIFIC_CHANGE_RULE}}

## Development Plan and Progress

- Development plan path: `{{DEVELOPMENT_PLAN_PATH}}`
- Completion progress path: `{{PROGRESS_RECORD_PATH}}`
- Plan binds `Baseline version`/`Baseline SHA-256` and non-empty `Objective`, `Scope`, `Ordered steps`, `Verification criteria`, `Known risks`; record before substantial implementation.
- Progress binds current `Run ID`/`Code version`; after verified work record `Completion date`, `Delivered result`, `Validation performed`, `Remaining work`, `Status`; completion requires nothing remaining and `Status: completed`.
- States: `pending`, `in_progress`, `completed`, `blocked`; never mark unexecuted/unverified work completed.
- Keep sensitive connection values out of these records unless the user explicitly authorizes their project-scoped handling.
- Update shared plan/progress/trace/context/evidence through `{{ATOMIC_RECORD_UPDATE_COMMAND}}` with a file lock, expected current SHA-256 and atomic replacement. A stale write must fail and be reread; concurrent Agents must not overwrite each other.

## Requirement Traceability and Delivery Gates

- Stable delivery is the only purpose of process complexity. Before adding Agents/artifacts/gates/context/records, map verified risk/failure, factual evidence, acceptance, observable signal and removal condition. Without a mapping, do not add or run it; concerns, best practices or anecdotes alone cannot justify permanent gates.
- `{{DELIVERY_CONTRACT_PATH}}` is the decision index: read-only `{{DELIVERY_GATE_PLANNER_COMMAND}}` → leased writer merges via `{{ATOMIC_RECORD_UPDATE_COMMAND}}` → `{{DELIVERY_CONTRACT_VALIDATION_COMMAND}}`. Never hand-edit derived risk/gates or reuse stale receipts; bind command, input fingerprint, run, verdict and output hash.
- Minimum reliable loop: approved objective/scope/non-goals/measurable acceptance → smallest implementation → affected tests/static checks → acceptance evidence. Extra stages need mapping; inapplicable artifacts need a verifiable `N/A` reason, not empty files.
- First prove the smallest end-to-end business flow through a real entry and observable result. Follow `result_candidate -> affected_checks_passed -> baseline_frozen -> hardening -> closure_candidate`; freeze binds code/build, acceptance command/result and evidence hash. Pre-freeze: correctness/core-acceptance/irreversible-harm checks only; afterward: mapped hardening only. Governance is not delivery.
- Hardening preserves frozen behavior/results. On optimization regression, stop it, restore or repair the minimum business flow, and rerun frozen acceptance before continuing; never weaken requirements/checks to pass.
- Maintain the traceability matrix at `{{REQUIREMENT_TRACEABILITY_PATH}}`: stable `REQ-*`, `FLOW-*`, `FEAT-*`, `UI-*`, `UT-*`, `AT-*`, `MOD-*`, `BB-*` IDs link every downstream artifact to its requirement.
- Each trace role needs a distinct artifact; files, symlinks or hard links cannot impersonate other roles.
- Before implementation, baseline objective/scope/non-goals/constraints/measurable acceptance; record baseline artifact, immutable version and SHA-256. Bind black-box evidence to code version, build ID, environment and timezone-aware time.
- `docs/requirements/questions.json`: `question_id`, `impact_scope`, `risk`, `proposed_default`, `safe_fallback`, `answer_status`, `delivery_disposition`, `assumption`, `owner`, `review_due`. `NOT_PROVIDED`: reversible async `P2 pending`, never blocks continued implementation/verification/acceptance/closure; legal/security/destructive/irreversible/permission risk changes safe action, not disposition. On `ANSWERED`, correct requirement/objective baseline and rerun only affected `impact_scope` gates.
- When applicable, preserve: solution design → system/module swimlanes → feature points → independent UI/UX prototype review → test points/unit cases → independently authored complete acceptance cases → implementation → code checks → independent black-box acceptance. Omit inapplicable stages, not empty placeholders.
- Kimi/DeepSeek disabled. Standard work uses distinct Codex-native `gpt-6-astra` Agent/runs: one assigned writer `reasoning_effort=medium`; one read-only BLACK_BOX `reasoning_effort=high`, sole independent gate for change/acceptance review and black-box execution on the same candidate hash. Parent GPT/Dispatcher relays only, no standard gate. Only mapped high-risk adds `$native-gpt-review-loop` solution-author/adjudication. Six candidate versions without pass: `incomplete` or `blocked`; no self-report proof, secrets or full chat.
- Classify and justify `small`, `standard`, or `high-risk`. Behavior/UI/API/mobile/touch/responsive are at least standard; public API, auth, security, privacy, migration, persistence, async, cross-module and schema are high-risk; unknown stays high-risk until investigated. Small: known non-observable impact, one registered writer, targeted checks only. Standard work uses at most one writer and one read-only BLACK_BOX Agent. High-risk: separately mapped specialist roles only.
- Read-only UI/UX Agent: review mapped high-risk UI against approved baseline/solution/swimlanes/feature points/prototype without expanding requirements. Define test points/unit cases before implementation; independent acceptance covers success/rejection/failure/retry/recovery/permission/boundaries.
- Implement only approved `REQ-*`/`FEAT-*`. New or changed behavior needs a new or updated identifier; before code continues, synchronize only applicable and mapped design/swimlane/UI/test/acceptance artifacts selected by the gate plan.
- After freeze run mapped `{{FORMAT_OR_STATIC_CHECK_COMMAND}}` checks before closure; unrelated quality gates must not block first usable results.
- If BLACK_BOX is planned, give an independent black-box Agent approved acceptance cases and a release-like interface, without allowing it to modify code or accept writer self-report. Record reproducible `BB-*` evidence.
- For planned independent roles, record writer/independent Agent/run IDs and hashed inputs/outputs. Validate multi-Agent evidence at `{{MULTI_AGENT_EVIDENCE_PATH}}` with `{{MULTI_AGENT_EVIDENCE_VALIDATION_COMMAND}}`; missing/extra roles, reused identities/artifacts, writable reviewers, open defects, failed gates, disagreement or majority vote block closure, not unanswered P2.
- Before retrying, route `implementation_defect` → implementation, `requirement_ambiguity` → baseline, `acceptance_case_defect` → acceptance cases, `environment_blocker` → blocked, `approved_requirement_change` → new baseline. Never edit requirements to make an implementation defect pass.
- Run the fail-closed semantic trace validator `{{TRACEABILITY_VALIDATION_COMMAND}}` before implementation handoff and again before marking any row or run `completed`. Missing/unrunnable/error: `blocked`, never manual judgment.
- At handoff/completion run `{{DELIVERY_BUNDLE_VALIDATION_COMMAND}}` only if planned; contract, trace, questions, plan/progress, commands, AGENTS, current run/latest index, baseline/code/build and automated-review/frontend evidence must agree or remain `blocked`.
- If a planned independent Agent cannot start: gate `blocked`, implementation must not self-certify. Do not mark `completed` until trace, tests, applicable independent acceptance and zero relevant bugs agree.
- Write or update delivery/completion documentation only after all required tests, including planned independent black-box acceptance, pass for the same candidate.

## Automated Code Review

- Automated review evidence path: `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}`
- Run `{{AUTOMATED_REVIEW_COMMAND}}` only at module closure candidate or human trigger. Intermediate edits only accumulate run deltas. Missing/failed closure review blocks acceptance; human-triggered snapshots do not stop unrelated implementation.
- Review actual changed files, affected callers/callees, public interfaces, config, persistence/async boundaries, tests, requirement trace and gate-plan-mapped swimlanes; not just a diff summary or writer self-report.
- Findings require severity, exact file/line, trigger, impact and executable reproduction/verification; separate requirement ambiguity from implementation defects.
- Writer repairs defects: add a failing regression when applicable, make the smallest root-cause fix, rerun affected checks. Limit auto-repair to three rounds and two repeats per failure fingerprint; never change approved requirements/authority or weaken gates to pass.
- Code/config changes stale a prior review. Review evidence contains trigger, candidate fingerprint, scope, findings, commands/results and verdict; actionable findings, unexplained errors or stale/blocked closure review prevent completion.

## Context and Token Budget

- Default only loads: effective `AGENTS.md` chain, progress index, module current run, and related traceability rows. Then read directly affected code/tests/config/diagrams; `latest.md`, old runs, whole-repository scans and raw logs are not default context.
- On-disk `{{CONTEXT_MANIFEST_PATH}}`: baseline/code/build, affected requirements/modules/files/dependencies/commands, effective AGENTS hash and evidence hashes; validators read it outside the prompt.
- Expand only for high-risk, cross-module, public contract, unknown impact or unresolved dependencies exposed by review/tests; record the reason in the manifest.
- Reuse only a completed different run's identical fingerprint: module, code/build, command, configuration hash, environment ID, input hashes and evidence hashes. AGENTS drift, aliases, missing provenance or multi-module worksets are stale: rerun. Before expansion/reuse run fail-closed manifest validator `{{CONTEXT_MANIFEST_VALIDATION_COMMAND}}`; failure is `blocked`.
- Store raw command output/screenshots/diffs/generated files at project paths; prompts/run summaries: command, exit status, result counts, fingerprint, evidence path only; do not paste bulk output.
- Read-only independent Agents receive role-specific input manifests/artifacts, not full chat, all repository documentation, unrelated module logs, reasoning or self-report as proof.
- Do not rerun an identical valid fingerprint. Token limits never excuse a required correctness or acceptance gate.

## Modular Execution Logs

- Compact execution index: `{{PROGRESS_RECORD_PATH}}`; current module status and record links only.
- For cross-module aggregation, progress and `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}` paths need literal `<module>`/`<run_id>` to separate module runs; single-module paths may be static.
- Immutable module run template path: `{{MODULE_EXECUTION_LOG_DIRECTORY}}/<module>/run-<run_id>.md`
- Cross-module runs: `{{SYSTEM_EXECUTION_LOG_DIRECTORY}}/`.
- Separate `run_id` (Agent execution) from `code_version` (Git commit/tag/build); never treat them as the same identifier.
- Run fields: run ID, module, status, code version, risk level, traceability IDs, changed files, delivered result, automated code review, verification/independent review evidence, remaining risks; only gate-planned swimlane records/paths.
- After verified completion, update module `latest.md` summary and the compact index; never rewrite immutable historical runs.
- Do not mark a run `completed` until its run record, module `latest.md`, and compact index are synchronized.
- Read index → current immutable run; `latest.md`/history only for regression, conflict or past-decision investigation.
- Reference project paths for test output, screenshots and diffs; do not paste large artifacts into logs.

## Swimlane Diagram Synchronization

- Classify `swimlane_applicable`/`flow_impact` (`none`, `changed`, or `uncertain`) in the current run from implementation entry/call/interface/config/test facts, not documentation alone; no separate classification artifact or empty diagram.
- If `swimlane_applicable=true` and `flow_impact=none`, do not rewrite the diagram file and preserve its content and SHA-256. At stage/milestone close, run registered lightweight `swimlane_freshness` and record its current code/diagram receipt; no redraw/browser evidence for unchanged diagrams.
- If `changed`, batch a stabilized candidate: update affected module diagrams at most once per stage/candidate before first downstream consumer or handoff; sooner only for active safety/security/irreversible/public-contract risk.
- If `flow_impact=uncertain`, investigate entry-point/call-chain/interface/configuration/test facts to resolve `none` or `changed` before downstream use or stage close; must not redraw just in case or complete with unresolved impact.
- Update the system overview at `{{SWIMLANE_OVERVIEW_PATH}}` only for verified system/cross-module boundaries, ownership, top-level entry/exit or external dependencies; otherwise only module diagram `{{MODULE_SWIMLANE_PATH}}`. No helper/temporary/test-only diagrams.
- After an actual diagram write, click through affected modules in the HTML browser: visible lane headers/connectors, module drill-down and return-to-overview must work.
- Serve local HTML from a registered loopback `http://`/`https://` preview, bind URL/path and actual/browser body hashes, and never use `file://` or an unrelated page as evidence.
- Record affected modules, diagram paths, reviewed code evidence and browser verification in the current run; update completion progress at `{{PROGRESS_RECORD_PATH}}`.
- Save code/diagram/hash/click binding at `{{SWIMLANE_EVIDENCE_PATH}}` and run `{{SWIMLANE_EVIDENCE_VALIDATION_COMMAND}}`; changed-module coverage, unique paths, visible enabled links/targets, return control and browser transcript must pass.
- Do not mark a stage/milestone `completed` until every `uncertain` is resolved, `changed` diagram synchronized/verified, and `none` has recorded freshness without rewriting.

## Frontend Interaction Verification

- After every frontend code change, use `browser:control-in-app-browser` to exercise the affected user flow with human-like clicks in a desktop PC browser viewport.
- For local pages use the registered server or loopback `http://` preview. Bind entry URL/root/artifact and same-run live response hash; stopped services, `file://`, redirects, decoys and unrelated pages are invalid.
- Run Playwright or Cypress end-to-end `{{FRONTEND_E2E_COMMAND}}` for the affected flow; if no suite applies, add the smallest maintainable test path or record a blocker.
- Click from the real entry through visible outcome, including applicable failure/retry/recovery. Bind ordered CSS-id actions, browser-computed visibility/enabled state, before/after DOM hashes proving the assertion node changed, and a decodable viewport-sized PNG.
- Only when approved baseline/environment/change scope explicitly includes mobile Web/touch/responsive behavior, repeat closure in applicable mobile browser viewports with mobile end-to-end cases. Native mobile uses its registered native test command, not browser automation. Otherwise mobile adaptation/verification is not required and must not block completion.
- Required viewports: no console errors, failed required requests, broken controls, clipped critical content or page-level horizontal overflow. Log viewport sizes, click path, assertions and evidence.
- Current read-only BLACK_BOX Agent executes or independently replays the completion-stage application-browser transcript; bind its distinct Agent run ID as verifier, not writer self-report.
- Save browser/entry/DOM/screenshot/action/E2E bindings at `{{FRONTEND_EVIDENCE_PATH}}`; then run `{{FRONTEND_EVIDENCE_VALIDATION_COMMAND}}`. Bind candidate/times, URL/root/path/hashes, ordered selectors, viewport, exact E2E argv/framework/tests and independent verifier. Stale/missing/reused/fabricated evidence, broken action order/state transition, console/network failures or baseline/code/build mismatch blocks completion.
- With any bug or unexplained error, do not mark frontend work `completed` or passed.

## Project-Specific Rules

- {{STABLE_PROJECT_RULE}}
