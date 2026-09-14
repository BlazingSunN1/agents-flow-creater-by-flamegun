# Optional Local Qwen writer policy

Load this reference only when the user explicitly selects Local Qwen as the implementation writer. The default writer remains one native `gpt-5.6-sol/medium` Agent. Local Qwen is a separate closed policy and is never an automatic fallback for an unavailable or mismatched Sol writer.

In this optional mode, the actual local Qwen run is the sole authorized writer for implementation and repair code, tests, scripts, configuration-as-code, and the records it owns. GPT/native Dispatcher and review roles remain read-only. Do not translate Qwen evidence into a Codex-native identity, retain a Sol lease for Qwen-authored bytes, or combine two writers in one task. Same-user local coordination is not OS enforcement.

## Local-only inference, exact model and actual tool-call provenance

1. Connect directly to local Ollama through a literal loopback endpoint; disable environment proxies and redirects. Query installed models and use the exact user-selected local Qwen model. Before sending source, verify local weights and local inference. Endpoint reachability alone is insufficient because a local API may expose remote models.
2. Invoke `POST /api/chat` with the exact model, the approved requirement or defect, only affected source/context, and a request for complete UTF-8 replacement content or an unambiguous minimal patch. The supported model set is exactly `qwen3.8:27b-bf16` and `qwen3.8:27b-q8_0`. Prefer bounded output and streaming for slow local models; record request start/end and preserve the actual response, including the final model and Ollama timing/token fields when supplied. A stream without its successful final completion record is incomplete and cannot authorize a write. Require requested, reported, and target-turn source models to match exactly. Bind the declared reasoning effort to the target Codex `turn_context.effort`; supported values are `none` and `xhigh`. Any client-side mapping of `xhigh` to an Ollama request option such as `max` is request configuration, not model capability or runtime proof, and must not replace the recorded target-turn value. Require the returned target set to match the approved target set exactly; reject missing, duplicate, unrequested, absolute, escaping or linked targets.
3. The Qwen run writes the result with its own file tool call or, only where its tooling has no direct write, its own deterministic byte-preserving application command. Do not use a native controller to author replacement bytes or silently fall back to another provider.

## Scope, canonical root, CAS and lease

Before writing, validate every canonical target with `validate_task_write_scope.py`, bind the current baseline SHA-256, and require the unique active lease to identify the actual Qwen writer. Governed shared records use `update_project_record.py` with the exact target, project root, content file, expected SHA-256, module, Agent/run, lease locator, and lease SHA-256; new files use `--expected-sha256 missing`. Scope, ownership, lease, or CAS drift stops the write. Per-file replacement is not a multi-file crash transaction; after interruption, reread actual state and rebuild the candidate.

## Checks, independent read-only review and native validator incompatibility

Compare applied hashes with the accepted candidate, run affected checks, and use a distinct read-only Agent for independent gates. The Qwen evidence policy remains `local-qwen-writer-v1`, provider `ollama_local`, and its dedicated strict source parser. It does not satisfy `codex-native-sol-writer-v1`; the Sol policy likewise does not satisfy the Qwen schema. Never falsify one provider/model to satisfy the other validator.

## Provenance and failure handling

Record provider `ollama_local`, exact requested/reported model, endpoint, request/response and result hashes, each target's baseline/result SHA-256, and the Qwen run's own identity/tool-call record. Keep raw source and large responses in authorized local evidence storage, not public distribution/default prompts. Local coordination does not attest the host; strict host proof remains separate. Missing provenance, unsupported model/provider, invalid output, or stale scope/CAS remains blocked. Continue only unrelated read-only work until the user explicitly selects a supported writer policy and its exact evidence is available.
