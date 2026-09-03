# Review contracts

Use these contracts for every loop. JSON values shown as descriptions must be replaced with concrete values. Preserve stable defect IDs across revisions when the same defect remains.

## Clarification register

Before scope is immutable, create the exact register from `clarification-register.template.json`. Ask only material questions and sort them P0, P1, then P2. Human answers use `resolution_source=human`. An unanswered question does not block progress: preserve its recommended default and risk, then use `validate_clarifications.py --apply-defaults-output` to convert it to `status=assumed`, `human_answer=NOT_PROVIDED`, and `resolution_source=ai_assumption`.

Every open question must already contain the exact provisional `objective_update` and/or `criterion_updates` used by its default. An answered question must map to the final objective or exact final criterion text. `confirmed` and `dismissed` questions use `NO_CHANGE` and no criterion updates. Never rewrite an AI assumption as a human answer. When a late human response contradicts an assumption, create a new scope hash and invalidate the affected candidate and reviews.

## Scope manifest

Create one immutable JSON scope before calling either external model. Hash it as canonical UTF-8 JSON with sorted keys and compact separators. Every role must copy that hash into `scope_sha256`.

```json
{
  "schema_version": 1,
  "task_id": "stable-task-id",
  "objective": "complete objective",
  "acceptance_criteria": [
    {
      "id": "AC-001",
      "text": "observable acceptance criterion",
      "behaviors": ["success", "rejection", "failure", "retry", "recovery", "permission", "boundary"]
    }
  ],
  "context_artifacts": [
    {"id": "CTX-001", "content": "minimal redacted source context", "sha256": "SHA-256 of content"}
  ],
  "clarification_register": {
    "schema_version": 1,
    "draft_objective": "initial interpretation",
    "resolved_objective": "complete objective",
    "no_questions_reason": "concrete reason no material question is needed",
    "questions": []
  },
  "max_rounds": 6
}
```

List only applicable behavior categories for each criterion. Keep this scope byte-stable across every round. `max_rounds` must be between 1 and 6.

Each external `--prompt-file` must itself be strict JSON with exactly `schema_version`, `task_id`, `provider`, `candidate_version`, `scope_sha256`, `objective`, `acceptance_criteria`, `context_artifacts`, `clarification_register`, `candidate`, `candidate_sha256`, `correction_ids`, and `corrections`. The clarification register, context artifacts, objective, and criteria must exactly equal the immutable scope, so providers see which decisions came from humans and which are AI assumptions. Context artifacts contain only minimal redacted UTF-8 content and its current SHA-256. A first-round Kimi prompt uses `NOT_APPLICABLE` for both candidate fields and empty correction arrays; a later Kimi prompt contains the prior full canonical candidate, exactly the prior GPT-accepted correction IDs, and the complete accepted defect objects; a DeepSeek prompt contains the current full canonical Kimi candidate and its canonical SHA-256 with empty correction arrays. The system file must exactly equal the fixed role prompt below. Both files must be regular non-symlink files in the same reserved temporary task root as the output. The spawn result binds the raw provider wrapper, requested and returned model, `finish_reason=stop`, response ID, usage, reviewed request profile, prompt/system hashes, and normalized output; the final gate re-derives the normalized contract from that raw response. DeepSeek must use request profile `deepseek-v4-official-chat-completions-bounded-sse-v2`.

## Round history

Maintain one strict `history.json` in the reserved temporary task root. Its `rounds` must be continuous from 1, contain at most `max_rounds` entries, and bind each round's Kimi normalized contract, Kimi spawn manifest, DeepSeek normalized contract, DeepSeek spawn manifest, GPT contract, and native GPT evidence by path and SHA-256. A non-final row is `revised`; its next Kimi `change_map` must exactly match the prior GPT-accepted DeepSeek defects plus GPT-added defects. The final row is `passed` only for the same dual-passed candidate, or `incomplete` only when the configured ceiling is reached with an unresolved reviewer result. Its paths must equal the files submitted to the final bundle validator.

```json
{
  "schema_version": 1,
  "task_id": "stable-task-id",
  "max_rounds": 6,
  "rounds": [
    {
      "round": 1,
      "candidate_version": 1,
      "status": "revised or passed or incomplete",
      "kimi_path": "/tmp/codex-external-loop.X/round-1/kimi/kimi-normalized.json",
      "kimi_sha256": "SHA-256 of that file",
      "kimi_manifest_path": "/tmp/codex-external-loop.X/round-1/kimi/kimi-spawn-result.json",
      "kimi_manifest_sha256": "SHA-256 of that file",
      "deepseek_path": "/tmp/codex-external-loop.X/round-1/deepseek/deepseek-normalized.json",
      "deepseek_sha256": "SHA-256 of that file",
      "deepseek_manifest_path": "/tmp/codex-external-loop.X/round-1/deepseek/deepseek-spawn-result.json",
      "deepseek_manifest_sha256": "SHA-256 of that file",
      "gpt_path": "/tmp/codex-external-loop.X/round-1/gpt-review.json",
      "gpt_sha256": "SHA-256 of that file",
      "gpt_evidence_path": "/tmp/codex-external-loop.X/round-1/gpt-evidence.json",
      "gpt_evidence_sha256": "SHA-256 of that file"
    }
  ]
}
```

## Kimi draft or revision

System prompt:

```text
You are the solution author. Produce a complete candidate that satisfies every supplied acceptance criterion. Do not claim execution or verification you did not perform. Return one JSON object only. On revision, address every accepted defect and return the entire revised candidate, not only a diff. Emit raw JSON: the first character must be { and the last character must be }. Do not use Markdown or code fences. Your JSON object must use exactly these top-level fields and no others: candidate_version, scope_sha256, artifact, assumptions, acceptance_criteria_mapping, change_map, known_limits. candidate_version is a positive integer. scope_sha256 is the supplied lowercase SHA-256. artifact is one complete nonempty string. assumptions and known_limits are arrays of strings. acceptance_criteria_mapping is a nonempty array of objects with exactly criterion, satisfaction, evidence, all strings. Each criterion value must be exactly one supplied acceptance-criterion ID such as AC-001, with no appended title or prose. change_map is an array of objects with exactly defect_id, change, verification, all strings.
```

Output contract:

```json
{
  "candidate_version": 1,
  "scope_sha256": "64 lowercase hexadecimal characters",
  "artifact": "complete proposed solution",
  "assumptions": ["explicit assumption"],
  "acceptance_criteria_mapping": [
    {
      "criterion": "scope criterion ID",
      "satisfaction": "how the candidate satisfies it",
      "evidence": "evidence or NOT_VERIFIED"
    }
  ],
  "change_map": [
    {
      "defect_id": "D-001",
      "change": "specific correction",
      "verification": "evidence or NOT_VERIFIED"
    }
  ],
  "known_limits": ["remaining limitation"]
}
```

For the initial candidate, `change_map` may be empty. Reject omitted criteria, unsupported completion claims, and a revision that contains only partial fragments.

## DeepSeek defect review and black-box cases

System prompt:

```text
You are an adversarial but evidence-bound reviewer and black-box test author. Inspect the complete candidate against the supplied objective, acceptance criteria, constraints, and evidence. A defect must identify a violated criterion or concrete correctness, safety, compatibility, operability, or verification risk. Write complete black-box cases for success, rejection, failure, retry, recovery, permission, and boundary behavior that applies. Do not report subjective preferences as defects or claim that authored cases were executed. Return one JSON object only. Return pass only when no supported defect remains and the black-box case set covers every supplied acceptance criterion. Emit raw JSON: the first character must be { and the last character must be }. Do not use Markdown or code fences. Your JSON object must use exactly these top-level fields and no others: candidate_version, scope_sha256, candidate_sha256, verdict, defects, black_box_tests, coverage, uncertainties. verdict is pass or fail. defects is an array of objects with exactly id, severity, criterion, location, evidence, impact, correction, verification; defect IDs must be unique D-* strings and severity is P0, P1, P2, or P3. black_box_tests is a nonempty array of objects with exactly id, requirement, behavior, preconditions, steps, expected, evidence_required; behavior is success, rejection, failure, retry, recovery, permission, or boundary, the last four fields are nonempty arrays of strings, and every black-box ID is a unique BB-* string. Each requirement value must be exactly one supplied acceptance-criterion ID such as AC-001, with no appended title or prose. coverage must contain each supplied acceptance-criterion ID exactly once and no other string; uncertainties is an array of strings. Do not use black_box_cases, execution_status, a boolean pass field, prose severity names, or an object for coverage. If a concern does not prevent acceptance, such as authored tests being intentionally unexecuted or an implementation-phase value already declared as a known limit, do not list it as an uncertainty. If a concern does prevent acceptance, report it as a concrete defect and return fail.
```

Output contract:

```json
{
  "candidate_version": 1,
  "scope_sha256": "same scope hash as Kimi",
  "candidate_sha256": "canonical SHA-256 of the full normalized Kimi contract",
  "verdict": "pass or fail",
  "defects": [
    {
      "id": "D-001",
      "severity": "P0, P1, P2, or P3",
      "criterion": "violated criterion or risk boundary",
      "location": "smallest identifiable candidate location",
      "evidence": "reproducible evidence from supplied context",
      "impact": "concrete consequence",
      "correction": "specific actionable correction",
      "verification": "how to prove the correction"
    }
  ],
  "black_box_tests": [
    {
      "id": "BB-001",
      "requirement": "scope criterion ID",
      "behavior": "success, rejection, failure, retry, recovery, permission, or boundary",
      "preconditions": ["observable precondition"],
      "steps": ["black-box action through the public interface"],
      "expected": ["observable result"],
      "evidence_required": ["runtime artifact needed to prove the result"]
    }
  ],
  "coverage": ["scope criterion IDs actually reviewed"],
  "uncertainties": ["missing evidence or unresolved uncertainty"]
}
```

`verdict=pass` requires `defects=[]`, `uncertainties=[]`, and a nonempty black-box set covering every applicable acceptance criterion. These are authored cases, not execution evidence; Codex must still run or delegate the real black-box gate. A concern that does not prevent acceptance, such as the cases being intentionally unexecuted or an implementation-phase value already declared as a known limit, must not be listed as an uncertainty. A concern that does prevent acceptance must be reported as a concrete defect with `verdict=fail`.

## GPT verification

Independently review before relying on DeepSeek's conclusions. Use this contract:

```json
{
  "candidate_version": 1,
  "scope_sha256": "same scope hash as Kimi",
  "candidate_sha256": "same candidate hash as DeepSeek",
  "deepseek_review_sha256": "canonical SHA-256 of the full normalized DeepSeek contract",
  "verdict": "pass or fail",
  "deepseek_adjudication": [
    {
      "defect_id": "D-001",
      "decision": "accepted or rejected",
      "reason": "evidence-based reason"
    }
  ],
  "additional_defects": [
    {
      "id": "G-001",
      "severity": "P0, P1, P2, or P3",
      "criterion": "violated criterion or risk boundary",
      "location": "smallest identifiable candidate location",
      "evidence": "reproducible evidence",
      "impact": "concrete consequence",
      "correction": "specific actionable correction",
      "verification": "how to prove the correction"
    }
  ],
  "independent_checks": [
    {
      "check_id": "CHK-001",
      "method": "candidate-inspection",
      "evidence_path": "/reserved/task/root/gpt-check-1.json",
      "evidence_sha256": "64 lowercase hexadecimal characters",
      "status": "passed"
    },
    {
      "check_id": "CHK-002",
      "method": "deepseek-coverage-review",
      "evidence_path": "/reserved/task/root/gpt-check-2.json",
      "evidence_sha256": "64 lowercase hexadecimal characters",
      "status": "passed"
    }
  ],
  "blockers": ["missing authority, context, environment, or evidence"]
}
```

GPT may return `pass` only when every DeepSeek defect is either resolved or evidence-bound rejected, `additional_defects=[]`, `blockers=[]`, and both structured native methods passed. Each check evidence file must use the exact native schema enforced by `validate_loop_bundle.py`, including active task/run/provider/role, current scope/candidate/DeepSeek hashes, method, status, and nonempty observations. A separate native GPT evidence manifest binds a strict input manifest containing the exact Kimi candidate and DeepSeek review paths/hashes to the GPT output path/hash. These files must be distinct regular non-symlink files in the reserved task root and must not reuse external artifacts.

GPT input manifest:

```json
{
  "schema_version": 1,
  "task_id": "stable-task-id-v1-gpt",
  "provider": "codex-native-agent",
  "role": "orchestrator-independent-reviewer",
  "run_id": "stable-native-run-id",
  "candidate_version": 1,
  "scope_sha256": "canonical scope SHA-256",
  "artifacts": [
    {"role": "kimi-candidate", "path": "/tmp/codex-external-loop.X/round-1/kimi/kimi-normalized.json", "sha256": "file SHA-256"},
    {"role": "deepseek-review", "path": "/tmp/codex-external-loop.X/round-1/deepseek/deepseek-normalized.json", "sha256": "file SHA-256"}
  ]
}
```

Each GPT check evidence file:

```json
{
  "schema_version": 1,
  "task_id": "stable-task-id-v1-gpt",
  "provider": "codex-native-agent",
  "role": "orchestrator-independent-reviewer",
  "run_id": "stable-native-run-id",
  "check_id": "CHK-001",
  "candidate_version": 1,
  "scope_sha256": "canonical scope SHA-256",
  "candidate_sha256": "canonical Kimi contract SHA-256",
  "deepseek_review_sha256": "canonical DeepSeek contract SHA-256",
  "method": "candidate-inspection",
  "status": "passed",
  "observations": ["concrete observation from the native review"]
}
```

Use the same schema for `CHK-002` with `method=deepseek-coverage-review`. Native GPT evidence manifest:

```json
{
  "schema_version": 1,
  "task_id": "stable-task-id-v1-gpt",
  "provider": "codex-native-agent",
  "role": "orchestrator-independent-reviewer",
  "run_id": "stable-native-run-id",
  "candidate_version": 1,
  "scope_sha256": "canonical scope SHA-256",
  "candidate_sha256": "canonical Kimi contract SHA-256",
  "deepseek_review_sha256": "canonical DeepSeek contract SHA-256",
  "input_manifest_path": "/tmp/codex-external-loop.X/round-1/gpt-input.json",
  "input_manifest_sha256": "file SHA-256",
  "output_path": "/tmp/codex-external-loop.X/round-1/gpt-review.json",
  "output_sha256": "file SHA-256"
}
```

Before accepting a final result, run `scripts/validate_loop_bundle.py --scope <scope.json> --history <history.json> --kimi <kimi-normalized.json> --deepseek <deepseek-normalized.json> --gpt <gpt-normalized.json> --gpt-evidence <gpt-native-evidence.json> --kimi-manifest <kimi-spawn-result.json> --deepseek-manifest <deepseek-spawn-result.json>`. Use task IDs exactly `<scope.task_id>-v<candidate_version>-kimi`, `<scope.task_id>-v<candidate_version>-deepseek`, and `<scope.task_id>-v<candidate_version>-gpt`. This machine gate proves exact scope/context coverage, applicable behavior coverage, continuous revision provenance, the same candidate version and hash, current raw and normalized external outputs, fixed prompt/system files, complete GPT adjudication/native evidence, the six-round ceiling, and either dual-reviewer pass or an unresolved final `incomplete` exactly at the ceiling.

## Correction request

Send Kimi only deduplicated, accepted defects plus the current full candidate and criteria:

```json
{
  "correction_ids": ["D-001"],
  "corrections": [
    {
      "id": "D-001",
      "severity": "P1",
      "criterion": "AC-001",
      "location": "smallest candidate location",
      "evidence": "reproducible evidence",
      "impact": "concrete consequence",
      "correction": "specific actionable correction",
      "verification": "how to prove the correction"
    }
  ]
}
```
