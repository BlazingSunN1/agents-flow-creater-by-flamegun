# Deterministic Delivery Orchestration

Load this reference when creating or updating a delivery contract, choosing validation depth, reusing evidence, or running an automated repair loop.

## One decision index

`docs/governance/delivery-contract.json` is the single machine-readable decision index for a candidate. Start from `assets/delivery-contract.template.json`. It binds the approved baseline, traceability, questions, plan, progress, command manifest, code/build/environment identity, normalized workset, deterministic gate plan, and bounded repair policy by path and SHA-256.

The contract is not a second requirements document, progress log, or evidence transcript. Those artifacts remain authoritative for their own content; the contract only points to their current immutable identity and computes which gates apply. The final delivery-bundle validator must receive this contract and reject any traceability, question list, plan, progress, command manifest, stage, baseline, workset, or candidate identity that differs from the bundle inputs. Human-readable progress and `latest` records may reference the contract, but cannot independently override its gate decision.

## Deterministic planner

Populate facts first, then generate the plan rather than editing it by hand. The planner is read-only and prints only the derived plan; the canonical module writer merges that output into the contract through the registered lease/CAS-protected atomic record updater:

```bash
python3 scripts/plan_delivery_gates.py docs/governance/delivery-contract.json --project-root .
python3 scripts/validate_delivery_contract.py docs/governance/delivery-contract.json --project-root .
```

The planner derives the minimum risk from declared change surfaces, rejects under-classification, sorts outputs, and binds every receipt-bearing required command to a gate-input fingerprint. It separately lists the final aggregate validators in `aggregate_command_ids`. Repeated runs over identical inputs must produce byte-equivalent plan content. A missing, disabled, removed, or manually weakened required command fails closed.

## Result-first staging

Create the first usable outcome before expanding nonessential governance. Drive the smallest approved business flow from a real entry through its core behavior to an observable acceptance result, then run its affected tests and existing relevant static checks. Freeze the passing result as a baseline that binds the exact code version, Build ID, acceptance command, result artifact and evidence SHA-256.

Represent that order in the delivery contract as `result_candidate -> affected_checks_passed -> baseline_frozen -> hardening -> closure_candidate`. `affected_checks_passed`, `baseline_frozen`, and `hardening` require current passing receipts for `real_entry_acceptance` and `targeted_tests`; changing only the delivery phase must not invalidate those business-evidence fingerprints.

Only after that baseline exists may the planner add nonessential gate expansion, broad refactoring, mapped code-quality hardening, performance work or experience polish. Before the first result, permit only checks required for correct execution, affected acceptance, or prevention of irreversible harm. Generic security, architecture and full-suite gates are deferred unless the changed surface or explicit approved scope maps them to the core acceptance. A complete governance bundle or a passing gate without the observable business result does not count as delivery.

Every hardening candidate must replay the frozen acceptance command. A regression stops the optimization path: restore or repair the minimum business flow and regenerate its evidence before any further polishing. Do not change the approved requirement, acceptance meaning or frozen check merely to make a hardened candidate pass.

## Validation tiers

- `quick`: known small implementation work only; package, structure, CLI, syntax, and direct target feedback. It never proves closure.
- `affected`: the default closure-candidate tier for known standard impact. Run with one `--changed-file` per normalized project-relative path. It selects mapped tests and relevant fast checks.
- `full`: final Skill release, high-risk or cross-module change, shared planner/schema change, or any unknown affected mapping. Unknown impact requires full but cannot start it without a signed freeze proof matching the current candidate SHA-256.

For this Skill:

```bash
python3 scripts/validate_skill.py --affected --changed-file scripts/example.py
python3 scripts/validate_skill.py --freeze-candidate
python3 scripts/validate_skill.py --full
```

`--freeze-candidate` first runs quick checks, then writes a signed proof outside the source tree. Explicit full and affected-to-full escalation both fail closed before mutation when the proof is absent, unsigned, malformed, failed, or stale. Any candidate change requires a new proof.

Local plugin release adds a distribution gate after cachebuster update and reinstall:

```bash
python3 scripts/validate_skill.py --full --distribution --require-direct-skills
```

It compares the source package, exact manifest-version cache, and every same-name direct Skill copy required by this maintainer setup. A missing, stale, or shadowing copy fails the release. Plugin-only environments that intentionally keep no direct copies omit `--require-direct-skills`; a package-local pass still cannot replace the cache comparison.

The JSON output records requested and effective tiers plus an escalation reason, so an Agent need not load the full workflow prose to understand the decision.

## Invalidation

The candidate fingerprint binds baseline, requirements-facing artifacts, normalized workset, live code/config/input hashes, identity, and planner version. Each receipt-bearing command gets a separate gate-input fingerprint that also binds that command's exact manifest entry. Run each underlying gate through `python3 scripts/flowctl.py gate ...`; the runner executes the registered argv and emits an immutable schema-v2 `assets/gate-receipt.template.json` receipt containing the exact fingerprint, argv/hash, execution interval, exit code, output path/hash, run ID and pass verdict. Hand-written legacy receipts are invalid. This local runner prevents accidental self-attestation but is not a hostile same-user security boundary; strict host proof remains opt-in. Closure and completion fail when any planned receipt is missing, stale, drifted or belongs to another command. A human-triggered implementation snapshot requires its review receipts plus only the business receipts already required by the reached phase; it does not activate final aggregates. `delivery_contract`, `delivery_bundle`, and `system_delivery_bundle` form a second phase outside this receipt graph: plan and execute them only at closure or completion after underlying receipts exist, and never issue or accept aggregate self-receipts. Updating progress alone does not invalidate unrelated gate inputs; changing a command changes that command binding; changing baseline, workset code, rules, configuration, environment, or input invalidates dependent gates and downstream review/acceptance evidence.

`swimlane_applicable` is a required boolean fact. When false, neither swimlane gate is planned. When true, `flow_impact=none` uses `swimlane_freshness` only at closure; `changed` or `uncertain` uses `swimlane_evidence`, and completion still requires uncertainty to be resolved. Mobile Web and native mobile are separate but composable: `mobile-web`, touch, responsive, or legacy `mobile` with `frontend_applicable=true` uses browser/E2E gates; `native-mobile`, or legacy `mobile` with `frontend_applicable=false`, uses `native_mobile_tests`. A combined Web plus native-mobile change runs both families; native-only scope does not require browser automation.

The command fingerprint hashes the command's source file and recognized project-local execution entrypoints: argv[0], a Python script, or a Python `-m` module/package entrypoint. It does not hash arbitrary argv arguments, which may name generated outputs. Declare imported dependencies, other interpreter entrypoints, and additional test/config inputs through the existing workset `input_files` / `configuration_files`; entrypoint discovery is not a dependency-graph scan.

The runner reserves output and receipt paths exclusively before execution; neither may already exist. A retry must use fresh paths. Failures preserve their diagnostic output; an interrupted execution may leave an empty, invalid receipt, never a passing result. Concurrent attempts cannot reuse the same output pair.

For `targeted_tests`, `frontend_e2e`, `mobile_frontend_e2e`, and `native_mobile_tests`, exit zero alone is insufficient: the captured output must contain a supported native report proving at least one executed test, no failures, and no skipped/pending cases. Supported outputs are unittest's native summary or Playwright/Cypress native JSON (without surrounding log text). `full_test_or_build` defaults to `result_kind: tests`, including wrapper commands; only a real build explicitly registered with `result_kind: build` is exempt from test counts. This optional field is allowed only on that command and is bound by its manifest fingerprint; classify it from the actual command, never to waive failed tests. Business commands do not require test counts. An unsupported runner/report needs an explicit report adapter and remains unverified, not silently passed. The runner and contract validator both use the manifest classification, not a receipt claim.

Mutation validation first requires each distinct test target to load, execute nonzero tests and pass on the unmodified candidate; reuse that baseline only within the current invocation. Only an executed test failure kills a mutant. Missing targets, import/syntax load errors, zero executed tests and worker timeouts invalidate the run rather than count as kills.

The `build` classification cannot exempt a recognizable test-framework invocation or a supported native test report emitted by a build wrapper. Opaque build wrappers still require classification from reviewed command facts; the registry is not a proof of arbitrary program semantics.

Receipts remain immutable. Recompute current fingerprints and mark old receipts stale instead of rewriting history. Any code change after review or black-box acceptance invalidates those downstream conclusions.

`change.deleted_files` is an optional, nonduplicate array of canonical project-relative paths (default `[]`), mirrored by the optional context field `Deleted files`. It is a subset of the complete `changed_files` / `Changed files` workset: a rename lists both old and new paths, with only the old path declared deleted. Deleted targets must actually be absent, with no symlink ancestors or path aliases; their absence is fingerprinted, and restoration invalidates evidence. Deleted configuration belongs in the changed/deleted workset, not the live `configuration_files` or `input_files` lists. Context code fingerprints use `_paths_fingerprint(..., deleted_files=set_of_deleted_paths)`; other fingerprint lists remain live-only. Bundle validation binds the two deletion declarations exactly. This records current absence, not historical proof of deletion or an old-content hash.

Stage alone does not change the business candidate fingerprint. `traceability` and `multi_agent_evidence` additionally bind the stage because their validators have stage-specific semantics; the latter also binds the required independent-role set. Other common receipts remain reusable only while their exact command and candidate inputs stay identical. Final aggregates always execute for the new stage.

Independent review input `artifacts` keep every required deleted path explicitly as `{"path":"old.py","state":"deleted"}`. Only context-declared deletions permit this shape, and current absence is rechecked; ordinary inputs retain the exact `{"path":"live.py","sha256":"..."}` shape. Deleted inputs are not silently removed from review scope.

`Code module` links name files, not directories. For deletion, retain an explicit link to the old path; standalone traceability validation requires `--context` to validate its `Deleted files` declaration, and the bundle passes its canonical context. Only that exact declared absent path in the `Code module` column is exempt from live-file resolution; other columns, undeclared missing paths, and directories remain invalid. Required independent review still explicitly receives each deleted path.

For inapplicable trace artifacts, pass `--delivery-contract` to standalone traceability validation; the bundle forwards its contract automatically. A validated, current, exactly bound plan permits reasoned `N/A` only for selected requirement rows: `Flow` when no swimlane applies and `flow_impact=none`, and `Black-box result` when the plan has no `BLACK_BOX` role. Without a contract, legacy strict behavior remains. This input check does not require traceability's own receipt or prove completion; final contract validation still requires all planned receipts.

## Bounded repair

Automatic repair is conditional, not mandatory. Use it only for formatting, deterministic generated artifacts, or a local implementation defect constrained by a failing regression test. The contract fixes `max_rounds <= 3`, `same_failure_limit <= 2`, regression-before-fix, and completion blocking on exhaustion.

Stop and record an open defect when the same failure fingerprint repeats twice, the candidate fingerprint does not change, a new P0 or security finding appears, or the round limit is reached. Never auto-edit an approved requirement baseline, acceptance criterion, AGENTS authority, permission/security decision, public contract, or destructive operation. Never weaken a test or gate to obtain a pass.

## Agent budget

Do not create an Agent merely because a workflow stage exists. The planner requests independent roles only at closure candidate, completion, high-risk, actual UI interaction/design work, or explicit human-review triggers. Plain user-visible text does not imply UI/UX work. Keep one leased writer; independent roles are read-only and receive only the contract summary, affected requirements/files, exact gate input, and the artifact they must return.
