from __future__ import annotations

from pathlib import Path

from implementation_agent_validation import (
    HostAttestationVerifier,
    Issue,
    validate_native_spawn_record,
)


def validate_native_gate_agent(
    gate: dict[str, object], role: str, module: str | None, root: Path,
    agent_ids: set[str], run_ids: set[str],
    host_attestation_verifier: HostAttestationVerifier | None,
    evidence: dict[str, object],
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
            or gate.get("agent_model") != "gpt-5.6-sol"):
        issues.append(Issue(
            "error", "invalid-gate-agent",
            f"{role} 必须声明并绑定为 Codex 原生 gpt-5.6-sol 独立 Agent；严格模式追加宿主证明",
        ))
    if gate.get("agent_reasoning_effort") != "xhigh":
        issues.append(Issue("error", "invalid-gate-agent-effort",
                            f"{role} 必须使用 reasoning_effort=xhigh"))
    slug = role.casefold().replace("_", "-")
    expected = {
        "schema_version": 1,
        "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent",
        "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "xhigh",
        "recorded_reasoning_effort": "xhigh",
        "agent_id": agent_id,
        "run_id": run_id,
        "role": f"{slug}-gate",
        "module": module,
        "maintainer_title": f"{role} Gate Reviewer",
    }
    issues.extend(_validate_gate_receipts(
        gate, role, root, expected, evidence, host_attestation_verifier,
    ))
    return issues


def _validate_gate_receipts(
    gate: dict[str, object], role: str, root: Path,
    expected: dict[str, object], evidence: dict[str, object],
    host_attestation_verifier: HostAttestationVerifier | None,
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
