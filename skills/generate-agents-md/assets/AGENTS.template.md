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
delivery_sequence: result_candidate_then_affected_checks_then_freeze_then_mapped_hardening
pre_result_gate_policy: correctness_and_irreversible_only
post_freeze_regression_replay: required
security_gate_policy: mapped_surface_or_explicit_only
automated_review: required_at_module_closure_candidate_or_human_trigger
context_manifest_validation: required_before_expansion_or_reuse
traceability_validation: required_before_handoff_and_completion
delivery_bundle_validation: required_before_handoff_and_completion
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
ui_ux_agent: conditional_on_ui_or_user_visible_change
sensitive_connection_values: explicit_project_authorization_only
authority_matrix_path: AGENTS.md#machine-enforced-authority-matrix
authority_matrix_sha256: aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643
authority_matrix_validation: required_before_delegation_and_completion
```

## Machine-Enforced Authority Matrix

This closed declaration expands to the canonical 96-row `expanded-authority-matrix-v1`. Unlisted actor/action pairs are denied. Delegation or prose cannot override it; local receipts bind coordination, while only strict-security receipts attest the host.

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

- `independent-only` requires a different Agent/run, exact `completed`/`pass`, receipt and candidate hashes, code version, and Build ID. Strict mode additionally requires the external host verifier.
- Bind the matrix locator/SHA-256 into the AGENTS cache key, trace, delivery bundles, system candidate, and receipts. Drift, stale reuse, missing proof, failed verdict, or reused identity blocks completion.
- Each module has one maintenance Agent and non-overlapping owned paths. Only explicit `allow` rows may write; implementation/maintenance never self-review, self-accept, release, close, or aggregate.
- Default local coordination is integrity coordination, not host attestation. Strict security is opt-in for mapped high risk/compliance or explicit selection; its same-user bootstrap is one-time, externally authorized, replay-protected, path-bound, atomic, and grants no business/review/acceptance/aggregation/completion authority.

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

The stable Agent titles in this table are ownership names. Thread IDs, session IDs and transient run IDs are runtime evidence and must not be written into this AGENTS.md.

| Module | Stable scope | Owned project-relative paths | Long-term maintenance Agent title |
| --- | --- | --- | --- |
| {{MODULE_KEY}} | {{MODULE_SCOPE}} | {{MODULE_OWNED_BOUNDARY}} | {{MODULE_AGENT_TITLE}} |

Each ownership cell is machine-readable and must contain one or more project-relative paths, with every path wrapped in backticks and multiple paths separated only by commas, for example `src/module-a/`, `tests/module-a/`. Put API or protocol descriptions in `Stable scope`, never in the ownership cell.

- A major functional module is a stable business capability with an independently testable entry, output contract, and non-overlapping ownership boundary; helpers and temporary task slices remain inside their owning module and do not create extra maintenance Agents.
- Every major functional module has one independent long-term maintenance Agent that maintains its requirement → design/flow → implementation → targeted tests → evidence/log/swimlane chain through successful independent black-box acceptance by a different read-only Agent. This chain must be complete before the module is completed.
- The `record_completion_after_verified_gates` matrix action allows the module maintenance Agent only to record the already-passed result after all applicable independent gates have passed; it does not authorize that Agent to independently adjudicate or close the module delivery.
- Main, parent, and child placement grants no inherent write authority. The sole module writer is the registered implementation/maintenance Agent/run holding the unique active coordination lease that matches module key, Agent/run IDs, title, exact owned paths, and current policy hashes. Default assurance is `delivery-first-local-coordination`; use `strict-security` host attestation only for mapped high-risk/compliance work or explicit human selection.
- The module maintenance Agent may implement an assigned change as the sole writer, but it must not self-certify review or acceptance of its own implementation; a different independent read-only Agent executes the applicable review and black-box gates against the same code/build identity. The preceding lease rule is mandatory for that write authority.
- Cross-module or system work must be split into one independently validated delivery bundle per affected module, written only by that module's registered maintenance Agent. After every affected module closes, a separate native Sol `SYSTEM_AGGREGATION` writer creates the system manifest and binds its canonical candidate payload SHA-256 in a closed output receipt. The Dispatcher only invokes the read-only validator. Dispatcher, aggregation writer, every module maintainer, and every gate reviewer must have globally distinct Agent IDs and run IDs; local mode records their bindings, while strict mode additionally host-attests them. System completion requires every affected module's current requirement IDs, code/build, targeted tests, independent acceptance, run/latest index, applicable flow-change swimlane evidence, and no open finding.
- The Dispatcher Agent is the user's only entry point and only decomposes requirements, routes module work, transfers context between sessions, orchestrates full-flow validation, summarizes results, and creates the maintenance Agent for a stable new module. The Dispatcher role is always read-only. The Dispatcher must not edit business code or write shared project records.
- Every implementation task has exactly one implementation Agent as its sole writer. A single-module task must use the corresponding registered maintenance Agent with the matching active lease. An identity that performed Dispatcher duties must enter implementation only through a separate implementation Agent/run and must not reuse the Dispatcher Agent ID or run ID, combine roles in one run, or self-attest the role transition. Other module maintenance Agents and all independent gate Agents are read-only for code and shared records.
- Every shared plan, progress, trace, context or evidence record update must use `scripts/update_project_record.py` with the canonical module key, the sole active maintainer Agent/run registered in `docs/governance/module-writer-registry.json`, exact target path, current AGENTS/authority-matrix hashes, and its matching lease. The registry rejects Dispatcher/reviewer roles and duplicate active module, Agent, run, or lease identities. Local mode preserves ownership, registry binding, file locking, CAS, and atomic replacement but is explicitly not security attestation; strict mode additionally requires host verification. Missing leases, cross-module targets, ownership or registry drift, or reused identities fail before files change.
- A project task may write only inside the canonical project root or its assigned isolated worktree and only within its owned paths. Before a write, validate every declared target with registered command ID `task_write_scope`; a resolved target outside that boundary, including a symlink escape, fails before mutation.
- For project tasks, global Skill/plugin source roots, Codex plugin caches, and direct Skill installation roots are read-only. Editing one requires a separate dedicated Skill-maintainer task, explicit authorization in the current user request, and one exact canonical maintenance source root; prior authorization, Agent hierarchy, or a project lease does not grant it.
- Plugin cache and direct Skill installs are derived outputs: update authorized source, validate, use cachebuster/reinstall; never edit those copies directly.
- The write-scope validator checks declared canonical targets and does not intercept a same-user shell that bypasses it. Claim filesystem-level isolation only when the host enforces a workspace write sandbox, isolated worktree, container, or OS permissions.
- Every dispatched module-maintenance implementation run and independent gate run must be a distinct Codex-native `gpt-5.6-sol` Agent/run. Implementation and maintenance use `reasoning_effort=high`; review and independent acceptance use `reasoning_effort=xhigh`. In delivery-first mode, closed local receipts bind the requested model, role, Agent/run, module, hashes, and outputs for coordination; they do not prove actual host runtime identity. In strict mode, a trusted current-host verifier must additionally corroborate them. Substitution, drift, reuse, or failed independent evidence blocks completion; absence of strict attestation does not block local delivery unless strict mode is selected.
- The Dispatcher sends the target module Agent a minimal sufficient context packet containing the user goal, approved requirements and constraints, affected modules, ownership boundaries, input/output contracts, dependencies and risks, verification and acceptance criteria, and relevant paths and evidence. The user need not repeat the request in a module session.
- The context packet must not contain the full chat, unrelated history, or another Agent's reasoning; link only the minimum role-relevant artifacts and current evidence.
- The Dispatcher orchestrates full-flow verification through applicable independent read-only roles and only checks and summarizes their evidence; neither the Dispatcher nor the implementation Agent may self-certify an independent gate.
- For a stable new module, the Dispatcher must first allocate a unique module key, name and non-overlapping boundary, create its independent long-term maintenance Agent/session, and register the stable title in this mapping. Before implementation, the non-overlapping ownership must exist; only then may the Dispatcher delegate initialization and implementation. Runtime thread/session IDs stay in runtime evidence, never in this AGENTS.md.

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

- Stable delivery is the only purpose of process complexity. Before adding an Agent, artifact, gate, context expansion or record, bind verified risk/failure, factual evidence, affected acceptance, observable signal and removal condition. If that mapping is absent, do not add or run it; a hypothetical concern, generic best practice, or one-off anecdote is not enough to create a permanent hard gate.
- Maintain `{{DELIVERY_CONTRACT_PATH}}` from `assets/delivery-contract.template.json` as the single machine-readable decision index. It references baseline, trace, questions, plan/progress, commands and current code/build/environment; prose, `latest`, receipts or bundles cannot override it.
- Populate contract facts, run read-only `{{DELIVERY_GATE_PLANNER_COMMAND}}`, and let only the canonical leased writer merge stdout through `{{ATOMIC_RECORD_UPDATE_COMMAND}}`; the planner never writes the contract. Validate with `{{DELIVERY_CONTRACT_VALIDATION_COMMAND}}`. Never hand-edit `gate_plan`, lower derived risk, disable planned commands, or reuse stale-fingerprint receipts. `quick` is feedback; known standard closure uses `affected`; high-risk, cross-module, shared planner/schema, release or unknown mapping uses `full`.
- Each receipt-bearing command stores immutable `assets/gate-receipt.template.json` evidence bound to command ID, gate-input fingerprint, distinct run ID, pass verdict and output hash. `delivery_contract`, `delivery_bundle`, and `system_delivery_bundle` are live second-phase aggregates listed only in `aggregate_command_ids` at closure/completion after underlying receipts; they never accept receipts for themselves or each other. Missing, stale, drifted or wrong-command receipts fail closure. Human-triggered snapshots use review receipts plus business receipts due at that phase; they do not pull aggregates forward.
- Every task closes the minimum reliable loop: approved objective, scope, non-goals and measurable acceptance → smallest implementation → affected tests and relevant static checks → acceptance evidence. Load extra stages only when mapped; use one verifiable `N/A` reason instead of an empty artifact.
- First drive the smallest end-to-end business flow through a real entry, the approved core behavior, and an observable acceptance result. The canonical state order is `result_candidate -> affected_checks_passed -> baseline_frozen -> hardening -> closure_candidate`: run affected checks and freeze the first pass against exact code version, Build ID, acceptance command/result and evidence SHA-256. Only after that freeze may nonessential mapped gates, refactoring, quality, performance or UX work begin. Before it, run only checks needed for correct execution, core acceptance or prevention of irreversible harm; unrelated generic gates stay deferred. Governance or a gate pass alone is not delivered.
- Hardening preserves the frozen behavior/result. If any later optimization regresses it, stop that optimization, restore or repair the minimum business flow, and rerun the frozen acceptance command before continuing; never weaken requirements or checks to pass.
- Maintain the delivery traceability matrix at `{{REQUIREMENT_TRACEABILITY_PATH}}` with stable `REQ-*`, `FLOW-*`, `FEAT-*`, `UI-*`, `UT-*`, `AT-*`, `MOD-*`, and `BB-*` IDs linking every downstream artifact to its requirement.
- Each trace role has a distinct artifact; files, symlinks or hard links cannot impersonate Requirement, Flow, Feature, UI, Unit-test, Acceptance, Code-module or Black-box roles.
- Before implementation baseline objective, scope, non-goals, constraints and measurable acceptance. Record baseline artifact, immutable version and SHA-256; bind final black-box evidence to code version, build ID, environment and timezone-aware time. Maintain `docs/requirements/questions.json` with `question_id`, `impact_scope`, `risk`, `proposed_default`, `safe_fallback`, `answer_status` (`ANSWERED` or `NOT_PROVIDED`), `delivery_disposition=NON_BLOCKING_P2`, `assumption`, `owner`, and timezone-aware `review_due`; validate with `python3 scripts/validate_requirement_questions.py docs/requirements/questions.json --project-root .`.
- Before applicable independent UI/UX, acceptance-case, change-review or black-box work, bind the canonical questions locator/SHA and current baseline in the closed input manifest. Missing, stale, noncanonical, baseline-mismatched or post-hoc evidence fails closed; valid `NOT_PROVIDED` is non-blocking P2, and bound rerun-complete `ANSWERED` may proceed. Strict mode also host-verifies the receipt.
- Every unanswered human question is asynchronous `P2 pending`, never a delivery blocker. Record a reversible minimum-impact proposed default, safe fallback and assumption; request confirmation and continue implementation, verification, acceptance and closure. Legal, security, destructive/irreversible, permission or environment risk changes the safe action but does not block delivery; objectively impossible external action stays unverified. `NOT_PROVIDED` has no answer evidence. On `ANSWERED`, correct the requirement/objective baseline, bind answer plus pre/post baselines, and rerun only affected `impact_scope` gates.
- When requirements/risk make stages applicable, preserve: solution design → system/module swimlanes → feature points → independent UI/UX prototype review for interaction/design changes → test points/unit cases → independently authored complete acceptance cases → implementation → continuous code checks → independent black-box acceptance. Omit inapplicable stages; do not create placeholders.
- Keep Kimi and DeepSeek external providers disabled. For multi-Agent review invoke `$native-gpt-review-loop`: spawn a read-only solution-author and a different read-only black-box-reviewer with `model=gpt-5.6-sol` and `reasoning_effort=xhigh`. A separate read-only coordinator/adjudicator (Codex GPT) also uses `reasoning_effort=xhigh`, independently adjudicates the same candidate and same hash, routes gates, and must use a different Agent ID and run ID from the leased writer, but must not execute or self-certify independent review, black-box, acceptance, or completion. The Dispatcher remains read-only. Only the current module maintenance/implementation Agent/run registered as canonical, using `reasoning_effort=high` and holding its unique active lease, may write; no identity can switch roles. Bind scope, minimum inputs, Agent/run IDs, native spawn/output, requested/actual model and effort, candidate version/hash, and distinct input/output hashes. Child self-report or project-authored receipts do not prove runtime or host trust. Limit the design loop to six candidate versions; same-candidate review yields `reviewed`, not delivery `pass`. Completion needs real black-box execution by another independent Agent/run on the same candidate/code/build; local mode retains a closed coordination receipt and strict mode adds host attestation. Otherwise mark `incomplete` or `blocked`. Never downgrade settings, pass full chat or secrets, or treat authored cases as executed evidence.
- If an applicable independent Agent cannot run, mark its gate `blocked` and it must not self-certify; do not mark delivery completed until trace, tests, independent acceptance, and zero open bugs pass.
- Classify each change as small, standard, or high-risk; record reason and change surfaces. `behavior-change`, `user-visible`, `ui`, `api`, `mobile`, `mobile-web`, `native-mobile`, `touch`, or `responsive` is at least standard; `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, or `data-schema` is high-risk; unknown impact is temporarily high-risk until a minimum factual investigation disproves it. Explicit mobile-Web/touch/responsive scope enables frontend validation and its registered mobile Playwright/Cypress command. Native-mobile-only scope uses the native command without browser applicability; combined scope runs both. Legacy `mobile` is mobile Web only when `frontend_applicable=true`; otherwise native. Unrelated work does not require mobile adaptation. Small work has known impact, no observable behavior, contract or flow change, and targeted verification; Dispatcher reuses the registered module maintenance Agent as sole writer, with no extra review Agent, prototype, swimlane, or full chain. Standard adds only gates mapped to changed behavior. Full multi-Agent governance is reserved for high-risk work, concurrent major modules, or explicit independence/compliance.
- Give the independent UI/UX Agent the approved requirement baseline, solution, swimlanes, and feature points. It may produce or review the prototype and UI states, but it must report ambiguity instead of expanding requirements or modifying implementation code.
- Define test points and applicable unit test cases before implementation. Give a separate acceptance Agent the approved baseline, feature points, UI states, and test points so it authors complete success, rejection, failure, retry, recovery, permission, and boundary cases before implementation begins.
- Implement only approved `REQ-*` and `FEAT-*` items. Any new or changed behavior requires a new or updated identifier and synchronized design, swimlane, UI, test, and acceptance artifacts before code continues.
- After the business baseline is frozen, run the mapped code-standard checks with `{{FORMAT_OR_STATIC_CHECK_COMMAND}}` during hardening and before closure. Formatting, type, lint, complexity, security, and architecture checks are mandatory only when the changed surface, approved scope, or verified failure mode maps them to the affected acceptance; unrelated checks must not block the first usable result.
- After implementation, give an independent black-box Agent the approved acceptance cases and a release-like interface, without asking it to modify code or accept the implementation Agent's self-report. Record reproducible evidence for every `BB-*` result.
- Record distinct implementation and applicable UI/UX, acceptance-case, and black-box Agent run IDs, plus a minimal input manifest and output evidence for each applicable independent gate; a non-UI, non-user-visible change marks UI/UX `N/A` with a verified reason and does not start that Agent. An applicable independent run ID must not equal the implementation run ID or another independent gate run ID.
- When justified, one implementation Agent (`gpt-5.6-sol`, `reasoning_effort=high`) is sole code/shared-record writer. Review, black-box and acceptance Agents use `gpt-5.6-sol`/`reasoning_effort=xhigh`, remain read-only, and receive no full chat, other reasoning or self-report as proof. Do not start black-box acceptance at implementation handoff. Standard work uses independent acceptance/black-box only for observable behavior selected by risk mapping; high-risk work adds change-review, requirement-consistency or domain-specialist Agents only with role-specific evidence mapping. UI/UX requires changed interaction/design. Every extra role needs an approved escalation reason.
- Validate multi-Agent evidence at `{{MULTI_AGENT_EVIDENCE_PATH}}` with `{{MULTI_AGENT_EVIDENCE_VALIDATION_COMMAND}}` using the delivery gate's `implementation` or `completion` stage. Bind every applicable role to a unique run ID, unique minimum input/output paths, hashed evidence and current baseline/code/build; paths match the trace matrix. Missing/extra roles, reused identity/artifact, writable reviewers, open defects, failed gates or unresolved reviewer disagreement are `blocked`; unanswered questions remain non-blocking P2 and are never resolved by majority vote.
- Store strict JSON inputs bound to role, run ID, baseline, affected requirements, minimum role artifacts and their SHA-256, with false full-chat/other-reasoning/self-report flags. Bind outputs to input-manifest SHA-256, role, run ID, baseline, code version, verdict and findings. Reject missing/extra/drifted artifacts, duplicate/unknown fields, boolean/integer aliases, symlink/hard-link aliases, normalized-content reuse, changed/configuration/input-file output reuse, or cross-role reuse.
- Classify every failure before retrying: route `implementation_defect` to implementation, `requirement_ambiguity` to the requirement baseline, `acceptance_case_defect` to acceptance cases, `environment_blocker` to blocked, and `approved_requirement_change` to a new baseline. Never edit requirements merely to make an implementation defect pass.
- Run the fail-closed semantic trace validator `{{TRACEABILITY_VALIDATION_COMMAND}}` before implementation handoff and again before marking any row or run `completed`. If the validator is missing, cannot run, or reports any error, the gate is `blocked`; do not substitute manual judgment.
- At both stages run the aggregate delivery-bundle validator `{{DELIVERY_BUNDLE_VALIDATION_COMMAND}}`; its traceability matrix, questions, plan/progress, commands, stage/workset, AGENTS.md, context manifest, automated-review evidence, current module run, completion-stage `latest.md`, baseline, code version, build, implementation run ID, multi-Agent and applicable frontend evidence must agree with the current contract. Missing or mismatched material is `blocked`.
- If an independent Agent cannot start, its gate is `blocked`; implementation cannot self-certify it. Do not mark `completed` until baseline/code/build, paths, trace, tests, independent acceptance and synchronized artifacts agree with no relevant bug, open finding or unexplained error.

## Automated Code Review

- When a module reaches a closure candidate with implementation, targeted tests, trace and current evidence ready, or when a human explicitly requests review, automatically run `{{AUTOMATED_REVIEW_COMMAND}}` against the current candidate. Intermediate code changes only accumulate changed-file and evidence deltas in the current run; they do not start a review.
- If a triggered review command is missing, cannot run, or reports an error, mark that review `blocked`; do not silently skip it. A blocked closure-candidate review prevents black-box acceptance and completion; a blocked human-triggered snapshot does not stop unrelated implementation work.
- Review the actual changed files and their affected callers, callees, public interfaces, configuration, persistence or asynchronous boundaries, tests, requirement trace, and swimlane diagrams. A diff summary or implementation self-report is not sufficient evidence.
- Record every actionable finding with severity, exact file and line, trigger, impact, and executable reproduction or verification. Classify requirement ambiguity separately from implementation defects.
- Route implementation defects back to implementation, add a failing regression test when applicable, make the smallest root-cause fix, and automatically rerun targeted tests, code standards, trace validation, this review, and the swimlane-impact classification. Validate affected swimlane evidence before its first downstream use and again at stage completion.
- Automatic repair is conditional and bounded by the delivery contract: at most three rounds and two repetitions of the same failure fingerprint. Stop with an open defect when the candidate fingerprint does not change, a new P0/security finding appears, or the budget is exhausted. Never auto-edit approved requirements, acceptance criteria, AGENTS authority, permissions/security decisions or destructive operations, and never weaken tests or gates to manufacture a pass.
- Any code or configuration change after a passing review makes that review stale. At the next module closure candidate, rerun review against the current code fingerprint; a human-triggered snapshot counts for closure only when its fingerprint still matches. Store the trigger, human request reference or `N/A`, implementation run ID, review scope, changed files, code version, commands and results, findings, rerun results, and verdict at `{{AUTOMATED_REVIEW_EVIDENCE_PATH}}`; bind this record through the aggregate delivery validator. Do not enter black-box acceptance or mark the run `completed` while any actionable finding, unexplained error, stale evidence, or blocked closure review remains.

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

- After every code module change, classify both `swimlane_applicable` as boolean and `flow_impact` as `none`, `changed`, or `uncertain` in the existing automated-review or current-run evidence; do not create a separate artifact solely for this classification. Derive the decision from implementation code, entry points, call chains, interfaces, configuration, and tests; documentation alone is not sufficient evidence. When `swimlane_applicable=false`, do not create an empty diagram and do not run either swimlane gate. A `changed` or `uncertain` flow requires `swimlane_applicable=true`.
- If `swimlane_applicable=true` and `flow_impact=none`, do not rewrite the diagram file and preserve its content and SHA-256. At stage or milestone close, run the registered lightweight `swimlane_freshness` command against the current code/diagram binding and store its gate receipt; do not require the full diagram-redraw/browser evidence path when no diagram changed.
- If `flow_impact=changed`, batch all changes for each affected module into one stabilized candidate and update that module diagram at most once per stage and candidate, before the first downstream consumer that relies on the diagram or before stage or milestone handoff, whichever comes first. Update sooner only when stale flow could mislead active safety, security, irreversible-operation, or public-contract work.
- If `flow_impact=uncertain`, perform the minimum entry-point, call-chain, interface, configuration, and test investigation needed to resolve it to `none` or `changed` before downstream use or stage close; must not redraw just in case and must not complete with unresolved impact.
- Update the complete system overview at `{{SWIMLANE_OVERVIEW_PATH}}` only when a verified change affects a system or cross-module boundary, module ownership, top-level entry or exit, cross-module handoff, or external dependency; otherwise update only the affected module diagram at `{{MODULE_SWIMLANE_PATH}}`. Create a missing diagram only for a stable flow used by design, handoff, operations, or acceptance, not for helpers, temporary task slices, or test-only modules.
- After an actual diagram write, open the interactive HTML in a browser and click through the affected modules. Verify that lane headers, connectors, module drill-down, and return-to-overview behavior are visible and complete.
- For local HTML or frontend pages, start the registered preview server on a loopback address, verify its HTTP health URL, and open that `http://` or `https://` URL in the application browser. Require a loopback host and bind the URL path to the current system-diagram path relative to its preview root, the diagram's actual SHA-256, and the browser-observed HTTP response-body SHA-256; never use `file://` or an unrelated HTTP page for automated browser evidence.
- Record the affected modules, diagram paths, reviewed code evidence, and browser verification result in the current module run, then update the compact completion progress record at `{{PROGRESS_RECORD_PATH}}`.
- Save that structured binding at `{{SWIMLANE_EVIDENCE_PATH}}` and run `{{SWIMLANE_EVIDENCE_VALIDATION_COMMAND}}`; the system diagram, every changed module, diagram hashes, exact module-owned Changed-file coverage, path/inode uniqueness, visible and enabled `href` controls to visible matching module target ids, a visible working return-to-overview target, and browser transcript must all validate before delivery.
- A stage or task milestone is not complete and must not be marked `completed` until every `uncertain` impact is resolved, each `changed` diagram is synchronized and verified, and each `none` result has a recorded freshness check without rewriting the diagram.

## Frontend Interaction Verification

- After every frontend code change, use `browser:control-in-app-browser` to exercise the affected user flow with human-like clicks in a desktop PC browser viewport.
- For local pages, use the project's registered development server or a loopback-only static preview command. Register the authoritative entry URL, preview root, and served entry artifact in the project command manifest; browser evidence must match them exactly. Confirm the HTTP endpoint is ready and require the validator's same-run live GET body SHA-256 to equal the entry artifact and recorded response hash; a stopped service, displayed `file://`, decoy file, redirected response, or unrelated HTTP page is not valid automated browser evidence.
- Run the project's Playwright or Cypress end-to-end command `{{FRONTEND_E2E_COMMAND}}` for the affected flow; if no applicable suite exists, add the smallest maintainable test path or record the missing suite as a blocker.
- Use human-like clicks from the real user entry point through state or data changes to the visible result, completing the full interaction closure including applicable validation, failure, retry, and recovery branches. Save a hashed UTF-8 DOM snapshot whose bytes equal the live served entry response; express navigation, click, and assertion targets as CSS id selectors. Every action transcript entry must include browser-computed `visible: true` and `enabled: true`; every declared click and assertion target must appear in the executed action set. Cross-check click selectors against DOM, document-ordered inline/linked CSS cascade including `!important`, ARIA, inert and disabled state. Bind each click to hashed before/after UTF-8 DOM snapshots that prove the declared assertion node itself changed and remains visible. Every screenshot must be a fully decodable PNG whose scanlines and dimensions cover the declared viewport.
- Only when the approved requirement baseline, supported environment, or affected change scope explicitly includes mobile Web, touch, or responsive browser behavior, repeat the closure in applicable mobile browser viewports and run the corresponding mobile end-to-end cases. Native mobile scope uses the registered native mobile test command instead of browser automation. Otherwise mobile adaptation and mobile verification are not required and must not block completion.
- Confirm there are no console errors, failed required requests, broken controls, clipped critical content, or page-level horizontal overflow in every required viewport; record viewport sizes, click path, assertions, and evidence in the current run.
- The completion-stage application-browser transcript must be executed or independently replayed by the current read-only BLACK_BOX Agent; bind its distinct Agent run ID as the verifier rather than accepting the implementation Agent's self-report.
- Save the structured browser, served entry-artifact identity, hashed DOM snapshot, viewport-sized decodable screenshot, hashed tool-action transcript, and native Playwright/Cypress report at `{{FRONTEND_EVIDENCE_PATH}}`, then validate it with `{{FRONTEND_EVIDENCE_VALIDATION_COMMAND}}`; bind browser/E2E run IDs, the independent verifier run ID, parseable ordered timezone-aware start/end times, page URL/preview root/entry path/hash, DOM selectors, transcript viewport plus screenshot paths/hashes, exact E2E argv hash, runner framework, and nonempty identified native tests with terminal states. Resolve inline and project-relative linked CSS in document cascade order, reject unreplayable CSS imports, require every declared action in its exact order and multiplicity, and bind every click to actual before/after DOM artifact hashes whose declared assertion node changes and is visible. Apply the same rules to mobile evidence when mobile is in scope, but require a distinct mobile run ID and distinct transcript/screenshot content hashes. Stale hashes, unrelated pages, missing/non-interactive DOM targets, undersized or structurally invalid screenshots, incomplete/reordered/deduplicated click paths, missing state transitions, failed requests, console errors, fabricated image bytes, summary-only or placeholder reports, reused desktop evidence, or mismatched baseline/code/build block completion.
- If any bug or unexplained error remains, the frontend change is not complete and must not be marked `completed` or passed.

## Project-Specific Rules

- {{STABLE_PROJECT_RULE}}
