from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from validate_context_manifest import _parse_metadata as parse_context_metadata
from validate_context_manifest import _split_paths
from validate_traceability import GATE_COLUMNS, LINK_RE, TRACE_COLUMNS, _parse_metadata, _parse_table
from template_schema_validation import multi_agent_issues as _multi_agent_template_issues
from implementation_agent_validation import (
    HostAttestationVerifier, ReceiptReplayState,
    _validate_implementation_agent_impl,
)
from native_gate_agent_validation import validate_native_gate_agent
from multi_agent_input_validation import validate_gate_input
from traceability_common import INDEPENDENT_ROLES, VALIDATION_STAGES, required_independent_roles
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
KNOWN_ROLES = INDEPENDENT_ROLES
V1_TOP_LEVEL_FIELDS = {"schema_version", "stage", "baseline_version", "baseline_sha256", "code_version", "candidate_sha256",
                    "build_id", "implementation_agent_title", "implementation_run_id",
                    "implementation_agent_provider", "implementation_agent_model",
                    "implementation_agent_reasoning_effort",
                    "implementation_agent_id", "implementation_spawn_receipt",
                    "implementation_spawn_receipt_sha256",
                    "single_writer_run_id", "gates", "open_disagreements"}
V2_RUNTIME_BINDING_FIELDS = {
    "authority_matrix_sha256", "owned_paths", "active_write_lease",
}
TOP_LEVEL_FIELDS = V1_TOP_LEVEL_FIELDS | V2_RUNTIME_BINDING_FIELDS
GATE_FIELDS = {
    "role", "run_id", "provider", "agent_model", "agent_reasoning_effort", "agent_id",
    "spawn_receipt", "spawn_receipt_sha256", "output_receipt", "output_receipt_sha256", "focus", "input_manifest", "input_sha256",
    "output_evidence", "output_sha256", "may_modify_code", "may_modify_shared_records",
    "received_full_chat", "received_other_agent_reasoning",
    "accepted_implementation_self_report", "verdict"}
@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
def validate_multi_agent_evidence(path: Path, *, trace_path: Path, context_path: Path, project_root: Path,
                                  stage: str = "completion", template: bool = False) -> list[Issue]:
    return _validate_multi_agent_evidence_impl(path, trace_path=trace_path, context_path=context_path, project_root=project_root, stage=stage, template=template, verifier=None, expected_requirement_questions_locator=None, expected_requirement_questions_sha256=None)
def _test_only_validate_multi_agent_evidence(
    path: Path, *, trace_path: Path, context_path: Path, project_root: Path,
    stage: str = "completion", template: bool = False, _test_only_host_attestation_verifier: HostAttestationVerifier,
    _test_only_expected_requirement_questions_locator: str,
    _test_only_expected_requirement_questions_sha256: str,
) -> list[Issue]:
    return _validate_multi_agent_evidence_impl(path, trace_path=trace_path, context_path=context_path, project_root=project_root, stage=stage, template=template, verifier=_test_only_host_attestation_verifier, expected_requirement_questions_locator=_test_only_expected_requirement_questions_locator, expected_requirement_questions_sha256=_test_only_expected_requirement_questions_sha256)
def _validate_multi_agent_evidence_impl(
    path: Path, *, trace_path: Path, context_path: Path, project_root: Path, stage: str,
    template: bool, verifier: HostAttestationVerifier | None,
    expected_requirement_questions_locator: str | None,
    expected_requirement_questions_sha256: str | None,
) -> list[Issue]:
    data, issues = _read_json(path)
    if data is None:
        return issues
    _validate_structure(data, issues, template=template)
    if template:
        issues.extend(Issue("error", code, message) for code, message in _multi_agent_template_issues(data, GATE_FIELDS))
        return _deduplicate(issues)
    if PLACEHOLDER_RE.search(path.read_text(encoding="utf-8")):
        issues.append(Issue("error", "placeholder", "多 Agent 证据包含未解析占位符"))
    root = project_root.resolve()
    context, forbidden_outputs = _agent_context(context_path, root, issues)
    receipt_replay_state = ReceiptReplayState.empty()
    implementation_issues = _validate_implementation_agent_impl(
        data, context, root, verifier, receipt_replay_state,
    )
    issues.extend(Issue(item.severity, item.code, item.message) for item in implementation_issues)
    requirement_ids = {
        item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()
    }
    metadata, trace_gates, role_paths = _read_trace(trace_path, requirement_ids, issues)
    if metadata is None:
        return _deduplicate(issues)
    if data.get("stage") != stage:
        issues.append(Issue("error", "agent-stage-mismatch", "多 Agent 证据 stage 与当前门禁不一致"))
    _validate_binding(data, metadata, issues)
    allowed_inputs = _allowed_role_inputs(role_paths, context)
    _validate_gates(
        data, metadata, trace_gates, root, stage, context, allowed_inputs,
        forbidden_outputs, verifier, expected_requirement_questions_locator,
        expected_requirement_questions_sha256, receipt_replay_state, issues,
    )
    disagreements = data.get("open_disagreements")
    if disagreements != []:
        issues.append(Issue("error", "open-agent-disagreement", "多 Agent 分歧必须关闭后才能通过"))
    return _deduplicate(issues)
def _read_json(path: Path) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [Issue("error", "invalid-agent-evidence", str(error))]
    if not isinstance(data, dict):
        return None, [Issue("error", "invalid-agent-evidence", "多 Agent 证据根节点必须是对象")]
    return data, []
def _validate_structure(data: dict[str, object], issues: list[Issue], *, template: bool = False) -> None:
    schema_version = data.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        issues.append(Issue("error", "invalid-schema-version", "schema_version 必须是整数 1 或 2"))
    expected_fields = TOP_LEVEL_FIELDS if schema_version == 2 else V1_TOP_LEVEL_FIELDS
    for field in (
        "stage", "baseline_version", "baseline_sha256", "code_version", "build_id",
        "candidate_sha256",
        "implementation_agent_title", "implementation_agent_provider",
        "implementation_agent_model", "implementation_agent_reasoning_effort", "implementation_agent_id",
        "implementation_run_id", "implementation_spawn_receipt",
        "implementation_spawn_receipt_sha256", "single_writer_run_id",
        "gates", "open_disagreements",
    ):
        if field not in data:
            issues.append(Issue("error", "missing-field", f"缺少多 Agent 证据字段：{field}"))
    if not isinstance(data.get("gates"), list):
        issues.append(Issue("error", "invalid-gates", "gates 必须是数组"))
    if schema_version == 2:
        for field in V2_RUNTIME_BINDING_FIELDS:
            if field not in data:
                issues.append(Issue("error", "missing-field", f"缺少多 Agent 证据字段：{field}"))
    identity_fields = V1_TOP_LEVEL_FIELDS - {"schema_version", "gates", "open_disagreements"}
    if any(type(data.get(field)) is not str or not data.get(field, "").strip() for field in identity_fields):
        issues.append(Issue("error", "invalid-agent-evidence-types", "多 Agent 身份、版本、构建和阶段字段必须是非空字符串"))
    if type(data.get("open_disagreements")) is not list:
        issues.append(Issue("error", "invalid-agent-disagreements", "open_disagreements 必须是数组"))
    candidate_sha = data.get("candidate_sha256")
    if (type(candidate_sha) is not str
            or (SHA256_RE.fullmatch(candidate_sha) is None and not (template and PLACEHOLDER_RE.fullmatch(candidate_sha)))):
        issues.append(Issue("error", "invalid-candidate-sha256", "candidate_sha256 必须是 64 位 SHA-256"))
    if set(data) != expected_fields:
        issues.append(Issue("error", "invalid-agent-evidence-fields", "多 Agent 证据含缺失、重复或未知字段"))
def _read_trace(
    path: Path, requirement_ids: set[str], issues: list[Issue],
) -> tuple[dict[str, str] | None, dict[str, dict[str, str]], dict[str, set[str]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        issues.append(Issue("error", "unreadable-trace", str(error)))
        return None, {}, {}
    rows, _, parse_issues = _parse_table(text, "Independent Gate Evidence", GATE_COLUMNS)
    for item in parse_issues:
        issues.append(Issue(item.severity, f"trace-{item.code}", item.message))
    return (
        _parse_metadata(text),
        {row["Gate"].strip(): row for row in (rows or [])},
        _trace_role_paths(text, requirement_ids),
    )
def _trace_role_paths(text: str, requirement_ids: set[str]) -> dict[str, set[str]]:
    rows, _, _ = _parse_table(text, "Traceability", TRACE_COLUMNS)
    columns = {
        "UI_UX": ("Flow", "Feature", "UI/UX"),
        "ACCEPTANCE_CASES": ("Feature", "UI/UX", "Unit tests", "Acceptance cases"),
        "CHANGE_REVIEW": ("Flow", "Unit tests", "Code module"),
        "BLACK_BOX": ("UI/UX", "Acceptance cases"),
        "REQUIREMENT_REVIEW": ("Requirement", "Flow", "Feature", "UI/UX"),
        "SPECIALIST_REVIEW": ("Flow", "Unit tests", "Code module"),
    }
    result: dict[str, set[str]] = {role: set() for role in columns}
    for row in rows or []:
        row_ids = {label.strip() for label, _ in LINK_RE.findall(row.get("Requirement", ""))}
        if requirement_ids and not requirement_ids & row_ids:
            continue
        for role, names in columns.items():
            for name in names:
                result[role].update(path.strip() for _, path in LINK_RE.findall(row.get(name, "")))
    return result
def _allowed_role_inputs(
    role_paths: dict[str, set[str]], context: dict[str, str],
) -> dict[str, set[str]]:
    baseline = context.get("Baseline artifact", "")
    direct = {
        item for field in ("Changed files", "Configuration files", "Input files")
        for item in _split_paths(context.get(field, ""))
    }
    result = {role: ({baseline} | paths) for role, paths in role_paths.items()}
    for role in ("CHANGE_REVIEW", "SPECIALIST_REVIEW"):
        result.setdefault(role, {baseline}).update(direct)
    return result
def _validate_binding(data: dict[str, object], metadata: dict[str, str], issues: list[Issue]) -> None:
    mappings = (
        ("baseline_version", "Baseline version"), ("baseline_sha256", "Baseline SHA-256"),
        ("code_version", "Code version"), ("build_id", "Build ID"),
        ("implementation_run_id", "Implementation run ID"),
    )
    for evidence_field, trace_field in mappings:
        if str(data.get(evidence_field, "")).casefold() != metadata.get(trace_field, "").casefold():
            issues.append(Issue("error", "stale-agent-binding", f"{evidence_field} 与追踪矩阵不一致"))
    if data.get("single_writer_run_id") != data.get("implementation_run_id"):
        issues.append(Issue("error", "multiple-or-wrong-writer", "唯一写者必须是实现 Agent"))
def _required_roles(metadata: dict[str, str], stage: str) -> set[str]:
    risk = metadata.get("Risk level", "")
    surfaces = {part.strip().casefold() for part in metadata.get("Change surfaces", "").split(",")}
    return required_independent_roles(risk, surfaces, stage)
def _validate_gates(
    data: dict[str, object],
    metadata: dict[str, str],
    trace_gates: dict[str, dict[str, str]],
    root: Path,
    stage: str,
    context: dict[str, str],
    allowed_inputs: dict[str, set[str]],
    forbidden_outputs: set[tuple[int, int]],
    host_attestation_verifier: HostAttestationVerifier | None,
    expected_requirement_questions_locator: str | None,
    expected_requirement_questions_sha256: str | None,
    receipt_replay_state: ReceiptReplayState,
    issues: list[Issue],
) -> None:
    gates = data.get("gates")
    if not isinstance(gates, list):
        return
    role_map: dict[str, dict[str, object]] = {}
    run_ids: set[str] = {str(data.get("implementation_run_id", ""))}
    agent_ids: set[str] = {str(data.get("implementation_agent_id", ""))}
    modules = [item.strip().casefold() for item in context.get("Modules", "").split(",") if item.strip()]
    module = modules[0] if len(modules) == 1 else None
    artifact_identities: set[tuple[int, int]] = set()
    artifact_hashes: set[str] = set()
    for raw in gates:
        if not isinstance(raw, dict):
            issues.append(Issue("error", "invalid-gate-entry", "独立 Agent 门禁条目必须是对象"))
            continue
        if set(raw) != GATE_FIELDS:
            issues.append(Issue("error", "invalid-gate-fields", "独立 Agent 门禁条目含缺失或未知字段"))
        role = str(raw.get("role", ""))
        if role not in KNOWN_ROLES:
            issues.append(Issue("error", "unknown-agent-role", f"未知独立 Agent 角色：{role}"))
            continue
        if role in role_map:
            issues.append(Issue("error", "duplicate-agent-role", f"独立 Agent 角色重复：{role}"))
        role_map[role] = raw
        _validate_gate(
            role, raw, data, trace_gates, run_ids, agent_ids, module, artifact_identities,
            artifact_hashes, context, allowed_inputs, forbidden_outputs, root, issues,
            host_attestation_verifier, expected_requirement_questions_locator,
            expected_requirement_questions_sha256, receipt_replay_state,
        )
    required = _required_roles(metadata, stage)
    for role in required - set(role_map):
        issues.append(Issue("error", "missing-agent-role", f"当前风险缺少独立 Agent：{role}"))
    for role in set(role_map) - required:
        issues.append(Issue("error", "nonapplicable-agent-role", f"当前阶段和风险不应启动独立 Agent：{role}"))
def _validate_gate(
    role: str,
    gate: dict[str, object],
    evidence: dict[str, object],
    trace_gates: dict[str, dict[str, str]],
    run_ids: set[str],
    agent_ids: set[str],
    module: str | None,
    artifact_identities: set[tuple[int, int]],
    artifact_hashes: set[str],
    context: dict[str, str],
    allowed_inputs: dict[str, set[str]],
    forbidden_outputs: set[tuple[int, int]],
    root: Path,
    issues: list[Issue],
    host_attestation_verifier: HostAttestationVerifier | None,
    expected_requirement_questions_locator: str | None,
    expected_requirement_questions_sha256: str | None,
    receipt_replay_state: ReceiptReplayState,
) -> None:
    raw_run_id = gate.get("run_id")
    run_id = raw_run_id.strip() if isinstance(raw_run_id, str) else ""
    issues.extend(Issue(item.severity, item.code, item.message) for item in validate_native_gate_agent(
        gate, role, module, root, agent_ids, run_ids, host_attestation_verifier,
        evidence, receipt_replay_state,
    ))
    trace_row = trace_gates.get(role)
    if trace_row and run_id != trace_row.get("Agent run ID", "").strip():
        issues.append(Issue("error", "trace-agent-run-mismatch", f"{role} 的 run_id 与追踪矩阵不一致"))
    if any(not isinstance(gate.get(field), str) or not gate.get(field, "").strip() for field in ("provider", "focus")):
        issues.append(Issue("error", "missing-agent-scope", f"{role} 缺少 provider 或 focus"))
    for boundary in ("may_modify_code", "may_modify_shared_records", "received_full_chat", "received_other_agent_reasoning", "accepted_implementation_self_report"):
        if gate.get(boundary) is not False:
            issues.append(Issue("error", "unsafe-agent-boundary", f"{role} 必须将 {boundary} 设为 false"))
    _validate_gate_artifacts(
        role, gate, evidence, context, trace_row, artifact_identities,
        artifact_hashes, allowed_inputs, forbidden_outputs, root, issues, host_attestation_verifier,
        expected_requirement_questions_locator, expected_requirement_questions_sha256,
    )
    if gate.get("verdict") != "pass":
        issues.append(Issue("error", "agent-gate-not-pass", f"{role} verdict 必须是 pass"))
def _validate_gate_artifacts(
    role: str, gate: dict[str, object], evidence: dict[str, object],
    context: dict[str, str], trace_row: dict[str, str] | None,
    artifact_identities: set[tuple[int, int]], artifact_hashes: set[str],
    allowed_inputs: dict[str, set[str]], forbidden_outputs: set[tuple[int, int]],
    root: Path, issues: list[Issue], host_attestation_verifier: HostAttestationVerifier | None,
    expected_requirement_questions_locator: str | None,
    expected_requirement_questions_sha256: str | None,
) -> None:
    for path_field, hash_field in (("input_manifest", "input_sha256"), ("output_evidence", "output_sha256")):
        raw_path = str(gate.get(path_field, ""))
        resolved = _validate_hashed_path(gate.get(path_field), gate.get(hash_field), root, role, issues)
        if resolved is not None:
            identity = (resolved.stat().st_dev, resolved.stat().st_ino)
            digest = _canonical_artifact_hash(resolved)
            if identity in artifact_identities:
                issues.append(Issue("error", "reused-agent-artifact", f"{role} 复用了其他角色证据：{raw_path}"))
            if digest in artifact_hashes:
                issues.append(Issue("error", "reused-agent-artifact-content", f"{role} 复用了其他角色相同内容：{raw_path}"))
            artifact_identities.add(identity)
            artifact_hashes.add(digest)
            if path_field == "input_manifest":
                issues.extend(Issue(item.severity, item.code, item.message) for item in validate_gate_input(
                    resolved, role, gate, evidence, context, allowed_inputs.get(role, set()),
                    root, host_attestation_verifier, expected_requirement_questions_locator,
                    expected_requirement_questions_sha256,
                ))
            if path_field == "output_evidence" and identity in forbidden_outputs:
                issues.append(Issue("error", "agent-output-reuses-workset", f"{role} 输出不得复用变更或输入文件"))
            if path_field == "output_evidence":
                _validate_gate_output(resolved, role, gate, evidence, issues)
        if trace_row:
            column = "Input manifest" if path_field == "input_manifest" else "Output evidence"
            links = LINK_RE.findall(trace_row.get(column, ""))
            if len(links) == 1 and links[0][1].strip() != raw_path:
                issues.append(Issue("error", "trace-agent-artifact-mismatch", f"{role} 的 {path_field} 与追踪矩阵不一致"))
def _agent_context(
    context_path: Path, root: Path, issues: list[Issue],
) -> tuple[dict[str, str], set[tuple[int, int]]]:
    try:
        context, _ = parse_context_metadata(context_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        issues.append(Issue("error", "unreadable-agent-context", str(error)))
        return {}, set()
    identities: set[tuple[int, int]] = set()
    for field in ("Changed files", "Configuration files", "Input files"):
        for raw_path in _split_paths(context.get(field, "")):
            candidate = root / raw_path
            try:
                identities.add((candidate.stat().st_dev, candidate.stat().st_ino))
            except OSError:
                issues.append(Issue("error", "missing-agent-context-input", f"工作集输入不存在：{raw_path}"))
    return context, identities

def _validate_gate_output(
    path: Path, role: str, gate: dict[str, object],
    evidence: dict[str, object], issues: list[Issue],
) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        issues.append(Issue("error", "invalid-agent-output", f"{role} 输出必须是无重复键的结构化 JSON"))
        return
    expected = {
        "schema_version": 1, "role": role, "run_id": gate.get("run_id"),
        "baseline_version": evidence.get("baseline_version"),
        "baseline_sha256": evidence.get("baseline_sha256"),
        "code_version": evidence.get("code_version"),
        "input_sha256": gate.get("input_sha256"), "verdict": "pass", "findings": [],
    }
    if not isinstance(data, dict) or set(data) != set(expected):
        issues.append(Issue("error", "invalid-agent-output", f"{role} 输出结构不完整或含未知字段"))
        return
    string_fields = (
        "role", "run_id", "baseline_version", "baseline_sha256", "code_version",
        "input_sha256", "verdict",
    )
    if (type(data.get("schema_version")) is not int or type(data.get("findings")) is not list
            or any(type(data.get(field)) is not str for field in string_fields)):
        issues.append(Issue("error", "invalid-agent-output", f"{role} 输出字段类型不合法"))
    elif any(data.get(key) != value for key, value in expected.items()):
        issues.append(Issue("error", "stale-agent-output", f"{role} 输出未绑定当前角色、run、基线或代码"))

def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-key")
        result[key] = value
    return result

def _canonical_artifact_hash(path: Path) -> str:
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        return hashlib.sha256(payload).hexdigest()
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_hashed_path(
    path_value: object,
    hash_value: object,
    root: Path,
    role: str,
    issues: list[Issue],
) -> Path | None:
    if type(path_value) is not str or type(hash_value) is not str:
        issues.append(Issue("error", "unsafe-agent-artifact-path", f"{role} 证据路径和哈希必须是字符串"))
        return None
    raw_path, expected = path_value, hash_value.casefold()
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", "unsafe-agent-artifact-path", f"{role} 证据路径必须位于项目内"))
        return None
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            issues.append(Issue("error", "unsafe-agent-artifact-path", f"{role} 证据路径不得经过符号链接"))
            return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", "unsafe-agent-artifact-path", f"{role} 证据路径越出项目根"))
        return None
    if not resolved.is_file():
        issues.append(Issue("error", "missing-agent-artifact", f"{role} 证据不存在：{raw_path}"))
        return None
    elif not SHA256_RE.fullmatch(expected) or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected:
        issues.append(Issue("error", "stale-agent-artifact", f"{role} 证据哈希已失效：{raw_path}"))
    return resolved
def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())
def main() -> int:
    parser = argparse.ArgumentParser(description="验证风险触发、多 Agent 独立性、单写者和证据绑定")
    parser.add_argument("path", type=Path)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--stage", choices=VALIDATION_STAGES, default="completion")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_multi_agent_evidence(arguments.path, trace_path=arguments.trace, context_path=arguments.context, project_root=arguments.project_root, stage=arguments.stage, template=arguments.template)
    failed = any(item.severity == "error" for item in issues)
    if arguments.json:
        print(json.dumps({"valid": not failed, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            print(f"{item.severity.upper()} {item.code} {item.message}")
        print(f"errors={sum(item.severity == 'error' for item in issues)} valid={str(not failed).lower()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
