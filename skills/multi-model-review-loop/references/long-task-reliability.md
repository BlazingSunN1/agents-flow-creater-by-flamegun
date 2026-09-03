# Long-task reliability

Use this profile when one provider call may outlive a normal interactive turn or produce a large candidate. Long duration never weakens provenance or completion gates.

## Budget and transport

- Keep the default provider output budget at 32K tokens. Raise it only when the complete normalized contract cannot fit after removing unrelated context; never exceed 262,144.
- Stream both providers through bounded UTF-8 SSE. Require stable response ID/model, one choice, `finish_reason=stop`, and the final `[DONE]` marker.
- Accept keep-alive comments but never treat them as progress evidence.
- Do not automatically retry after any response byte is received. A partial stream may have consumed provider work and cannot be joined to another response safely.
- Treat `length`, `content_filter`, `tool_calls`, `insufficient_system_resource`, malformed JSON, identity drift, byte-budget overflow, and missing `[DONE]` as blocked output.

## Checkpoints and resumption

Write a checkpoint only after an atomic artifact is fully validated:

1. immutable scope and context hashes;
2. Kimi raw response, normalized candidate, and spawn manifest;
3. DeepSeek raw response, normalized review, and spawn manifest;
4. native GPT evidence and adjudication;
5. validated history row.

After each item above, write and validate `checkpoint.json` with `scripts/validate_checkpoint.py`. The exact top-level fields are `schema_version`, `task_id`, `round`, `candidate_version`, `stage`, `scope_path`, `scope_file_sha256`, `history_path`, `history_sha256`, `artifacts`, and `next_action`. `scope_file_sha256` is the SHA-256 of the exact scope file bytes; the `scope_sha256` inside contracts remains the canonical JSON hash defined in `review-contracts.md`. Each artifact has exactly `role`, `path`, and `sha256`. Stages and next actions are fixed: `scope -> run-kimi`, `kimi -> run-deepseek`, `deepseek -> run-gpt`, and `gpt -> record-history`. Artifact roles are the exact accumulated prefix of `kimi`, `kimi-manifest`, `deepseek`, `deepseek-manifest`, `gpt`, and `gpt-evidence`.

For round one, both history fields are `NOT_APPLICABLE`. A later round binds the complete prior history ending in one validated `revised` row. The checkpoint validator revalidates that history, derives the exact GPT-accepted corrections and prior candidate, and then validates every completed current-round role. After a full row is appended, the final history gate remains authoritative; a partial checkpoint never means `passed`.

Resume from the latest valid checkpoint and continue with its exact `next_action`. If raw provider bytes and the normalized contract exist but manifest publication was interrupted, repeat the same `spawn_external_agent.py` invocation with `--resume`; it validates existing bytes and publishes the missing manifest without a provider recall. If the raw response is absent or partial, block and require an explicitly authorized fresh task ID. Never reconstruct state from chat text, a compacted conversation summary, a partial response, or an unbound candidate copy.

If the active Codex turn is compacted or disconnected, return only a compact checkpoint containing task root, task ID, current round, current state, candidate hash, completed roles, next action, and blockers. Do not print the full candidate or provider response into chat merely to preserve it.

## Version and evidence invariants

- Prompt candidate version, task ID version, provider result version, manifest version, and history round must match exactly.
- DeepSeek must receive and report the current complete Kimi candidate hash.
- A new Kimi response invalidates every earlier DeepSeek/GPT pass.
- A late human answer that changes an AI assumption creates a new scope hash and invalidates affected current/downstream checkpoints; the prior assumption remains in history rather than being rewritten.
- A provider output marked complete means only that its strict contract was received. It does not mean black-box tests ran.
- Real browser, command, unit, and acceptance evidence must be produced by current native execution and bound to the current code/candidate/run.

## Failure handling

- Before response bytes: retry only retryable connection or service failures within the configured retry count.
- After response bytes: record a blocked attempt and start a fresh task ID if the user or GPT authorizes another provider call.
- At the round limit: return `incomplete`, preserving unresolved defects and the next correction request.
- On cancellation or user scope change: stop scheduling new provider calls; never reuse a prior pass for the revised scope.

Long-task acceptance tests must cover a multi-thousand-chunk stream, keep-alives, partial disconnect, missing completion marker, response identity drift, output-budget boundary, version drift, candidate replay, and resume from each atomic checkpoint.
