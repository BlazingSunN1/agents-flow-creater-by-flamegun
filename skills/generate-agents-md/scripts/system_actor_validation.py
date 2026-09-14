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
from historical_project_record_authorization import validate_historical_project_record_write_proof
from project_record_authorization import (
    DELIVERY_FIRST_MODE, authorize_project_record_write,
    writer_runtime_expectation,
)


DISPATCHER_IDENTITY = {
    "title": "System Dispatcher",
    "provider": "codex-native-agent",
    "model": "gpt-6-astra",
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
    verifier: HostAttestationVerifier | None, *, manifest_path: Path | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    state = ReceiptReplayState.empty()
    issues.extend(_validate_dispatcher(value, root, verifier, state))
    issues.extend(_validate_aggregation_writer(
        value, root, verifier, state, manifest_path=manifest_path,
    ))
    return issues


def validate_module_gate_actors(
    evidence: dict[str, object], module: str, root: Path,
    verifier: HostAttestationVerifier | None, *, stage: str = "completion",
) -> tuple[list[Issue], frozenset[str], frozenset[str]]:
    """Re-attest gate actors even when a caller injects a custom module validator."""
    issues = _validate_module_closure(evidence, stage)
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


def _validate_module_closure(evidence: dict[str, object], stage: str) -> list[Issue]:
    """Recheck the non-delegable closure invariants at system scope."""
    issues: list[Issue] = []
    candidate_sha256 = evidence.get("candidate_sha256")
    if (not isinstance(candidate_sha256, str) or len(candidate_sha256) != 64
            or any(character.lower() not in "0123456789abcdef" for character in candidate_sha256)):
        issues.append(Issue(
            "error", "module-candidate-binding-invalid",
            "模块候选绑定必须是 64 位 SHA-256，并由独立门禁输出精确回显",
        ))
    if (evidence.get("stage") != stage
            or evidence.get("single_writer_run_id") != evidence.get("implementation_run_id")):
        issues.append(Issue(
            "error", "module-not-closed",
            f"模块多 Agent 证据必须处于 {stage} 且绑定唯一实现 run",
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
            f"{stage} 模块必须包含至少一个独立门禁及其封闭 receipt 输出；严格模式追加宿主证明",
        ))
        return issues
    roles = [raw.get("role") for raw in gates if isinstance(raw, dict)]
    if (len(roles) != len(gates) or any(not isinstance(role, str) or not role for role in roles)
            or len(roles) != len(set(roles))):
        issues.append(Issue(
            "error", "module-gates-incomplete",
            f"{stage} 模块的独立门禁角色必须非空且唯一",
        ))
    if any(not isinstance(raw, dict) or raw.get("verdict") != "pass" for raw in gates):
        issues.append(Issue(
            "error", "module-gate-not-pass",
            f"{stage} 模块的每个独立门禁 verdict 必须精确为 pass",
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
            "Dispatcher 必须声明并绑定为只读原生 gpt-6-astra Agent；严格模式追加宿主证明",
        ))
    expected = _base_expected(
        value, prefix="dispatcher", receipt_kind="codex-native-spawn-result",
        role="dispatcher", title=DISPATCHER_IDENTITY["title"],
        read_only=True, owned_paths_field="dispatcher_owned_paths",
        reasoning_effort="high", model="gpt-6-astra", root=root, issues=issues,
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
    state: ReceiptReplayState, *, manifest_path: Path | None,
) -> list[Issue]:
    issues: list[Issue] = []
    runtime, authority_issues = _validate_aggregation_write_authority(value, root, manifest_path)
    if runtime is None:
        runtime = {
            "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol", "requested_reasoning_effort": "medium",
            "recorded_reasoning_effort": "medium",
        }
    if (value.get("aggregation_writer_role") != "SYSTEM_AGGREGATION"
            or value.get("aggregation_writer_title") != AGGREGATION_IDENTITY["title"]
            or value.get("aggregation_writer_provider") != runtime["provider"]
            or value.get("aggregation_writer_model") != runtime["requested_model"]):
        issues.append(Issue(
            "error", "system-aggregation-agent-invalid",
            "系统聚合写者必须与已验证 writer policy 精确一致",
        ))
    expected = _base_expected(
        value, prefix="aggregation_writer", receipt_kind="codex-native-output-result",
        role="system-aggregation", title=AGGREGATION_IDENTITY["title"],
        read_only=False, owned_paths_field="aggregation_writer_owned_paths",
        reasoning_effort=runtime["requested_reasoning_effort"],
        model=runtime["requested_model"], root=root, issues=issues,
        provider=runtime["provider"], recorded_model=runtime["recorded_model"],
        recorded_reasoning_effort=runtime["recorded_reasoning_effort"],
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
    if value.get("runtime_receipt_schema_version") != 2:
        issues.append(Issue(
            "error", "system-aggregation-runtime-binding-invalid",
            "可写系统聚合 Agent 必须使用 runtime receipt schema 2",
        ))
    issues.extend(authority_issues)
    return issues


def _validate_aggregation_write_authority(
    value: dict[str, object], root: Path, manifest_path: Path | None,
) -> tuple[dict[str, str] | None, list[Issue]]:
    if manifest_path is None:
        return None, [Issue("error", "system-manifest-target-missing", "schema-v2 系统聚合必须绑定清单路径")]
    try:
        target = manifest_path.resolve().relative_to(root.resolve())
    except ValueError:
        return None, [Issue("error", "system-manifest-target-unsafe", "系统清单必须位于项目根内")]
    descriptors = _aggregation_write_descriptors(value, target)
    if isinstance(descriptors, list):
        return None, descriptors
    live, history, owned, agent, run = descriptors
    history_runtime, history_issues = _historical_aggregation_authority(
        value, root, history, owned, agent, run,
    )
    if history_runtime is None:
        return None, history_issues
    live_runtime, live_issues = _live_aggregation_authority(
        value, root, target, live, agent, run, history_runtime,
    )
    if live_runtime is None:
        return None, live_issues
    return history_runtime, []


def _aggregation_write_descriptors(
    value: dict[str, object], target: Path,
) -> tuple[dict[str, object], dict[str, object], list[str], str, str] | list[Issue]:
    live = value.get("aggregation_manifest_write_lease")
    history = value.get("aggregation_receipt_write_proof")
    if (not isinstance(live, dict) or set(live) != {"lease_id", "path", "sha256"}
            or not isinstance(history, dict) or set(history) != {"lease_id", "path", "sha256"}):
        return [Issue("error", "system-aggregation-write-binding-invalid", "聚合 receipt 历史证明与当前 manifest 租约必须各自完整绑定")]
    if (live["lease_id"] == history["lease_id"] or live["path"] == history["path"]
            or str(value.get("aggregation_spawn_receipt")) == target.as_posix()):
        return [Issue("error", "system-aggregation-write-binding-invalid", "聚合 receipt 历史证明与当前 manifest 写入必须使用不同目标和租约")]
    owned = value.get("aggregation_writer_owned_paths")
    if not isinstance(owned, list) or not all(isinstance(path, str) for path in owned):
        return [Issue("error", "system-aggregation-write-binding-invalid", "聚合 owned paths 无效")]
    agent = str(value.get("aggregation_writer_agent_id", ""))
    run = str(value.get("aggregation_writer_run_id", ""))
    return live, history, owned, agent, run


def _historical_aggregation_authority(
    value: dict[str, object], root: Path, history: dict[str, object],
    owned: list[str], agent: str, run: str,
) -> tuple[dict[str, str] | None, list[Issue]]:
    try:
        history_profile = validate_historical_project_record_write_proof(
            root=root, proof_path=Path(str(history["path"])),
            proof_sha256=str(history["sha256"]), target=Path(str(value["aggregation_spawn_receipt"])),
            module_key=str(value.get("aggregation_writer_module_key", "")),
            maintainer_title=str(value.get("aggregation_writer_maintainer_title", "")),
            agent_id=agent, run_id=run,
            lease_id=str(history["lease_id"]), owned_paths=owned,
            baseline_sha256=str(value.get("baseline_sha256", "")),
            code_version=str(value.get("code_version", "")), build_id=str(value.get("build_id", "")),
            candidate_sha256=str(value.get("candidate_sha256", "")),
        )
        history_runtime = writer_runtime_expectation(history_profile)
    except (RuntimeError, KeyError, TypeError) as error:
        return None, [Issue("error", "system-aggregation-receipt-write-proof-invalid", str(error))]
    return history_runtime, []


def _live_aggregation_authority(
    value: dict[str, object], root: Path, target: Path,
    live: dict[str, object], agent: str, run: str,
    history_runtime: dict[str, str],
) -> tuple[dict[str, str] | None, list[Issue]]:
    try:
        binding = authorize_project_record_write(
            root=root, target=target,
            module_key=str(value.get("aggregation_writer_module_key", "")),
            agent_id=agent, run_id=run, agents_path=Path("AGENTS.md"),
            lease_path=Path(str(live["path"])), lease_sha256=str(live["sha256"]),
            authorization_mode=DELIVERY_FIRST_MODE,
        )
        live_runtime = writer_runtime_expectation(binding.writer_profile)
        if live_runtime != history_runtime:
            raise RuntimeError("writer-profile-mismatch")
        if live["lease_id"] != _lease_id(binding.lease_path, root):
            raise RuntimeError("manifest-lease-id-mismatch")
    except (RuntimeError, KeyError, TypeError) as error:
        return None, [Issue("error", "system-aggregation-manifest-write-lease-invalid", str(error))]
    return live_runtime, []


def _lease_id(relative: Path, root: Path) -> object:
    path = root / relative
    return json.loads(path.read_text(encoding="utf-8")).get("lease_id")


def _base_expected(
    value: dict[str, object], *, prefix: str, receipt_kind: str,
    role: str, title: str, read_only: bool, owned_paths_field: str,
    reasoning_effort: str, model: str, root: Path, issues: list[Issue],
    provider: str = "codex-native-agent", recorded_model: str | None = None,
    recorded_reasoning_effort: str | None = None,
) -> dict[str, object]:
    schema_version = value.get("runtime_receipt_schema_version")
    expected = {
        "schema_version": schema_version,
        "receipt_kind": receipt_kind,
        "provider": provider,
        "requested_model": model,
        "recorded_model": recorded_model or model,
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
            "recorded_reasoning_effort": recorded_reasoning_effort or reasoning_effort,
        })
    return expected
