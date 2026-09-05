---
name: multi-model-review-loop
description: Temporarily paused external-review integration. Kimi and DeepSeek provider calls are disabled by policy; keep this Skill explicit-only until the user separately authorizes re-enabling the isolated multi-model review loop. Codex GPT remains available normally.
---

# Multi-model review loop

> **Paused legacy integration:** Kimi and DeepSeek external-provider execution is disabled. Do not invoke, resume, or claim an external review result while `scripts/external_provider_policy.py` keeps `EXTERNAL_PROVIDERS_ENABLED = False`. Use `$native-gpt-review-loop` for the active two-child `gpt-6-astra` workflow. Dry-run inspection remains available.

Run a Kimi -> DeepSeek -> GPT -> Kimi correction loop with explicit evidence and bounded execution. Treat external models as untrusted advisers; keep final scope, single-writer authority, implementation, and acceptance decisions with Codex.

Keep the integration isolated: do not change Codex's default model, login, proxy, global environment, or provider configuration. Read external credentials only inside this skill's subprocess after explicit invocation.

## Preconditions

Load credentials without printing their values. Prefer environment variables when present:

- `MOONSHOT_API_KEY`
- `DEEPSEEK_API_KEY`

On macOS, fall back to Keychain account matching the current OS user and these services:

- `codex-multi-model-review-loop-moonshot`
- `codex-multi-model-review-loop-deepseek`

Use optional `KIMI_MODEL`, `KIMI_BASE_URL`, and `DEEPSEEK_MODEL` overrides. This installed profile defaults to the account-verified Kimi Code model `k3` at `https://api.kimi.com/coding/v1` and DeepSeek `deepseek-v4-pro` at the fixed official base `https://api.deepseek.com`. DeepSeek accepts only `deepseek-v4-pro` or `deepseek-v4-flash`; retired aliases and nonofficial base URLs fail closed. When replacing a key with one from another Kimi product or region, also update the Kimi base URL and re-query `/models`; Kimi Code and Kimi Open Platform keys are not interchangeable.

Use `scripts/call_model.py` only through `spawn_external_agent.py`; it independently rechecks the reserved task root, fixed structured inputs, credential scan, byte budget, and fresh output as defense in depth. The DeepSeek path follows the official OpenAI-compatible V4 Chat Completions profile with thinking enabled, `reasoning_effort=max`, JSON Output, and bounded SSE streaming. Read [references/deepseek-official-integration.md](references/deepseek-official-integration.md) when configuring or diagnosing DeepSeek.

## Isolated external-adviser entry

Use `scripts/spawn_external_agent.py` as the isolated external counterpart to Codex's native sub-Agent scheduling. Each invocation synchronously runs exactly one Kimi or DeepSeek adviser, validates that provider's JSON contract, and writes only into a reserved directory under the system temporary root. The script itself does not provide a persistent agent lifecycle or replace native `spawn_agent`; a host execution session may be used only to wait for or cancel that one subprocess. It rejects workspace output paths and does not change Codex's model, session, login, proxy, environment, tools, or workspace files.

Create a task directory with `mktemp -d /tmp/codex-external-loop.XXXXXX`, then invoke one adviser at a time:

```bash
python3 <skill-dir>/scripts/spawn_external_agent.py kimi \
  --task-id <task_id>-v1-kimi --system-file <kimi-system.txt> \
  --prompt-file <kimi-request.txt> --output-dir <task-dir>/round-1/kimi

python3 <skill-dir>/scripts/spawn_external_agent.py deepseek \
  --task-id <task_id>-v1-deepseek --system-file <deepseek-system.txt> \
  --prompt-file <deepseek-request.txt> --output-dir <task-dir>/round-1/deepseek
```

Kimi must finish before DeepSeek reviews that candidate and authors its black-box cases. Codex GPT may continue unrelated local reasoning or verification while an external subprocess is running, but never expose secrets or mutate the same candidate concurrently. The active GPT alone merges findings, checks black-box coverage, writes and validates the GPT contract, and decides whether another round is required. It may apply an accepted result only when separately authorized and already assigned as the registered maintenance Agent for the current module; a Dispatcher remains read-only. DeepSeek authors cases but does not claim execution; Codex still runs or delegates the real black-box gate.

Before the first run, read [references/review-contracts.md](references/review-contracts.md) completely. Use its JSON contracts and prompts without weakening their evidence requirements.

## Clarify requirements without blocking progress

Before freezing scope, the active GPT must identify material ambiguities that could change the objective, acceptance criteria, interfaces, risk, compatibility, or delivery boundary. Write them to the strict register in [references/clarification-register.template.json](references/clarification-register.template.json), ordered by P0, P1, then P2. Ask no more than 12 questions and omit questions whose answers cannot change implementation or acceptance.

Show the concise question list to the human, but do not stop project progress while waiting. Every open question must include one safe, reversible `proposed_default`, its `risk_if_wrong`, and the exact provisional objective or criterion update. Validate the draft:

```bash
python3 <skill-dir>/scripts/validate_clarifications.py \
  <clarification-register.json> --stage draft
```

If the human answers, record the answer with `resolution_source=human` and revise the objective or exact criterion text. If no answer is available, publish an assumed register and continue:

```bash
python3 <skill-dir>/scripts/validate_clarifications.py \
  <clarification-register.json> --stage draft \
  --apply-defaults-output <clarification-register.assumed.json>
```

An assumed answer is not human approval. Preserve `human_answer=NOT_PROVIDED`, `resolution_source=ai_assumption`, and the visible risk in every prompt and final delivery. Embed the resolved or assumed register in the immutable scope. A later human answer that conflicts with an AI assumption creates a new scope hash, invalidates prior candidate/reviewer passes, and re-runs only the affected work plus downstream gates.

For a long-running or large-output task, also read [references/long-task-reliability.md](references/long-task-reliability.md). Keep full candidates and raw provider responses in the reserved task root, not in chat; resume only from an atomic validated checkpoint. Both providers use bounded streaming, but a disconnect after response bytes begin is blocked rather than silently retried.

Validate the latest atomic checkpoint before resuming:

```bash
python3 <skill-dir>/scripts/validate_checkpoint.py <task-root>/checkpoint.json
```

If a provider response was completely received but normalization or manifest publication was interrupted, rerun the same adviser command with `--resume`. Resume never calls the provider again; a missing raw response blocks and requires an explicitly authorized fresh task ID.

## Establish scope

1. Restate the objective, candidate artifact type, constraints, acceptance criteria, and evidence available. Generate the clarification register, apply human answers or non-blocking defaults, then write the strict scope manifest from `references/review-contracts.md`; assign stable criterion IDs and only the applicable black-box behavior categories.
2. Distinguish analysis from implementation. Draft and revise an isolated candidate unless the user explicitly asks to modify workspace files.
3. Inspect only user-authorized context. Remove secrets, credentials, personal data, and irrelevant files before sending context to external APIs.
4. Create a reserved task-specific directory with `mktemp -d /tmp/codex-external-loop.XXXXXX`. Store the immutable scope, strictly bounded context artifacts, structured prompts, fixed system prompts, round history, raw responses, normalized reports, native GPT evidence, and candidates there. The external runner uses the platform system-temporary root rather than trusting `TMPDIR`; it rejects credentials, oversized inputs, any input/output outside that root, and any symlink component. Do not overwrite the user's source artifact during iteration.
5. Set `max_rounds` to 6 unless the user chooses another integer from 1 through 6. A limit is a safety boundary, never a success condition.

## Run the loop

### 1. Ask Kimi for the initial candidate

Build a prompt using the Kimi draft contract. Include the complete acceptance criteria and only the minimum necessary source context.

Run:

```bash
python3 <skill-dir>/scripts/spawn_external_agent.py kimi \
  --task-id <task_id>-v1-kimi --system-file <kimi-system.txt> \
  --prompt-file <kimi-request.txt> --output-dir <task-dir>/round-1/kimi
```

Validate the response against the contract. If it is invalid, make one repair request that includes validation errors. An invalid response after repair blocks the run; it does not count as a reviewed candidate.

Require the response candidate version to equal the prompt version and task-ID version exactly. A model-generated version increment or decrement is stale output even when the remaining JSON contract is valid.

The fixed provider system prompts include the exact machine-validated output fields and nested shapes. Generate each prompt with `scripts/write_system_prompt.py <provider> <task-root>/<provider>-system.txt`; do not hand-maintain a shorter paraphrase that omits the schema.

`spawn_external_agent.py` validates Kimi and DeepSeek automatically. Use the bundled validator directly for the GPT contract and when independently rechecking an external artifact:

```bash
python3 <skill-dir>/scripts/validate_contract.py gpt <gpt-review.json> --output <gpt-review.normalized.json>
```

### 2. Ask DeepSeek for black-box cases and defect review

Send the current full candidate, objective, acceptance criteria, and evidence. Do not send earlier reviewer conclusions unless needed to check a claimed correction. Require complete observable black-box cases plus defect locations, evidence, impact, and actionable corrections. DeepSeek must label unexecuted cases as authored, never passed.

The runner machine-binds `deepseek-v4-official-chat-completions-bounded-sse-v2`. It rejects legacy model aliases, alternate endpoints, truncated responses, response-model drift, or a stale request profile before the final bundle can pass.

```bash
python3 <skill-dir>/scripts/spawn_external_agent.py deepseek \
  --task-id <task_id>-v1-deepseek --system-file <deepseek-system.txt> \
  --prompt-file <deepseek-request.txt> --output-dir <task-dir>/round-1/deepseek
```

Reject vague style preferences as defects unless they violate an acceptance criterion or create a concrete risk. Treat missing required evidence, contradictions, unsafe assumptions, and unverified completion claims as defects.

### 3. Perform the GPT verification

Use the active Codex GPT to independently inspect the same full candidate and source evidence. Then adjudicate every DeepSeek defect:

- accept it when reproducible or directly supported;
- reject it with a concrete reason when unsupported;
- add defects DeepSeek missed;
- preserve uncertainty as an unresolved defect or explicit blocker;
- never mark an API failure, missing context, or invalid JSON as a pass.

Produce the GPT verification contract and native evidence set from the reference file. Each required check must bind a current task-root evidence file; the native evidence manifest must bind the exact Kimi/DeepSeek inputs, GPT output, active Codex run ID, hashes, provider, and role. Do not ask Kimi or DeepSeek to impersonate GPT, and do not accept a bare unbound GPT JSON file.

Save it and validate it with `validate_contract.py gpt <gpt-review.json>` before deciding whether to pass.

### 4. Decide or revise

Pass only when both conditions hold for the exact same scope and candidate version/hash:

1. DeepSeek returns `pass` with an empty defects array, no uncertainty, and a nonempty black-box case set covering every applicable acceptance criterion.
2. GPT independently returns `pass` with an empty defects array and no blockers.

Run the final machine binding gate; prose agreement is insufficient:

```bash
python3 <skill-dir>/scripts/validate_loop_bundle.py \
  --scope <scope.json> --history <history.json> --kimi <kimi-normalized.json> \
  --deepseek <deepseek-normalized.json> --gpt <gpt-normalized.json> \
  --gpt-evidence <gpt-native-evidence.json> \
  --kimi-manifest <kimi-spawn-result.json> \
  --deepseek-manifest <deepseek-spawn-result.json>
```

The gate rejects empty criterion mappings, incomplete applicable behavior coverage, a revision without an exact accepted-defect change map, missing native GPT checks, raw-provider or usage provenance drift, version/hash drift, reviewer-output replay, or more than six rounds.

Otherwise, merge accepted DeepSeek defects and GPT-added defects into one deduplicated correction request. Put both the ordered IDs in `correction_ids` and the complete exact defect objects in `corrections`; the final bundle gate must match both to the prior GPT decision. Ask Kimi to return a complete revised candidate plus a change map. Do not accept a patch fragment as the new candidate.

Increment the candidate version and repeat DeepSeek review and GPT verification from scratch. Never reuse an earlier pass for a changed candidate.

## Stop conditions

Stop with `passed` only after both reviewers pass the same candidate.

Stop with machine-validated `incomplete` when `max_rounds` is reached and either reviewer still fails. Return the latest candidate, unresolved defects, completed rounds, and the next correction request. Never describe this as defect-free.

Stop with `blocked` after a non-transient API/configuration failure, repeated invalid contract output, missing required evidence, or an authorization boundary. Explain what is needed to resume.

Stop early if the user interrupts, changes scope, or revokes authorization.

## Deliver the result

Return:

- status: `passed`, `incomplete`, or `blocked`;
- final candidate version and location;
- number of completed review rounds;
- DeepSeek and GPT verdicts for the final candidate;
- unresolved defects or blockers;
- unanswered questions continued under AI assumptions, including each default and `risk_if_wrong`;
- validation performed and validation not performed;
- token/usage data when the provider returned it.

Apply a passed proposal to workspace files only when implementation is in scope. For code work, run repository tests and quality gates after applying it; model agreement alone is not runtime verification.
