from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path

from delivery_gate_planner import (
    GatePlanError, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
    validate_deleted_files,
)
from strict_json import loads as strict_json_loads
from validate_project_commands import validate_project_commands
from gate_test_results import test_result_passes


PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
STABLE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REQ_ID_RE = re.compile(r"REQ-\d+")
TOP_FIELDS = {
    "schema_version", "contract_id", "stage", "status", "baseline", "artifacts",
    "identity", "change", "repair_policy", "gate_plan", "gate_receipts",
}
ARTIFACT_FIELDS = {
    "traceability", "questions", "development_plan", "progress", "command_manifest",
}
REF_FIELDS = {"path", "sha256"}
IDENTITY_FIELDS = {"code_version", "build_id", "environment_id"}
CHANGE_FIELDS = {
    "delivery_phase", "baseline_frozen",
    "requirement_ids", "modules", "changed_files", "configuration_files", "input_files",
    "direct_dependency_boundaries", "risk_level", "risk_reason", "surfaces", "flow_impact",
    "frontend_applicable", "swimlane_applicable", "cross_module", "human_review_triggered",
}
REPAIR_FIELDS = {"max_rounds", "same_failure_limit", "regression_test_before_fix", "on_exhaustion"}
GATE_RECEIPT_FIELDS = {
    "schema_version", "producer", "command_id", "gate_input_fingerprint",
    "command_argv", "command_argv_sha256", "started_at", "ended_at", "exit_code",
    "verdict", "run_id", "output_path", "output_sha256",
}
STATUS_BY_STAGE = {
    "planning": {"pending", "in_progress"},
    "implementation": {"in_progress"},
    "closure_candidate": {"closure_candidate"},
    "completion": {"completed"},
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_delivery_contract(
    path: Path, *, project_root: Path, template: bool = False,
) -> list[Issue]:
    data, issues = _read_contract(path)
    if data is None:
        return issues
    _validate_shape(data, issues, template)
    if template:
        if not PLACEHOLDER_RE.search(path.read_text(encoding="utf-8")):
            issues.append(Issue("error", "missing-template-placeholder", "公共模板必须保留占位符"))
        return _deduplicate(issues)
    required_objects = (
        "baseline", "artifacts", "identity", "change", "repair_policy", "gate_plan", "gate_receipts",
    )
    if not TOP_FIELDS.issubset(data) or any(not isinstance(data.get(field), dict) for field in required_objects):
        return _deduplicate(issues)
    root = project_root.resolve()
    _validate_refs(data, root, issues)
    _validate_semantics(data, root, issues)
    return _deduplicate(issues)


def _read_contract(path: Path) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [Issue("error", "invalid-delivery-contract", str(error))]
    if not isinstance(data, dict):
        return None, [Issue("error", "invalid-delivery-contract", "交付契约根节点必须是对象")]
    return data, []


def _validate_shape(data: dict[str, object], issues: list[Issue], template: bool) -> None:
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issues.append(Issue("error", "invalid-schema-version", "schema_version 必须是整数 1"))
    if set(data) != TOP_FIELDS:
        issues.append(Issue("error", "invalid-contract-fields", "交付契约含缺失或未知顶层字段"))
    _exact_object(data.get("baseline"), {"version", *REF_FIELDS}, "baseline", issues)
    _exact_object(data.get("artifacts"), ARTIFACT_FIELDS, "artifacts", issues)
    _exact_object(data.get("identity"), IDENTITY_FIELDS, "identity", issues)
    change = data.get("change")
    _exact_object(change, CHANGE_FIELDS | ({"deleted_files"} if isinstance(change, dict) and "deleted_files" in change else set()), "change", issues)
    _exact_object(data.get("repair_policy"), REPAIR_FIELDS, "repair_policy", issues)
    if not isinstance(data.get("gate_plan"), dict):
        issues.append(Issue("error", "invalid-gate-plan", "gate_plan 必须是对象"))
    if not isinstance(data.get("gate_receipts"), dict):
        issues.append(Issue("error", "invalid-gate-receipts", "gate_receipts 必须是对象"))
    artifacts = data.get("artifacts")
    if isinstance(artifacts, dict):
        for name, value in artifacts.items():
            _exact_object(value, REF_FIELDS, f"artifacts.{name}", issues)
    receipts = data.get("gate_receipts")
    if isinstance(receipts, dict):
        for command_id, value in receipts.items():
            if not isinstance(command_id, str) or not command_id:
                issues.append(Issue("error", "invalid-gate-receipts", "gate receipt 命令 ID 必须非空"))
            _exact_object(value, REF_FIELDS, f"gate_receipts.{command_id}", issues)
    if template:
        return
    strings = (data.get("contract_id"), data.get("stage"), data.get("status"))
    if any(not isinstance(value, str) or not value for value in strings):
        issues.append(Issue("error", "invalid-contract-identity", "契约 ID、阶段和状态必须是非空字符串"))


def _exact_object(value: object, fields: set[str], name: str, issues: list[Issue]) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        issues.append(Issue("error", "invalid-contract-fields", f"{name} 含缺失或未知字段"))


def _validate_refs(data: dict[str, object], root: Path, issues: list[Issue]) -> None:
    refs = {"baseline": data["baseline"], **data["artifacts"]}
    for name, value in refs.items():
        if not isinstance(value, dict):
            continue
        raw, declared = value.get("path"), value.get("sha256")
        target = _resolve_file(raw, root, issues, name)
        if not isinstance(declared, str) or SHA256_RE.fullmatch(declared) is None:
            issues.append(Issue("error", "invalid-artifact-sha256", f"{name} 缺少有效 SHA-256"))
        elif target is not None and hashlib.sha256(target.read_bytes()).hexdigest() != declared:
            issues.append(Issue("error", "stale-artifact-sha256", f"{name} 已漂移"))
    change = data["change"]
    if isinstance(change, dict):
        try:
            deleted = validate_deleted_files(change, root)
        except (GatePlanError, TypeError) as error:
            issues.append(Issue("error", "invalid-deleted-files", str(error)))
            deleted = set()
        for field in ("changed_files", "configuration_files", "input_files"):
            values = change.get(field)
            if isinstance(values, list):
                for raw in values:
                    if field != "changed_files" or not isinstance(raw, str) or raw not in deleted:
                        _resolve_file(raw, root, issues, field)


def _resolve_file(raw: object, root: Path, issues: list[Issue], source: str) -> Path | None:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        issues.append(Issue("error", "unsafe-contract-path", f"{source} 必须是安全项目相对路径"))
        return None
    path = root / raw
    if path.is_symlink() or not path.is_file():
        issues.append(Issue("error", "missing-contract-file", f"{source} 文件不存在或为符号链接：{raw}"))
        return None
    try:
        path.resolve().relative_to(root)
    except ValueError:
        issues.append(Issue("error", "unsafe-contract-path", f"{source} 越出项目根：{raw}"))
        return None
    return path


def _validate_semantics(data: dict[str, object], root: Path, issues: list[Issue]) -> None:
    stage, status = data["stage"], data["status"]
    if stage not in STATUS_BY_STAGE or status not in STATUS_BY_STAGE.get(str(stage), set()):
        issues.append(Issue("error", "invalid-stage-status", "stage 与 status 不匹配"))
    if not isinstance(data["contract_id"], str) or STABLE_ID_RE.fullmatch(data["contract_id"]) is None:
        issues.append(Issue("error", "invalid-contract-id", "contract_id 必须是稳定单段标识符"))
    identity = data["identity"]
    if not isinstance(identity, dict) or any(
        type(identity.get(field)) is not str or not identity.get(field, "").strip()
        for field in IDENTITY_FIELDS
    ):
        issues.append(Issue(
            "error", "invalid-candidate-identity", "code_version、build_id、environment_id 必须是非空字符串",
        ))
    baseline = data["baseline"]
    if not isinstance(baseline, dict) or type(baseline.get("version")) is not str or not baseline.get("version", "").strip():
        issues.append(Issue("error", "invalid-candidate-identity", "baseline.version 必须是非空字符串"))
    change = data["change"]
    _validate_change(change, issues)
    _validate_repair_policy(data["repair_policy"], issues)
    if issues:
        return
    try:
        impact = compute_impact_fingerprint(data, root)
        command_fingerprints = compute_command_fingerprints(data, root)
        expected = build_gate_plan(
            change, stage=str(stage), impact_fingerprint=impact,
            command_fingerprints=command_fingerprints,
        )
    except GatePlanError as error:
        issues.append(Issue("error", "invalid-gate-plan-input", str(error)))
        return
    if data["gate_plan"] != expected:
        issues.append(Issue("error", "stale-gate-plan", "gate_plan 与当前事实的确定性规划结果不一致"))
        return
    _validate_planned_commands(data, root, issues)
    _validate_gate_receipts(data, root, issues)


def _validate_gate_receipts(data: dict[str, object], root: Path, issues: list[Issue]) -> None:
    plan = data["gate_plan"]
    receipt_refs = data["gate_receipts"]
    if not isinstance(plan, dict) or not isinstance(receipt_refs, dict):
        return
    fingerprints = plan.get("gate_input_fingerprints")
    if not isinstance(fingerprints, dict):
        return
    expected = {str(item) for item in fingerprints}
    supplied = {str(item) for item in receipt_refs}
    phase = data.get("change", {}).get("delivery_phase")
    if data.get("stage") in {"closure_candidate", "completion"}:
        required = expected
    else:
        required = (
            expected & {"real_entry_acceptance", "targeted_tests"}
            if phase in {"affected_checks_passed", "baseline_frozen", "hardening"}
            else set()
        )
        if bool(data.get("change", {}).get("human_review_triggered")):
            required |= expected & {"automated_review", "multi_agent_evidence"}
    if required:
        for command_id in sorted(required - supplied):
            issues.append(Issue("error", "missing-gate-receipt", f"缺少当前门禁 receipt：{command_id}"))
    for command_id in sorted(supplied - expected):
        issues.append(Issue("error", "unexpected-gate-receipt", f"receipt 不属于当前门禁计划：{command_id}"))
    registered_commands = _registered_commands(data, root)
    for command_id in sorted(expected & supplied):
        ref = receipt_refs.get(command_id)
        if not isinstance(ref, dict):
            continue
        _validate_gate_receipt(
            command_id, ref, fingerprints, registered_commands.get(command_id, {}), root, issues,
        )


def _validate_gate_receipt(
    command_id: str, ref: dict[str, object], fingerprints: dict[str, object],
    command: dict[str, object], root: Path, issues: list[Issue],
) -> None:
    expected_argv = command.get('argv')
    receipt_path = _resolve_file(ref.get("path"), root, issues, f"gate_receipts.{command_id}")
    declared = ref.get("sha256")
    if not isinstance(declared, str) or SHA256_RE.fullmatch(declared) is None:
        issues.append(Issue("error", "invalid-gate-receipt-sha256", f"{command_id} receipt 缺少有效 SHA-256"))
        return
    if receipt_path is None:
        return
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != declared:
        issues.append(Issue("error", "stale-gate-receipt-sha256", f"{command_id} receipt 已漂移"))
        return
    try:
        receipt = strict_json_loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(Issue("error", "invalid-gate-receipt", f"{command_id}: {error}"))
        return
    if not isinstance(receipt, dict) or set(receipt) != GATE_RECEIPT_FIELDS:
        issues.append(Issue("error", "invalid-gate-receipt", f"{command_id} receipt 字段无效"))
        return
    if (type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != 2
            or receipt.get("producer") != "flowctl-gate-runner"
            or receipt.get("command_id") != command_id):
        issues.append(Issue("error", "invalid-gate-receipt", f"{command_id} receipt 身份无效"))
    if receipt.get("gate_input_fingerprint") != fingerprints.get(command_id):
        issues.append(Issue("error", "stale-gate-receipt", f"{command_id} receipt 未绑定当前门禁输入"))
    argv, argv_sha = receipt.get("command_argv"), receipt.get("command_argv_sha256")
    observed_argv_sha = hashlib.sha256(
        "\0".join(argv).encode("utf-8")
    ).hexdigest() if isinstance(argv, list) and all(type(item) is str for item in argv) else None
    if argv != expected_argv or argv_sha != observed_argv_sha:
        issues.append(Issue("error", "gate-receipt-command-mismatch", f"{command_id} receipt 未绑定登记 argv"))
    if not _valid_gate_interval(receipt.get("started_at"), receipt.get("ended_at")):
        issues.append(Issue("error", "invalid-gate-receipt-time", f"{command_id} receipt 执行时间无效"))
    if (receipt.get("verdict") != "pass" or type(receipt.get("exit_code")) is not int
            or receipt.get("exit_code") != 0 or type(receipt.get("run_id")) is not str
            or not receipt.get("run_id", "").strip()):
        issues.append(Issue("error", "gate-receipt-not-pass", f"{command_id} receipt 未通过或 run_id 无效"))
    output = _resolve_file(receipt.get("output_path"), root, issues, f"gate_receipt_output.{command_id}")
    output_sha = receipt.get("output_sha256")
    if not isinstance(output_sha, str) or SHA256_RE.fullmatch(output_sha) is None:
        issues.append(Issue("error", "invalid-gate-output-sha256", f"{command_id} 输出缺少有效 SHA-256"))
    elif output is not None and hashlib.sha256(output.read_bytes()).hexdigest() != output_sha:
        issues.append(Issue("error", "stale-gate-output", f"{command_id} 输出已漂移"))
    elif output is not None and not test_result_passes(
            command_id, expected_argv, output.read_bytes(), result_kind=command.get('result_kind', 'tests')):
        issues.append(Issue("error", "gate-test-result-not-pass", f"{command_id} 缺少非零执行且全部通过的原生测试结果"))


def _registered_commands(data: dict[str, object], root: Path) -> dict[str, dict[str, object]]:
    artifacts = data.get("artifacts")
    manifest_ref = artifacts.get("command_manifest") if isinstance(artifacts, dict) else None
    path = _resolve_file(manifest_ref.get("path"), root, [], "command_manifest") if isinstance(manifest_ref, dict) else None
    if path is None:
        return {}
    try:
        manifest = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {}
    commands = manifest.get("commands") if isinstance(manifest, dict) else None
    return {
        item["id"]: item
        for item in commands if isinstance(commands, list) and isinstance(item, dict)
        and isinstance(item.get("id"), str)
    } if isinstance(commands, list) else {}


def _valid_gate_interval(started: object, ended: object) -> bool:
    if type(started) is not str or type(ended) is not str:
        return False
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    except ValueError:
        return False
    return start.tzinfo is not None and end.tzinfo is not None and start <= end


def _validate_planned_commands(data: dict[str, object], root: Path, issues: list[Issue]) -> None:
    artifacts = data["artifacts"]
    plan = data["gate_plan"]
    manifest_ref = artifacts.get("command_manifest") if isinstance(artifacts, dict) else None
    if not isinstance(manifest_ref, dict):
        return
    manifest_path = _resolve_file(
        manifest_ref.get("path"), root, issues, "artifacts.command_manifest",
    )
    if manifest_path is None:
        return
    for manifest_issue in validate_project_commands(manifest_path, project_root=root):
        issues.append(Issue(manifest_issue.severity, manifest_issue.code, manifest_issue.message))
    try:
        manifest = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(Issue("error", "invalid-command-manifest", str(error)))
        return
    commands = manifest.get("commands") if isinstance(manifest, dict) else None
    if not isinstance(commands, list):
        issues.append(Issue("error", "invalid-command-manifest", "命令清单 commands 必须是数组"))
        return
    applicability = {
        item.get("id"): item.get("applicability")
        for item in commands if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    required = plan.get("required_command_ids") if isinstance(plan, dict) else None
    if isinstance(required, list):
        missing = [command_id for command_id in required if applicability.get(command_id) != "required"]
        if missing:
            issues.append(Issue(
                "error", "planned-command-not-enabled",
                f"确定性门禁要求的命令未启用：{', '.join(map(str, missing))}",
            ))


def _validate_change(change: object, issues: list[Issue]) -> None:
    if not isinstance(change, dict):
        return
    list_fields = ("requirement_ids", "modules", "changed_files", "configuration_files", "input_files", "surfaces")
    for field in list_fields:
        values = change.get(field)
        if not isinstance(values, list) or (field in {"requirement_ids", "modules", "changed_files", "surfaces"} and not values):
            issues.append(Issue("error", "invalid-change-set", f"{field} 必须是适用的非重复数组"))
        elif len(values) != len(set(map(str, values))) or any(not isinstance(item, str) or not item for item in values):
            issues.append(Issue("error", "invalid-change-set", f"{field} 包含重复或非法值"))
    ids = change.get("requirement_ids")
    if isinstance(ids, list) and any(REQ_ID_RE.fullmatch(str(item)) is None for item in ids):
        issues.append(Issue("error", "invalid-requirement-ids", "requirement_ids 必须使用 REQ-数字"))
    for field in ("direct_dependency_boundaries", "risk_reason"):
        if not isinstance(change.get(field), str) or not str(change.get(field)).strip():
            issues.append(Issue("error", "invalid-change-set", f"{field} 必须是非空字符串"))
    for field in (
        "baseline_frozen", "frontend_applicable", "swimlane_applicable",
        "cross_module", "human_review_triggered",
    ):
        if type(change.get(field)) is not bool:
            issues.append(Issue("error", "invalid-change-set", f"{field} 必须是布尔值"))
    modules = change.get("modules")
    surfaces = change.get("surfaces")
    if isinstance(modules, list) and isinstance(surfaces, list):
        expected_cross = len(modules) > 1 or "cross-module" in surfaces
        if change.get("cross_module") is not expected_cross:
            issues.append(Issue("error", "cross-module-mismatch", "cross_module 与模块数或变更面不一致"))


def _validate_repair_policy(value: object, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        return
    valid = (
        type(value.get("max_rounds")) is int and 1 <= value["max_rounds"] <= 3
        and type(value.get("same_failure_limit")) is int and 1 <= value["same_failure_limit"] <= 2
        and value.get("regression_test_before_fix") is True
        and value.get("on_exhaustion") == "block_completion_and_record_open_defect"
    )
    if not valid:
        issues.append(Issue("error", "invalid-repair-policy", "自动修复必须限界、先回归测试且耗尽后阻断完成"))


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证统一交付契约、实时哈希和确定性门禁计划")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_delivery_contract(arguments.path, project_root=arguments.project_root, template=arguments.template)
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
