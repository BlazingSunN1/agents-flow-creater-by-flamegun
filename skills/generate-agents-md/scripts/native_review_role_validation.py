from __future__ import annotations

from pathlib import Path

from implementation_agent_validation import (
    HostAttestationVerifier,
    Issue,
    validate_native_spawn_record,
)


def validate_native_review_role_receipts(
    data: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    adjudicator = {
        "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol", "agent_id": data.get("adjudicator_agent_id"),
        "requested_reasoning_effort": "xhigh", "recorded_reasoning_effort": "xhigh",
        "run_id": data.get("adjudicator_run_id"), "role": "coordinator-adjudicator",
        "module": data.get("module"), "maintainer_title": "coordinator-adjudicator",
    }
    writer = {
        "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol", "agent_id": data.get("writer_agent_id"),
        "requested_reasoning_effort": "high", "recorded_reasoning_effort": "high",
        "run_id": data.get("writer_run_id"), "role": data.get("writer_role"),
        "module": data.get("module"), "maintainer_title": data.get("maintainer_title"),
    }
    return [
        *validate_native_spawn_record(
            data=data, root=root, expected=adjudicator,
            path_field="adjudicator_spawn_receipt",
            hash_field="adjudicator_spawn_receipt_sha256",
            code_prefix="native-loop-adjudicator", label="native loop 只读协调裁决 Agent",
            host_attestation_verifier=verifier,
        ),
        *validate_native_spawn_record(
            data=data, root=root, expected=writer,
            path_field="writer_spawn_receipt", hash_field="writer_spawn_receipt_sha256",
            code_prefix="native-loop-writer", label="native loop 租约实现/维护 Agent",
            host_attestation_verifier=verifier,
        ),
    ]
