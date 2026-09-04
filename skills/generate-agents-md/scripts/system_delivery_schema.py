from __future__ import annotations

LEGACY_SYSTEM_FIELDS = {
    "schema_version", "dispatcher_mode", "requirement_ids", "code_version", "build_id",
    "agents_path", "agents_sha256", "system_changed_files", "affected_modules",
    "module_bundles", "open_findings", "dispatcher_title", "dispatcher_provider",
    "dispatcher_model", "dispatcher_agent_id", "dispatcher_run_id",
    "dispatcher_spawn_receipt", "dispatcher_spawn_receipt_sha256", "aggregation_writer_role",
    "aggregation_writer_title", "aggregation_writer_provider", "aggregation_writer_model",
    "aggregation_writer_agent_id", "aggregation_writer_run_id",
    "aggregation_spawn_receipt", "aggregation_spawn_receipt_sha256", "authority_binding",
}
RUNTIME_RECEIPT_V2_FIELDS = {
    "runtime_receipt_schema_version", "baseline_sha256", "candidate_sha256",
    "dispatcher_owned_paths", "aggregation_writer_owned_paths",
}
SYSTEM_FIELDS = LEGACY_SYSTEM_FIELDS | RUNTIME_RECEIPT_V2_FIELDS
ENTRY_FIELDS = {"module", "bundle_manifest_path", "bundle_manifest_sha256"}
MODULE_FIELDS = {
    "schema_version", "module", "requirement_ids", "code_version", "build_id",
    "requirement_baseline_version", "requirement_baseline_sha256",
    "maintainer_title", "maintainer_provider", "maintainer_model", "maintainer_reasoning_effort",
    "maintainer_agent_id", "maintainer_spawn_receipt",
    "maintainer_spawn_receipt_sha256", "implementation_run_id", "stage",
    "open_findings", "artifacts", "authority_binding",
}
ARTIFACT_FIELDS = {
    "agents", "trace", "context", "command_manifest", "multi_agent_evidence", "swimlane_evidence", "frontend_evidence",
    "requirement_questions", "requirement_questions_sha256",
}
OPTIONAL_ARTIFACT_FIELDS = {"delivery_contract"}
ARTIFACT_HASH_FIELDS = {"requirement_questions_sha256"}
