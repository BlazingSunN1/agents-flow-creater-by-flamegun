from __future__ import annotations

import hashlib
import json
from pathlib import Path

from implementation_agent_validation import (
    HostAttestationVerifier,
    Issue,
    ReceiptReplayState,
    _v2_expected_bindings,
    validate_native_spawn_record,
    validate_v2_binding_source,
)
from native_gate_agent_validation import validate_native_gate_agent


DISPATCHER_IDENTITY = {
    "title": "System Dispatcher",
    "provider": "codex-native-agent",
    "model": "gpt-5.6-sol",
}
AGGREGATION_IDENTITY = {
    "title": "System Aggregation Writer",
    "provider": "codex-native-agent",
    "model": "gpt-5.6-sol",
}
AGGREGATION_RECEIPT_FIELDS = {
    "aggregation_spawn_receipt",
    "aggregation_spawn_receipt_sha256",
}


def system_candidate_payload_sha256(value: dict[str, object]) -> str:
    """Hash the system candidate without the aggregation receipt/hash circular edge."""
    payload = {key: item for key, item in value.items() if key not in AGGREGATION_RECEIPT_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_system_actors(
    value: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    issues: list[Issue] = []
    state = ReceiptReplayState.empty()
    issues.extend(_validate_dispatcher(value, root, verifier, state))
    issues.extend(_validate_aggregation_writer(value, root, verifier, state))
    return issues


def validate_module_gate_actors(
    evidence: dict[str, object], module: str, root: Path,
    verifier: HostAttestationVerifier | None,
) -> tuple[list[Issue], frozenset[str], frozenset[str]]:
    """Re-attest gate actors even when a caller injects a custom module validator."""
    issues = _validate_module_closure(evidence)
    used_agents = {str(evidence.get("implementation_agent_id", ""))}
    used_runs = {str(evidence.get("implementation_run_id", ""))}
    reviewer_agents: set[str] = set()
    reviewer_runs: set[str] = set()
    receipt_state = ReceiptReplayState.empty()
    gates = evidence.get("gates")
    if not isinstance(gates, list):
        return [Issue("error", "system-module-gates-invalid", "模块 gates 必须是数组")], frozenset(), frozenset()
    for raw in gates:
        if not isinstance(raw, dict):
            issues.append(Issue("error", "system-module-gate-invalid", "模块 gate 必须是对象"))
            continue
        role = str(raw.get("role", ""))
        issues.extend(validate_native_gate_agent(
            raw, role, module, root, used_agents, used_runs, verifier, evidence,
            receipt_state,
        ))
        if isinstance(raw.get("agent_id"), str):
            reviewer_agents.add(str(raw["agent_id"]))
        if isinstance(raw.get("run_id"), str):
            reviewer_runs.add(str(raw["run_id"]))
    return issues, frozenset(reviewer_agents), frozenset(reviewer_runs)


def _validate_module_closure(evidence: dict[str, object]) -> list[Issue]:
    """Recheck the non-delegable completion invariants at system scope."""
    issues: list[Issue] = []
    candidate_sha256 = evidence.get("candidate_sha256")
    if (not isinstance(candidate_sha256, str) or len(candidate_sha256) != 64
            or any(character.lower() not in "0123456789abcdef" for character in candidate_sha256)):
        issues.append(Issue(
            "error", "module-candidate-binding-invalid",
            "模块候选绑定必须是 64 位 SHA-256，并由独立门禁输出精确回显",
        ))
    if (evidence.get("stage") != "completion"
            or evidence.get("single_writer_run_id") != evidence.get("implementation_run_id")):
        issues.append(Issue(
            "error", "module-not-closed",
            "模块多 Agent 证据必须处于 completion 且绑定唯一实现 run",
        ))
    if evidence.get("open_disagreements") != []:
        issues.append(Issue(
            "error", "module-open-disagreement",
            "模块多 Agent 证据不得包含开放分歧",
        ))
    gates = evidence.get("gates")
    if not isinstance(gates, list) or not gates:
        issues.append(Issue(
            "error", "module-gates-incomplete",
            "completion 模块必须包含至少一个独立门禁及其封闭 receipt 输出；严格模式追加宿主证明",
        ))
        return issues
    roles = [raw.get("role") for raw in gates if isinstance(raw, dict)]
    if (len(roles) != len(gates) or any(not isinstance(role, str) or not role for role in roles)
            or len(roles) != len(set(roles))):
        issues.append(Issue(
            "error", "module-gates-incomplete",
            "completion 模块的独立门禁角色必须非空且唯一",
        ))
    if any(not isinstance(raw, dict) or raw.get("verdict") != "pass" for raw in gates):
        issues.append(Issue(
            "error", "module-gate-not-pass",
            "completion 模块的每个独立门禁 verdict 必须精确为 pass",
        ))
    return issues


def _validate_dispatcher(
    value: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
    state: ReceiptReplayState,
) -> list[Issue]:
    issues: list[Issue] = []
    if any(value.get(f"dispatcher_{key}") != expected for key, expected in DISPATCHER_IDENTITY.items()):
        issues.append(Issue(
            "error", "system-dispatcher-agent-invalid",
            "Dispatcher 必须声明并绑定为只读原生 gpt-5.6-sol Agent；严格模式追加宿主证明",
        ))
    expected = _base_expected(
        value, prefix="dispatcher", receipt_kind="codex-native-spawn-result",
        role="dispatcher", title=DISPATCHER_IDENTITY["title"],
        read_only=True, owned_paths_field="dispatcher_owned_paths",
        reasoning_effort="xhigh", root=root, issues=issues,
    )
    issues.extend(validate_native_spawn_record(
        data=value, root=root, expected=expected,
        path_field="dispatcher_spawn_receipt",
        hash_field="dispatcher_spawn_receipt_sha256",
        code_prefix="system-dispatcher", label="Dispatcher",
        host_attestation_verifier=verifier,
        receipt_replay_state=state,
    ))
    return issues


def _validate_aggregation_writer(
    value: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
    state: ReceiptReplayState,
) -> list[Issue]:
    issues: list[Issue] = []
    if (value.get("aggregation_writer_role") != "SYSTEM_AGGREGATION"
            or any(value.get(f"aggregation_writer_{key}") != expected
                   for key, expected in AGGREGATION_IDENTITY.items())):
        issues.append(Issue(
            "error", "system-aggregation-agent-invalid",
            "系统聚合写者必须是独立原生 gpt-5.6-sol Agent",
        ))
    expected = _base_expected(
        value, prefix="aggregation_writer", receipt_kind="codex-native-output-result",
        role="system-aggregation", title=AGGREGATION_IDENTITY["title"],
        read_only=False, owned_paths_field="aggregation_writer_owned_paths",
        reasoning_effort="high", root=root, issues=issues,
    )
    expected["candidate_payload_sha256"] = system_candidate_payload_sha256(value)
    expected["authority_binding"] = value.get("authority_binding")
    issues.extend(validate_native_spawn_record(
        data=value, root=root, expected=expected,
        path_field="aggregation_spawn_receipt",
        hash_field="aggregation_spawn_receipt_sha256",
        code_prefix="system-aggregation", label="系统聚合写者",
        host_attestation_verifier=verifier,
        receipt_replay_state=state,
    ))
    return issues


def _base_expected(
    value: dict[str, object], *, prefix: str, receipt_kind: str,
    role: str, title: str, read_only: bool, owned_paths_field: str,
    reasoning_effort: str, root: Path, issues: list[Issue],
) -> dict[str, object]:
    # The system bundle itself has long used schema_version=2.  Receipt schema
    # evolution is explicit so old bundles continue to validate as receipt v1.
    schema_version = value.get("runtime_receipt_schema_version", 1)
    expected = {
        "schema_version": schema_version,
        "receipt_kind": receipt_kind,
        "provider": "codex-native-agent",
        "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol",
        "agent_id": value.get(f"{prefix}_agent_id"),
        "run_id": value.get(f"{prefix}_run_id"),
        "role": role,
        "module": "system",
        "maintainer_title": title,
    }
    if schema_version == 2:
        authority = value.get("authority_binding")
        source = {
            "authority_matrix_sha256": (
                authority.get("sha256") if isinstance(authority, dict) else None
            ),
            "owned_paths": value.get(owned_paths_field),
            "baseline_sha256": value.get("baseline_sha256"),
            "code_version": value.get("code_version"),
            "build_id": value.get("build_id"),
            "candidate_sha256": value.get("candidate_sha256"),
        }
        issues.extend(validate_v2_binding_source(
            source, root, require_active_lease=False,
            allow_empty_owned_paths=read_only, code_prefix=f"system-{role}",
        ))
        expected.update(_v2_expected_bindings(
            source, read_only=read_only, include_active_lease=False,
        ))
        expected.update({
            "requested_reasoning_effort": reasoning_effort,
            "recorded_reasoning_effort": reasoning_effort,
        })
    return expected
