from __future__ import annotations

from pathlib import Path

from strict_json import loads as strict_json_loads

from implementation_agent_validation import (
    HostAttestationVerifier,
    Issue,
    ReceiptReplayState,
    _v2_expected_bindings,
    validate_native_spawn_record,
    validate_v2_binding_source,
)


def validate_native_gate_agent(
    gate: dict[str, object], role: str, module: str | None, root: Path,
    agent_ids: set[str], run_ids: set[str],
    host_attestation_verifier: HostAttestationVerifier | None,
    evidence: dict[str, object],
    receipt_replay_state: ReceiptReplayState | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    run_id = _unique_identity(
        gate.get("run_id"), run_ids, "reused-or-missing-agent-run",
        f"{role} 的 run_id 缺失或复用", issues,
    )
    agent_id = _unique_identity(
        gate.get("agent_id"), agent_ids, "reused-or-missing-agent-id",
        f"{role} 的 agent_id 缺失、复用或与维护 Agent 相同", issues,
    )
    if (gate.get("provider") != "codex-native-agent"
            or gate.get("agent_model") != "gpt-6-astra"):
        issues.append(Issue(
            "error", "invalid-gate-agent",
            f"{role} 必须声明并绑定为 Codex 原生 gpt-6-astra 独立 Agent；严格模式追加宿主证明",
        ))
    if gate.get("agent_reasoning_effort") != "high":
        issues.append(Issue("error", "invalid-gate-agent-effort",
                            f"{role} 必须使用 reasoning_effort=high"))
    schema_version = _gate_receipt_schema_version(gate, root, issues)
    expected = _gate_expected(role, module, agent_id, run_id, schema_version)
    if schema_version == 2:
        gate_bindings = dict(evidence)
        gate_bindings.pop("active_write_lease", None)
        issues.extend(validate_v2_binding_source(
            gate_bindings, root, require_active_lease=False,
            allow_empty_owned_paths=False, code_prefix="gate",
        ))
        expected.update(_v2_expected_bindings(
            evidence, read_only=True, include_active_lease=False,
        ))
    elif schema_version != 1:
        issues.append(Issue(
            "error", "invalid-gate-runtime-binding",
            "独立 gate receipt schema_version 必须是整数 1 或 2",
        ))
    issues.extend(_validate_gate_receipts(
        gate, role, root, expected, evidence, host_attestation_verifier,
        receipt_replay_state,
    ))
    return issues


def _gate_receipt_schema_version(
    gate: dict[str, object], root: Path, issues: list[Issue],
) -> object:
    """Read the gate's own receipt version; the enclosing evidence version is unrelated."""
    versions: list[object] = []
    for field in ("spawn_receipt", "output_receipt"):
        relative = gate.get(field)
        if not isinstance(relative, str) or not relative.strip():
            continue
        try:
            path = (root / relative).resolve(strict=True)
            path.relative_to(root.resolve())
            value = strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if isinstance(value, dict):
            versions.append(value.get("schema_version"))
    if len(versions) == 2 and versions[0] == versions[1] and versions[0] in (1, 2):
        return versions[0]
    issues.append(Issue(
        "error", "invalid-gate-runtime-binding",
        "独立 gate 的 spawn/output receipt 必须声明相同的整数 schema_version 1 或 2",
    ))
    return None


def _gate_expected(
    role: str, module: str | None, agent_id: str, run_id: str,
    schema_version: object,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent",
        "requested_model": "gpt-6-astra",
        "recorded_model": "gpt-6-astra",
        "requested_reasoning_effort": "high",
        "recorded_reasoning_effort": "high",
        "agent_id": agent_id,
        "run_id": run_id,
        "role": f"{role.casefold().replace('_', '-')}-gate",
        "module": module,
        "maintainer_title": f"{role} Gate Reviewer",
    }


def _validate_gate_receipts(
    gate: dict[str, object], role: str, root: Path,
    expected: dict[str, object], evidence: dict[str, object],
    host_attestation_verifier: HostAttestationVerifier | None,
    receipt_replay_state: ReceiptReplayState | None,
) -> list[Issue]:
    issues = validate_native_spawn_record(
        data=gate,
        root=root,
        expected=expected,
        path_field="spawn_receipt",
        hash_field="spawn_receipt_sha256",
        code_prefix="gate",
        label=f"{role} 独立验收 Agent",
        host_attestation_verifier=host_attestation_verifier,
        receipt_replay_state=receipt_replay_state,
    )
    output_expected = {
        **expected,
        "receipt_kind": "codex-native-output-result",
        "input_sha256": gate.get("input_sha256"),
        "output_sha256": gate.get("output_sha256"),
        "baseline_version": evidence.get("baseline_version"),
        "code_version": evidence.get("code_version"),
        "build_id": evidence.get("build_id"),
        "candidate_sha256": evidence.get("candidate_sha256"),
        "verdict": gate.get("verdict"),
    }
    issues.extend(validate_native_spawn_record(
        data=gate,
        root=root,
        expected=output_expected,
        path_field="output_receipt",
        hash_field="output_receipt_sha256",
        code_prefix="gate-output",
        label=f"{role} 独立验收输出",
        host_attestation_verifier=host_attestation_verifier,
        record_label="output result",
        invalid_code="invalid-gate-output-receipt",
        receipt_replay_state=receipt_replay_state,
    ))
    return issues


def _unique_identity(
    value: object, used: set[str], code: str, message: str, issues: list[Issue],
) -> str:
    identity = value.strip() if isinstance(value, str) else ""
    if not identity or identity in used:
        issues.append(Issue("error", code, message))
    else:
        used.add(identity)
    return identity
