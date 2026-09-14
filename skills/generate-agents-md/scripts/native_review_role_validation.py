from __future__ import annotations

from pathlib import Path

from implementation_agent_validation import (
    HostAttestationVerifier,
    Issue,
    _v2_expected_bindings,
    validate_native_spawn_record,
    validate_v2_binding_source,
)
from historical_project_record_authorization import validate_historical_project_record_write_proof
from project_record_authorization import writer_runtime_expectation


def validate_native_review_role_receipts(
    data: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    adjudicator = _adjudicator_expectation(data)
    writer_source = _writer_binding_source(data)
    writer_profile, proof_issues = _validate_writer_write_proof(data, root)
    writer = _writer_expectation(data, writer_source, writer_profile)
    issues = validate_v2_binding_source(
        writer_source, root, require_active_lease=False,
        allow_empty_owned_paths=False, code_prefix="native-loop-writer",
    )
    issues.extend(proof_issues)
    issues.extend(validate_native_spawn_record(
        data=data, root=root, expected=adjudicator,
        path_field="adjudicator_spawn_receipt",
        hash_field="adjudicator_spawn_receipt_sha256",
        code_prefix="native-loop-adjudicator", label="native loop 只读协调裁决 Agent",
        host_attestation_verifier=verifier,
    ))
    issues.extend(validate_native_spawn_record(
        data=data, root=root, expected=writer,
        path_field="writer_spawn_receipt", hash_field="writer_spawn_receipt_sha256",
        code_prefix="native-loop-writer", label="native loop 租约实现/维护 Agent",
        host_attestation_verifier=verifier,
    ))
    return issues


def _adjudicator_expectation(data: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-6-astra",
        "recorded_model": "gpt-6-astra", "agent_id": data.get("adjudicator_agent_id"),
        "requested_reasoning_effort": "high", "recorded_reasoning_effort": "high",
        "run_id": data.get("adjudicator_run_id"), "role": "coordinator-adjudicator",
        "module": data.get("module"), "maintainer_title": "coordinator-adjudicator",
    }


def _writer_binding_source(data: dict[str, object]) -> dict[str, object]:
    return {
        "authority_matrix_sha256": data.get("authority_matrix_sha256"),
        "owned_paths": data.get("writer_owned_paths"),
        "baseline_sha256": data.get("baseline_sha256"),
        "code_version": data.get("code_version"), "build_id": data.get("build_id"),
        "candidate_sha256": data.get("final_candidate_sha256"),
    }


def _writer_expectation(
    data: dict[str, object], writer_source: dict[str, object],
    writer_profile: dict[str, object] | None,
) -> dict[str, object]:
    runtime = writer_runtime_expectation(writer_profile) if writer_profile is not None else {
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol", "requested_reasoning_effort": "medium",
        "recorded_reasoning_effort": "medium",
    }
    writer = {
        "schema_version": 2, "receipt_kind": "codex-native-spawn-result",
        **runtime, "agent_id": data.get("writer_agent_id"),
        "run_id": data.get("writer_run_id"), "role": data.get("writer_role"),
        "module": data.get("module"), "maintainer_title": data.get("maintainer_title"),
    }
    writer.update(_v2_expected_bindings(writer_source, read_only=False, include_active_lease=False))
    writer["historical_write_proof"] = data.get("writer_write_proof")
    return writer


def _validate_writer_write_proof(
    data: dict[str, object], root: Path,
) -> tuple[dict[str, object] | None, list[Issue]]:
    descriptor = data.get("writer_write_proof")
    owned = data.get("writer_owned_paths")
    if (not isinstance(descriptor, dict)
            or set(descriptor) != {"lease_id", "target_path", "path", "sha256"}
            or not isinstance(owned, list)
            or not all(isinstance(item, str) for item in owned)):
        return None, [Issue(
            "error", "native-loop-writer-write-proof-invalid",
            "native loop writer 必须绑定独立历史写入证明与规范 owned_paths",
        )]
    try:
        profile = validate_historical_project_record_write_proof(
            root=root, proof_path=Path(str(descriptor["path"])),
            proof_sha256=str(descriptor["sha256"]),
            target=Path(str(descriptor["target_path"])),
            module_key=str(data.get("module", "")).casefold(),
            maintainer_title=str(data.get("maintainer_title", "")),
            agent_id=str(data.get("writer_agent_id", "")),
            run_id=str(data.get("writer_run_id", "")),
            lease_id=str(descriptor["lease_id"]), owned_paths=owned,
            baseline_sha256=str(data.get("baseline_sha256", "")),
            code_version=str(data.get("code_version", "")),
            build_id=str(data.get("build_id", "")),
            candidate_sha256=str(data.get("final_candidate_sha256", "")),
        )
        writer_runtime_expectation(profile)
    except (RuntimeError, KeyError, TypeError) as error:
        return None, [Issue("error", "native-loop-writer-write-proof-invalid", str(error))]
    return profile, []
