# Agent Interaction Protocol

This reference expands the core interaction rules without creating another delivery state machine. The existing delivery contract and registered `flowctl scope/check/plan/gate/record` validators remain authoritative. Read only the relevant section for a standard or complete task's first handoff, a material change, a blocker, or when version/evidence details are needed. Small tasks use the core rules and do not load this file by default.

## 1. Responsibilities and task sizing

The main Agent owns the full control loop: preserve the user's original objective, analyze requirements, recommend a design, divide executable work, coordinate dependencies and permissions, diagnose returned problems, route bounded repairs, organize independent acceptance, and reconcile every requirement before delivery. It is not a message relay. Delegated Agents execute within the assigned boundary, return real evidence and may challenge a technical approach; they do not silently reinterpret requirements, broaden scope, acquire authority or self-accept.

Use the existing sizing model:

- Small: impact is known, no behavior/contract/flow change exists, and targeted verification is available. Use one writer; one task is sufficient.
- Standard: use at most one writer and one independent read-only BLACK_BOX Agent.
- Complete/high-risk: use only for verified high risk, large concurrent modules, or mapped independence/compliance needs. Add only justified roles and gates.
- Unknown: perform the minimum investigation needed to classify impact; do not invent a fourth tier.

Task sizing never relaxes the unique-writer lease, owned paths, candidate-first rule, independent acceptance, or applicable delivery gates.

## 2. Requirement and design baseline

Before delegation, retain an accessible, versioned reference to the original request or approved requirement baseline. Record stable requirement IDs when the project has them; otherwise state explicit measurable success conditions without creating a new tracking artifact solely for a small task. The main Agent records its recommended approach, boundaries, assumptions and unresolved decisions. Every requirement is either assigned, already covered with evidence, explicitly deferred by authority, or blocked with cause. Absence is never approval, and the main Agent cannot approve a user-facing requirement tradeoff on the user's behalf.

Structural completeness checks cannot establish natural-language semantic correctness. The main Agent remains accountable for whether the design and decomposition actually satisfy the user's meaning.

## 3. First assignment

Required for every delegated implementation:

1. Objective and requirement IDs, or explicit success conditions when no IDs exist.
2. Main Agent's recommended approach and relevant design boundary.
3. Exact scope, owned paths and prohibitions.
4. Inputs, dependencies and accessible version/hash-bound source references.
5. Observable acceptance conditions and applicable validation level.
6. Actual permission, role/model and unique-writer binding supported by the current coordination system.
7. Candidate identifier/path and source or requirement baseline fingerprint.
8. Required return shape and next action.

Conditionally include task/run/interaction IDs, parent revision, event ID, lease reference, external environment, or specialized evidence paths only when the active host/project protocol actually uses them. Do not manufacture files, empty tables, lease claims or identifiers to make a packet look complete. Never refer to “the previous conversation”; either include the necessary fact or cite an accessible stable source.

The main Agent validates dependencies and authorization before dispatch. Unknown task/requirement IDs, dependency cycles, conflicting concurrent ownership and paths outside the granted boundary are blockers under existing scope/lease validation. A small task may remain one task; decomposition exists to make work executable, not to increase Agent count.

## 4. Progress and returned problems

After assignment, communicate only a material scope/requirement delta, a substantive blocker, or a useful stage/result. Do not require receipt acknowledgements, heartbeat reports or unchanged polling. Prefer event-driven completion or a bounded wait. Retrying the same event must preserve its task/run/candidate/version and content; a conflicting reuse is a new event or an error. Timeout is `unknown`, not `failed`, and cannot justify starting another writer.

A returned problem contains:

- Facts and the expected versus actual result.
- Minimal reproduction and evidence reference.
- Verified cause, or clearly labelled hypothesis/unknown.
- Affected scope and whether useful work can continue.
- Blocking status and the next safe action, if known.

The main Agent classifies the problem as `requirement`, `design`, `implementation`, `environment`, or `permission`. It then returns one consolidated repair delta for related findings: reason, exact added/removed/changed scope, minimum repair, regression condition, evidence invalidated by the change, and `continue`, `pause`, or `cancel`. If cause is unknown, authorize bounded investigation before prescribing a fix. Use the existing bounded repair limit; never retry indefinitely, weaken acceptance, widen authority, or let the writer become its own reviewer. Higher-priority host requirements to stop and ask remain controlling.

Users decide real requirement tradeoffs and grant necessary permissions. They should not have to perform technical decomposition or choose among implementation details that the main Agent can safely resolve.

## 5. Version, change and cancellation

Where the host provides task/run/message versions, bind material events to task, run, sender, recipient, revision, parent revision, candidate and event ID. Accept an identical replay idempotently; reject conflicting reuse, stale parents, reordered revisions, wrong recipients, cross-task/run messages and wrong candidates. These are host/protocol fields, not mandatory new files for every small task.

Only the designated main Agent may dispatch work or issue a scope/requirement change. New user requirements return through the main Agent for one controlled version update. Explicit user stop, cancellation or authority revocation is honored immediately. A cancelled or superseded result may be retained as historical evidence but cannot advance current status. Message claims about sender, role, provider, model or effort are not host identity proof; use supported runtime context and existing identity validators where applicable.

A requirement, scope, command, input, candidate or acceptance change invalidates every affected old receipt or review. Record which evidence is invalid and rerun only the mapped checks unless impact is unknown/high-risk or this is a release candidate.

## 6. Acceptance and delivery truth

Interaction status is coordination information only. Do not add a parallel sequence beside `result_candidate -> affected_checks_passed -> baseline_frozen -> hardening -> closure_candidate`. Reuse the existing delivery contract and registered `flowctl scope/check/plan/gate/record` commands.

For each requirement at handoff, report `completed`, `blocked`, or `unverified` with evidence references. A critical requirement can be completed only when a real project entry produced its observable expected result on the current candidate and every applicable independent gate receipt is valid for the same requirement, run, code/build and candidate. The writer's `passed` statement, a non-empty JSON field, a protocol validation result, or a `closure_candidate` label is not acceptance. Existing receipt, contract, multi-Agent and bundle validators determine validity and independent role binding.

Protocol/document validation means only that the described packet follows the documented shape. It does not prove that a host sent the assignment, an Agent executed it, runtime isolation exists, tests passed, or delivery completed. Real messaging and waiting use the configured host transport. Default coordination does not add a network service, daemon, automatic approval, host signature or strict security mode.

Source integration requires the tested candidate's applicable checks, independent acceptance and unchanged source baseline. Candidate or source drift blocks integration; do not roll back concurrent user work. Publishing, cache refresh, installation and marketplace changes require separate authorization.

## 7. Cost and comparison

Use actual runtime/provider metering and keep input, cached-input and output tokens separate. If task/run/Agent attribution is missing, report `unavailable`; event count, message count, character count and cumulative snapshots that cannot be safely deduplicated are not token usage. Do not infer billing, prices or savings without the required measured inputs.

A future controlled comparison may record total main-plus-sub-Agent tokens including retries, end-to-end elapsed time, supplemental dispatch count, rework count and missed-requirement count for equivalent baselines and acceptance. Until such a run exists, label efficiency claims `NOT_MEASURED`. This reference adds no automatic monitor or benchmark command.
