from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256
from implementation_agent_validation import HostAttestationVerifier, validate_native_spawn_record
from native_gate_agent_validation import validate_native_gate_agent
from native_review_checkpoint_validation import CHECKPOINT_FIELDS, WRAPPER_FIELDS, validate_checkpoint_chain
from native_review_role_validation import validate_native_review_role_receipts
from strict_json import loads as strict_json_loads


SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
TOP_FIELDS = {
    "schema_version", "stage", "authority_matrix_sha256", "workflow_id", "module", "maintainer_title",
    "adjudicator_agent_id", "adjudicator_run_id", "adjudicator_spawn_receipt",
    "adjudicator_spawn_receipt_sha256", "adjudicator_may_modify_code",
    "adjudicator_may_modify_shared_records", "adjudicator_holds_writer_lease",
    "writer_agent_id", "writer_run_id", "writer_role", "writer_spawn_receipt",
    "writer_spawn_receipt_sha256", "scope_version", "scope_sha256", "baseline_version",
    "baseline_sha256", "code_version", "build_id", "max_candidate_versions", "candidates",
    "final_candidate_version", "final_candidate_sha256", "outcome",
    "runtime_multi_agent_evidence", "runtime_multi_agent_evidence_sha256",
    "checkpoint_chain",
}
CANDIDATE_FIELDS = {
    "version", "candidate_artifact", "candidate_sha256", "solution_author",
    "black_box_reviewer", "coordinator_adjudication",
}
CHILD_FIELDS = {
    "provider", "agent_model", "agent_reasoning_effort", "agent_id", "run_id", "spawn_receipt",
    "spawn_receipt_sha256", "output_receipt", "output_receipt_sha256", "input_manifest",
    "input_sha256", "output_evidence", "output_sha256", "may_modify_code",
    "may_modify_shared_records", "received_full_chat", "received_other_agent_reasoning",
    "accepted_implementation_self_report", "verdict",
}
ADJUDICATION_FIELDS = {
    "agent_id", "run_id", "candidate_version", "candidate_sha256", "verdict", "findings", "uncertainties",
    "blockers", "disagreements",
}
REVIEW_OUTPUT_FIELDS = {
    "schema_version", "role", "agent_id", "run_id", "scope_sha256", "candidate_version",
    "candidate_sha256", "verdict", "findings", "uncertainties", "blockers",
    "disagreements", "black_box_cases",
}
INPUT_FIELDS = {
    "schema_version", "role", "agent_id", "run_id", "scope_sha256", "candidate_version",
    "candidate_sha256", "includes_full_chat", "includes_other_agent_reasoning",
    "includes_implementation_self_report",
}
CASE_CATEGORIES = {"success", "rejection", "failure", "retry", "recovery", "permission", "boundary"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_native_review_loop(
    path: Path, *, project_root: Path, template: bool = False,
) -> list[Issue]:
    return _validate_native_review_loop_impl(path, project_root=project_root, template=template, verifier=None)


def _test_only_validate_native_review_loop(
    path: Path, *, project_root: Path, template: bool = False,
    _test_only_host_attestation_verifier: HostAttestationVerifier,
) -> list[Issue]:
    return _validate_native_review_loop_impl(
        path, project_root=project_root, template=template,
        verifier=_test_only_host_attestation_verifier,
    )


def _validate_native_review_loop_impl(
    path: Path, *, project_root: Path, template: bool,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    data, issues = _read_object(path, "invalid-native-loop-evidence")
    if data is None:
        return issues
    _closed_fields(data, TOP_FIELDS, "invalid-native-loop-fields", issues)
    _validate_top(data, template, issues)
    if template:
        _validate_template_shape(data, issues)
        return _deduplicate(issues)
    root = project_root.resolve()
    agent_ids: set[str] = set()
    run_ids: set[str] = set()
    _unique(data.get("adjudicator_agent_id"), agent_ids, issues)
    _unique(data.get("adjudicator_run_id"), run_ids, issues)
    if (data.get("writer_agent_id") == data.get("adjudicator_agent_id")
            or data.get("writer_run_id") == data.get("adjudicator_run_id")):
        issues.append(Issue(
            "error", "reused-native-loop-writer-identity",
            "协调裁决者与租约写者必须使用不同 Agent ID 和 run ID",
        ))
    _unique(data.get("writer_agent_id"), agent_ids, issues)
    _unique(data.get("writer_run_id"), run_ids, issues)
    issues.extend(_convert(validate_native_review_role_receipts(data, root, verifier)))
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return _deduplicate(issues)
    for index, candidate in enumerate(candidates, start=1):
        _validate_candidate(
            candidate, index, data, root, agent_ids, run_ids,
            verifier, issues,
        )
    issues.extend(_convert(validate_checkpoint_chain(data, root, verifier)))
    _validate_final(data, root, agent_ids, run_ids, verifier, issues)
    return _deduplicate(issues)


def _validate_top(data: dict[str, object], template: bool, issues: list[Issue]) -> None:
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issues.append(Issue("error", "invalid-native-loop-schema", "schema_version 必须是 1"))
    if template:
        return
    for field in (
        "authority_matrix_sha256", "scope_sha256", "baseline_sha256", "final_candidate_sha256",
    ):
        if not _is_sha(data.get(field)):
            issues.append(Issue("error", "invalid-native-loop-sha256", f"{field} 必须是 SHA-256"))
    if str(data.get("authority_matrix_sha256", "")).casefold() != AUTHORITY_MATRIX_SHA256:
        issues.append(Issue("error", "stale-authority-matrix-binding", "native loop 未绑定固定权限矩阵"))
    if data.get("stage") not in {"design-review", "completion"}:
        issues.append(Issue("error", "invalid-native-loop-stage", "stage 必须是 design-review 或 completion"))
    if data.get("max_candidate_versions") != 6:
        issues.append(Issue("error", "invalid-native-loop-limit", "max_candidate_versions 必须固定为 6"))
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        issues.append(Issue("error", "invalid-native-loop-candidates", "candidates 必须是非空数组"))
    elif len(candidates) > 6:
        issues.append(Issue("error", "too-many-candidate-versions", "候选版本不得超过六轮"))
    strings = TOP_FIELDS - {
        "schema_version", "max_candidate_versions", "candidates", "checkpoint_chain", "final_candidate_version",
        "adjudicator_may_modify_code", "adjudicator_may_modify_shared_records",
        "adjudicator_holds_writer_lease",
    }
    if any(type(data.get(field)) is not str or not str(data.get(field)).strip() for field in strings):
        issues.append(Issue("error", "invalid-native-loop-types", "native loop 标识和绑定字段必须是非空字符串"))
    if type(data.get("final_candidate_version")) is not int:
        issues.append(Issue("error", "invalid-native-loop-types", "final_candidate_version 必须是整数"))
    if data.get("writer_role") not in {"implementation", "module-maintainer"}:
        issues.append(Issue("error", "invalid-native-loop-writer-role", "writer_role 必须是 implementation 或 module-maintainer"))
    if any(data.get(field) is not False for field in (
        "adjudicator_may_modify_code", "adjudicator_may_modify_shared_records",
        "adjudicator_holds_writer_lease",
    )):
        issues.append(Issue(
            "error", "unsafe-native-loop-adjudicator-boundary",
            "协调裁决者必须只读、不得写共享记录且不得持 writer lease",
        ))


def _validate_template_shape(data: dict[str, object], issues: list[Issue]) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        issues.append(Issue("error", "invalid-native-loop-template", "模板必须含一个完整候选示例"))
        return
    candidate = candidates[0]
    _closed_fields(candidate, CANDIDATE_FIELDS, "invalid-native-loop-candidate-fields", issues)
    for key in ("solution_author", "black_box_reviewer"):
        child = candidate.get(key)
        if not isinstance(child, dict):
            issues.append(Issue("error", "invalid-native-loop-template", f"模板缺少 {key} 对象"))
        else:
            _closed_fields(child, CHILD_FIELDS, "invalid-native-loop-child-fields", issues)
            for boundary in (
                "may_modify_code", "may_modify_shared_records", "received_full_chat",
                "received_other_agent_reasoning", "accepted_implementation_self_report",
            ):
                if child.get(boundary) is not False:
                    issues.append(Issue("error", "unsafe-native-loop-boundary", f"模板 {key}.{boundary} 必须为 false"))
    for boundary in (
        "adjudicator_may_modify_code", "adjudicator_may_modify_shared_records",
        "adjudicator_holds_writer_lease",
    ):
        if data.get(boundary) is not False:
            issues.append(Issue(
                "error", "unsafe-native-loop-adjudicator-boundary",
                f"模板 {boundary} 必须为 false",
            ))
    adjudication = candidate.get("coordinator_adjudication")
    if not isinstance(adjudication, dict):
        issues.append(Issue("error", "invalid-native-loop-template", "模板缺少 coordinator_adjudication"))
    else:
        _closed_fields(adjudication, ADJUDICATION_FIELDS, "invalid-coordinator-adjudication-fields", issues)
    chain = data.get("checkpoint_chain")
    if not isinstance(chain, list) or len(chain) != 1 or not isinstance(chain[0], dict):
        issues.append(Issue("error", "invalid-native-loop-checkpoint-template", "模板必须含一个 checkpoint"))
    else:
        _closed_fields(chain[0], WRAPPER_FIELDS, "invalid-native-loop-checkpoint-fields", issues)
        checkpoint = chain[0].get("checkpoint")
        if not isinstance(checkpoint, dict):
            issues.append(Issue("error", "invalid-native-loop-checkpoint-template", "模板 checkpoint 必须是对象"))
        else:
            _closed_fields(checkpoint, CHECKPOINT_FIELDS, "invalid-native-loop-checkpoint-fields", issues)


def _validate_candidate(
    raw: object, index: int, bundle: dict[str, object], root: Path,
    agent_ids: set[str], run_ids: set[str], verifier: HostAttestationVerifier | None,
    issues: list[Issue],
) -> None:
    if not isinstance(raw, dict):
        issues.append(Issue("error", "invalid-native-loop-candidate", "候选条目必须是对象"))
        return
    _closed_fields(raw, CANDIDATE_FIELDS, "invalid-native-loop-candidate-fields", issues)
    if raw.get("version") != index:
        issues.append(Issue("error", "nonsequential-candidate-version", "候选版本必须从 1 连续递增"))
    candidate = _hashed_file(raw.get("candidate_artifact"), raw.get("candidate_sha256"), root, issues)
    for key, role, verdict in (
        ("solution_author", "solution-author", "produced"),
        ("black_box_reviewer", "black-box-reviewer", "pass"),
    ):
        child = raw.get(key)
        _validate_child(
            child, role, verdict, index, raw, bundle, root, agent_ids, run_ids, verifier, issues,
        )
    author = raw.get("solution_author")
    if isinstance(author, dict) and candidate is not None:
        if (author.get("output_evidence") != raw.get("candidate_artifact")
                or str(author.get("output_sha256", "")).casefold() != str(raw.get("candidate_sha256", "")).casefold()):
            issues.append(Issue("error", "solution-output-not-candidate", "方案 Agent 输出必须就是该候选文件"))
    _validate_adjudication(
        raw.get("coordinator_adjudication"), index, raw.get("candidate_sha256"), bundle, issues,
    )


def _validate_child(raw: object, role: str, expected_verdict: str, version: int, candidate: dict[str, object],
    bundle: dict[str, object], root: Path, agent_ids: set[str], run_ids: set[str], verifier: HostAttestationVerifier | None,
    issues: list[Issue]) -> None:
    if not isinstance(raw, dict):
        issues.append(Issue("error", "invalid-native-loop-child", f"{role} 必须是对象"))
        return
    _closed_fields(raw, CHILD_FIELDS, "invalid-native-loop-child-fields", issues)
    if raw.get("provider") != "codex-native-agent" or raw.get("agent_model") != "gpt-6-astra":
        issues.append(Issue("error", "invalid-native-loop-model", f"{role} 必须是原生 gpt-6-astra"))
    if raw.get("agent_reasoning_effort") != "high":
        issues.append(Issue("error", "invalid-native-loop-effort", f"{role} 必须使用 reasoning_effort=high"))
    for field in (
        "may_modify_code", "may_modify_shared_records", "received_full_chat",
        "received_other_agent_reasoning", "accepted_implementation_self_report",
    ):
        if raw.get(field) is not False:
            issues.append(Issue("error", "unsafe-native-loop-boundary", f"{role} 的 {field} 必须为 false"))
    _unique(raw.get("agent_id"), agent_ids, issues)
    _unique(raw.get("run_id"), run_ids, issues)
    input_path = _hashed_file(raw.get("input_manifest"), raw.get("input_sha256"), root, issues)
    output_path = _hashed_file(raw.get("output_evidence"), raw.get("output_sha256"), root, issues)
    _validate_input(input_path, raw, role, version, candidate.get("candidate_sha256"), bundle, issues)
    if role == "black-box-reviewer":
        _validate_review_output(output_path, raw, version, candidate.get("candidate_sha256"), bundle, issues)
    if raw.get("verdict") != expected_verdict:
        issues.append(Issue("error", "invalid-native-loop-verdict", f"{role} verdict 必须是 {expected_verdict}"))
    expected = {
        "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-6-astra",
        "recorded_model": "gpt-6-astra", "agent_id": raw.get("agent_id"),
        "requested_reasoning_effort": "high", "recorded_reasoning_effort": "high",
        "run_id": raw.get("run_id"), "role": role, "module": bundle.get("module"),
        "maintainer_title": role,
    }
    issues.extend(_convert(validate_native_spawn_record(
        data=raw, root=root, expected=expected, path_field="spawn_receipt",
        hash_field="spawn_receipt_sha256", code_prefix="native-loop-child", label=role,
        host_attestation_verifier=verifier,
    )))
    output_expected = {
        **expected, "receipt_kind": "codex-native-output-result",
        "input_sha256": raw.get("input_sha256"), "output_sha256": raw.get("output_sha256"),
        "scope_sha256": bundle.get("scope_sha256"), "candidate_version": version,
        "candidate_sha256": candidate.get("candidate_sha256"), "verdict": raw.get("verdict"),
    }
    issues.extend(_convert(validate_native_spawn_record(
        data=raw, root=root, expected=output_expected, path_field="output_receipt",
        hash_field="output_receipt_sha256", code_prefix="native-loop-child-output", label=role,
        host_attestation_verifier=verifier, record_label="output result",
    )))


def _validate_input(
    path: Path | None, child: dict[str, object], role: str, version: int,
    candidate_sha: object, bundle: dict[str, object], issues: list[Issue],
) -> None:
    data = _read_path_object(path, "invalid-native-loop-input", issues)
    if data is None:
        return
    _closed_fields(data, INPUT_FIELDS, "invalid-native-loop-input-fields", issues)
    expected_candidate = candidate_sha if role == "black-box-reviewer" else "N/A"
    expected = {
        "schema_version": 1, "role": role, "agent_id": child.get("agent_id"),
        "run_id": child.get("run_id"), "scope_sha256": bundle.get("scope_sha256"),
        "candidate_version": version, "candidate_sha256": expected_candidate,
        "includes_full_chat": False, "includes_other_agent_reasoning": False,
        "includes_implementation_self_report": False,
    }
    if data != expected:
        issues.append(Issue("error", "stale-native-loop-input", f"{role} 输入未精确绑定当前 scope/candidate/run"))


def _validate_review_output(
    path: Path | None, child: dict[str, object], version: int,
    candidate_sha: object, bundle: dict[str, object], issues: list[Issue],
) -> None:
    data = _read_path_object(path, "invalid-native-loop-review-output", issues)
    if data is None:
        return
    _closed_fields(data, REVIEW_OUTPUT_FIELDS, "invalid-native-loop-review-output-fields", issues)
    expected = {
        "schema_version": 1, "role": "black-box-reviewer", "agent_id": child.get("agent_id"),
        "run_id": child.get("run_id"), "scope_sha256": bundle.get("scope_sha256"),
        "candidate_version": version, "candidate_sha256": candidate_sha,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        issues.append(Issue("error", "stale-native-loop-review-output", "黑盒审查未绑定同一候选和 run"))
    open_fields = ("findings", "uncertainties", "blockers", "disagreements")
    if any(type(data.get(field)) is not list for field in open_fields):
        issues.append(Issue("error", "invalid-native-loop-review-lists", "黑盒审查开放项必须是数组"))
    if data.get("verdict") == "pass" and any(data.get(field) != [] for field in open_fields):
        issues.append(Issue("error", "open-native-loop-items", "pass 时黑盒审查不得有开放项"))
    cases = data.get("black_box_cases")
    categories: set[str] = set()
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, dict) and set(case) == {"category", "case"} and type(case.get("case")) is str and case.get("case", "").strip():
                categories.add(str(case.get("category")))
    if categories != CASE_CATEGORIES:
        issues.append(Issue("error", "incomplete-black-box-cases", "黑盒用例必须完整覆盖七类可观察场景"))


def _validate_adjudication(
    raw: object, version: int, candidate_sha: object,
    bundle: dict[str, object], issues: list[Issue],
) -> None:
    if not isinstance(raw, dict):
        issues.append(Issue("error", "invalid-coordinator-adjudication", "只读协调裁决必须是对象"))
        return
    _closed_fields(raw, ADJUDICATION_FIELDS, "invalid-coordinator-adjudication-fields", issues)
    if (raw.get("agent_id") != bundle.get("adjudicator_agent_id")
            or raw.get("run_id") != bundle.get("adjudicator_run_id")
            or raw.get("candidate_version") != version
            or raw.get("candidate_sha256") != candidate_sha):
        issues.append(Issue("error", "stale-coordinator-adjudication", "协调裁决未绑定同一裁决 Agent/run 和候选"))
    open_fields = ("findings", "uncertainties", "blockers", "disagreements")
    if any(type(raw.get(field)) is not list for field in open_fields):
        issues.append(Issue("error", "invalid-coordinator-adjudication", "协调裁决开放项必须是数组"))
    if raw.get("verdict") == "pass" and any(raw.get(field) != [] for field in open_fields):
        issues.append(Issue("error", "open-native-loop-items", "协调裁决 pass 时不得有开放项"))


def _validate_final(
    data: dict[str, object], root: Path, agent_ids: set[str], run_ids: set[str],
    verifier: HostAttestationVerifier | None, issues: list[Issue],
) -> None:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[-1], dict):
        return
    final = candidates[-1]
    if (data.get("final_candidate_version") != final.get("version")
            or str(data.get("final_candidate_sha256", "")).casefold()
            != str(final.get("candidate_sha256", "")).casefold()):
        issues.append(Issue("error", "stale-final-candidate", "最终候选必须是最后一轮的相同 hash"))
    reviewer = final.get("black_box_reviewer")
    adjudication = final.get("coordinator_adjudication")
    local_pass = (
        isinstance(reviewer, dict) and reviewer.get("verdict") == "pass"
        and isinstance(adjudication, dict) and adjudication.get("verdict") == "pass"
        and all(adjudication.get(field) == [] for field in ("findings", "uncertainties", "blockers", "disagreements"))
    )
    if data.get("stage") == "design-review":
        if data.get("outcome") not in ({"reviewed"} if local_pass else {"incomplete", "blocked"}):
            issues.append(Issue("error", "invalid-native-loop-outcome", "设计评审只能 reviewed；不能冒充运行验收 pass"))
        if data.get("runtime_multi_agent_evidence") != "N/A" or data.get("runtime_multi_agent_evidence_sha256") != "N/A":
            issues.append(Issue("error", "invalid-runtime-evidence-boundary", "设计评审阶段运行证据必须为 N/A"))
        return
    if data.get("outcome") != "pass" or not local_pass:
        issues.append(Issue("error", "invalid-native-loop-outcome", "completion 必须同候选双 pass 且运行黑盒通过"))
    runtime_path = _hashed_file(
        data.get("runtime_multi_agent_evidence"), data.get("runtime_multi_agent_evidence_sha256"), root, issues,
    )
    runtime = _read_path_object(runtime_path, "invalid-runtime-multi-agent-evidence", issues)
    if runtime is None:
        return
    if any(runtime.get(field) != data.get(field) for field in ("baseline_version", "code_version", "build_id")):
        issues.append(Issue("error", "stale-runtime-multi-agent-binding", "运行证据版本/构建与最终候选不一致"))
    if str(runtime.get("candidate_sha256", "")).casefold() != str(data.get("final_candidate_sha256", "")).casefold():
        issues.append(Issue("error", "stale-runtime-candidate-binding", "运行黑盒未绑定最终 candidate_sha256"))
    gates = runtime.get("gates")
    black_box = next((item for item in gates if isinstance(item, dict) and item.get("role") == "BLACK_BOX"), None) if isinstance(gates, list) else None
    if black_box is None:
        issues.append(Issue("error", "missing-runtime-black-box", "completion 缺少真实 BLACK_BOX 执行证据"))
        return
    issues.extend(_convert(validate_native_gate_agent(
        black_box, "BLACK_BOX", str(data.get("module")), root, agent_ids, run_ids,
        verifier, runtime,
    )))
    if black_box.get("verdict") != "pass":
        issues.append(Issue("error", "runtime-black-box-not-pass", "真实 BLACK_BOX verdict 必须为 pass"))


def _read_object(path: Path, code: str) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        return None, [Issue("error", code, str(error))]
    if not isinstance(value, dict):
        return None, [Issue("error", code, "根节点必须是对象")]
    return value, []


def _read_path_object(path: Path | None, code: str, issues: list[Issue]) -> dict[str, object] | None:
    if path is None:
        return None
    value, nested = _read_object(path, code)
    issues.extend(nested)
    return value


def _hashed_file(path_value: object, hash_value: object, root: Path, issues: list[Issue]) -> Path | None:
    if type(path_value) is not str or type(hash_value) is not str:
        issues.append(Issue("error", "unsafe-agent-artifact-path", "证据路径和哈希必须是字符串"))
        return None
    path = Path(path_value)
    if not path_value or path.is_absolute() or path.as_posix() != path_value or ".." in path.parts:
        issues.append(Issue("error", "unsafe-agent-artifact-path", "证据必须是规范项目相对路径"))
        return None
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            issues.append(Issue("error", "unsafe-agent-artifact-path", "证据路径不得经过符号链接"))
            return None
    if not current.is_file():
        issues.append(Issue("error", "missing-agent-artifact", f"证据不存在：{path_value}"))
        return None
    if not _is_sha(hash_value) or hashlib.sha256(current.read_bytes()).hexdigest() != str(hash_value).casefold():
        issues.append(Issue("error", "stale-agent-artifact", f"证据哈希失效：{path_value}"))
    return current


def _closed_fields(data: dict[str, object], fields: set[str], code: str, issues: list[Issue]) -> None:
    if set(data) != fields:
        issues.append(Issue("error", code, "对象含缺失或未知字段"))


def _unique(value: object, used: set[str], issues: list[Issue]) -> None:
    identity = value.strip() if isinstance(value, str) else ""
    if not identity or identity in used:
        issues.append(Issue("error", "reused-native-loop-identity", "父/子角色必须使用不同非空 Agent ID 和 run ID"))
    else:
        used.add(identity)


def _is_sha(value: object) -> bool:
    return type(value) is str and SHA256_RE.fullmatch(value) is not None


def _convert(values: list[object]) -> list[Issue]:
    return [Issue(str(item.severity), str(item.code), str(item.message)) for item in values]


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证原生 GPT-6 方案/黑盒审查闭环和运行黑盒绑定")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_native_review_loop(
        arguments.path, project_root=arguments.project_root, template=arguments.template,
    )
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
