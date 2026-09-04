from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from authority_binding_validation import authority_binding_issues, authority_metadata_issues

from traceability_common import (
    ALLOWED_SURFACES,
    FINDING_COLUMNS,
    FINDING_ROUTES,
    GATE_COLUMNS,
    HIGH_RISK_SURFACES,
    Issue,
    LINK_RE,
    PLACEHOLDER_RE,
    REQUIRED_GATES,
    REQUIRED_METADATA,
    RISK_ORDER,
    STANDARD_SURFACES,
    STATUSES,
    TRACE_COLUMNS,
    TRACE_PREFIXES, VALIDATION_STAGES, VERDICTS,
    required_independent_roles,
)
from traceability_parsing import (
    _deduplicate,
    _findings_none_is_mixed,
    _is_na,
    _metadata_duplicates,
    _parse_metadata,
    _parse_table,
    _resolve_project_path,
)
from trace_template_validation import validate_template_tables
from trace_stage_validation import black_box_not_started, pending_black_box_issues
from trace_row_identity_validation import requirement_identity_issues
from trace_baseline_validation import _validate_baseline

def validate_traceability(
    path: Path,
    *,
    project_root: Path,
    template: bool = False,
    stage: str = "completion",
) -> list[Issue]:
    issues: list[Issue] = []
    text = _read_traceability(path, issues)
    if text is None:
        return issues
    _validate_document_shape(text, template, stage, issues)
    metadata = _validate_metadata(text, issues)
    tables = _parse_required_tables(text, template, issues)
    if template:
        issues.extend(Issue("error", code, message) for code, message in authority_metadata_issues(metadata))
        issues.extend(validate_template_tables(tables[0], tables[1], tables[2], tables[3]))
        return _deduplicate(issues)
    trace_rows, trace_numbers, gate_rows, gate_numbers, finding_rows, finding_numbers = tables
    root = project_root.resolve()
    issues.extend(
        Issue("error", code, message)
        for code, message in authority_binding_issues(metadata, root)
    )
    surfaces = _validate_risk(metadata, issues)
    expected_sha = _validate_baseline(metadata, root, issues)
    _validate_trace_rows(trace_rows, trace_numbers, surfaces, root, issues)
    gates = _validate_gate_rows(gate_rows, gate_numbers, metadata, expected_sha, surfaces, root, stage, issues)
    open_findings = _validate_finding_rows(finding_rows, finding_numbers, root, issues)
    _validate_stage(stage, trace_rows, gates, metadata, surfaces, open_findings, issues)
    return _deduplicate(issues)


def _read_traceability(path: Path, issues: list[Issue]) -> str | None:
    try:
        payload = path.read_bytes()
    except OSError as error:
        issues.append(Issue("error", "unreadable-file", f"无法读取追踪矩阵：{error}"))
        return None
    if b"\x00" in payload:
        issues.append(Issue("error", "nul-byte", "追踪矩阵包含 NUL 字节"))
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        issues.append(Issue("error", "invalid-utf8", f"追踪矩阵不是有效 UTF-8：{error.start}"))
        return None


def _validate_document_shape(text: str, template: bool, stage: str, issues: list[Issue]) -> None:
    if not template and PLACEHOLDER_RE.search(text):
        issues.append(Issue("error", "placeholder", "项目追踪矩阵包含未解析占位符"))
    if stage not in VALIDATION_STAGES:
        issues.append(Issue("error", "invalid-stage", "stage 必须是 implementation、closure_candidate 或 completion"))


def _validate_metadata(text: str, issues: list[Issue]) -> dict[str, str]:
    metadata = _parse_metadata(text)
    for field, row in _metadata_duplicates(text):
        issues.append(Issue("error", "duplicate-metadata", f"追踪元数据重复：{field}", row))
    for field in REQUIRED_METADATA:
        if field not in metadata or not metadata[field].strip():
            issues.append(Issue("error", "missing-metadata", f"缺少元数据：{field}"))
    return metadata


def _parse_required_tables(
    text: str, template: bool, issues: list[Issue],
) -> tuple[list[dict[str, str]], list[int], list[dict[str, str]], list[int], list[dict[str, str]], list[int]]:
    trace_rows, trace_numbers, trace_issues = _parse_table(text, "Traceability", TRACE_COLUMNS)
    gate_rows, gate_numbers, gate_issues = _parse_table(text, "Independent Gate Evidence", GATE_COLUMNS)
    finding_rows, finding_numbers, finding_issues = _parse_table(
        text, "Open Findings", FINDING_COLUMNS, allow_none=True,
    )
    issues.extend(trace_issues + gate_issues + finding_issues)
    if not template and _findings_none_is_mixed(text):
        issues.append(Issue("error", "ambiguous-findings", "Open Findings 不能同时包含 None 和问题表"))
    missing = (
        (trace_rows, "missing-trace-table", "缺少标准 Traceability 表格"),
        (gate_rows, "missing-gate-table", "缺少标准 Independent Gate Evidence 表格"),
        (finding_rows, "missing-findings-section", "缺少 Open Findings 章节"),
    )
    for rows, code, message in missing:
        if rows is None:
            issues.append(Issue("error", code, message))
    return (
        trace_rows or [], trace_numbers, gate_rows or [], gate_numbers,
        finding_rows or [], finding_numbers,
    )


def _validate_risk(metadata: dict[str, str], issues: list[Issue]) -> set[str]:
    risk = metadata.get("Risk level", "")
    surfaces = {
        item.strip().casefold()
        for item in metadata.get("Change surfaces", "").split(",")
        if item.strip()
    }
    if risk not in RISK_ORDER:
        issues.append(Issue("error", "invalid-risk-level", "Risk level 必须是 small、standard 或 high-risk"))
    else:
        required_risk = "small"
        if surfaces & STANDARD_SURFACES:
            required_risk = "standard"
        if surfaces & HIGH_RISK_SURFACES:
            required_risk = "high-risk"
        if RISK_ORDER[risk] < RISK_ORDER[required_risk]:
            issues.append(
                Issue(
                    "error",
                    "risk-underclassified",
                    f"Change surfaces 至少要求 {required_risk}，当前为 {risk}",
                )
            )
    if not surfaces:
        issues.append(Issue("error", "missing-change-surfaces", "Change surfaces 不能为空"))
    unknown_surfaces = surfaces - ALLOWED_SURFACES
    if unknown_surfaces:
        issues.append(
            Issue(
                "error",
                "unknown-change-surface",
                f"未知 Change surfaces 必须先归类并按 high-risk 处理：{', '.join(sorted(unknown_surfaces))}",
            )
        )
        if risk in RISK_ORDER and RISK_ORDER[risk] < RISK_ORDER["high-risk"]:
            issues.append(Issue("error", "risk-underclassified", "未知变更面要求 high-risk"))
    if not metadata.get("Risk reason", "").strip():
        issues.append(Issue("error", "missing-risk-reason", "Risk reason 不能为空"))
    return surfaces


def _validate_trace_rows(trace_rows: list[dict[str, str]], row_numbers: list[int], surfaces: set[str], root: Path, issues: list[Issue]) -> None:
    artifact_ids: dict[str, tuple[str, int]] = {}
    requirement_rows: dict[str, int] = {}
    artifact_roles: dict[tuple[int, int], str] = {}
    artifact_content_roles: dict[str, str] = {}
    if not trace_rows:
        issues.append(Issue("error", "empty-trace-table", "Traceability 至少需要一条需求追踪记录"))
    for row, row_number in zip(trace_rows, row_numbers):
        status = row["Status"].strip()
        if status not in STATUSES:
            issues.append(Issue("error", "invalid-trace-status", f"非法追踪状态：{status}", row_number))
        for column, prefix in TRACE_PREFIXES.items():
            cell = row[column].strip()
            if _is_na(cell):
                if column != "UI/UX":
                    issues.append(Issue("error", "invalid-na", f"{column} 不允许 N/A", row_number))
                elif "ui" in surfaces:
                    issues.append(Issue("error", "ui-artifact-required", "实际 UI 变更不能把 UI/UX 工件标记为 N/A", row_number))
                continue
            links = LINK_RE.findall(cell)
            if not links:
                issues.append(Issue("error", "missing-trace-link", f"{column} 必须使用带路径的 {prefix} Markdown 链接", row_number))
                continue
            issues.extend(requirement_identity_issues(column, links, row_number, requirement_rows))
            for artifact_id, artifact_path in links:
                if not artifact_id.startswith(prefix):
                    issues.append(Issue("error", "wrong-id-prefix", f"{column} 使用了错误编号 {artifact_id}", row_number))
                normalized_path = artifact_path.strip()
                previous = artifact_ids.get(artifact_id)
                if previous is not None and previous[0] != normalized_path:
                    issues.append(
                        Issue(
                            "error",
                            "conflicting-trace-id",
                            f"编号 {artifact_id} 在第 {previous[1]} 行映射到 {previous[0]}，当前却映射到 {normalized_path}",
                            row_number,
                        )
                    )
                else:
                    artifact_ids[artifact_id] = (normalized_path, row_number)
                resolved = _resolve_project_path(artifact_path, root, issues, "trace-artifact", row_number)
                if resolved and resolved.is_file() and (issue := _trace_role_reuse_issue(
                    resolved, column, artifact_path, row_number, artifact_roles, artifact_content_roles,
                )):
                    issues.append(issue)
                if resolved and column == "Code module" and not resolved.exists():
                    issues.append(Issue("error", "missing-code-module", f"代码模块不存在：{artifact_path}", row_number))
        if status == "completed" and any(not row[column].strip() for column in TRACE_PREFIXES):
            issues.append(Issue("error", "incomplete-completed-row", "completed 行存在空追踪单元格", row_number))


def _trace_role_reuse_issue(
    resolved: Path, column: str, artifact_path: str, row_number: int,
    artifact_roles: dict[tuple[int, int], str],
    artifact_content_roles: dict[str, str],
) -> Issue | None:
    identity = (resolved.stat().st_dev, resolved.stat().st_ino)
    digest = _semantic_artifact_digest(resolved)
    previous_role = artifact_roles.get(identity) or artifact_content_roles.get(digest)
    artifact_roles[identity] = column
    artifact_content_roles[digest] = column
    if previous_role is None or previous_role == column:
        return None
    return Issue(
        "error", "reused-trace-artifact-role",
        f"{column} 与 {previous_role} 不能复用同一语义工件：{artifact_path}", row_number,
    )


def _semantic_artifact_digest(path: Path) -> str:
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        canonical = payload
    else:
        normalized = unicodedata.normalize("NFC", text)
        visible = "".join(character for character in normalized if unicodedata.category(character) != "Cf")
        lines = [line.rstrip(" \t") for line in visible.splitlines()]
        canonical = "\n".join(lines).strip("\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_gate_rows(
    gate_rows: list[dict[str, str]],
    row_numbers: list[int],
    metadata: dict[str, str],
    expected_sha: str,
    surfaces: set[str],
    root: Path,
    stage: str,
    issues: list[Issue],
) -> dict[str, dict[str, str]]:
    gates: dict[str, dict[str, str]] = {}
    agent_run_ids: dict[str, str] = {}
    implementation_run_id = metadata.get("Implementation run ID", "").strip()
    required_roles = required_independent_roles(metadata.get("Risk level", ""), surfaces, stage)
    for row, row_number in zip(gate_rows, row_numbers):
        gate = row["Gate"].strip()
        if gate not in REQUIRED_GATES:
            issues.append(Issue("error", "invalid-gate", f"未知独立门禁：{gate}", row_number))
            continue
        if gate in gates:
            issues.append(Issue("error", "duplicate-gate", f"独立门禁重复：{gate}", row_number))
        gates[gate] = row
        if _validate_gate_applicability(
            gate, row, row_number, required_roles, stage, issues,
        ):
            continue
        if gate == "BLACK_BOX" and stage == "implementation":
            if not black_box_not_started(row):
                issues.append(Issue(
                    "error", "implementation-black-box-started",
                    "implementation 阶段 BLACK_BOX 必须明确为未启动且不得携带 run/input/output", row_number,
                ))
            issues.extend(Issue("error", code, message, row_number) for code, message in pending_black_box_issues(row, metadata, expected_sha))
            continue
        _validate_required_gate(
            gate,
            row,
            row_number,
            metadata,
            expected_sha,
            implementation_run_id,
            agent_run_ids,
            root,
            issues,
        )

    for gate in REQUIRED_GATES:
        if gate not in gates:
            issues.append(Issue("error", "missing-independent-gate", f"缺少独立门禁：{gate}"))
    return gates


def _validate_gate_applicability(
    gate: str,
    row: dict[str, str],
    row_number: int,
    required_roles: set[str],
    stage: str,
    issues: list[Issue],
) -> bool:
    applicability = row["Applicability"].strip()
    if applicability == "required":
        if stage in {"closure_candidate", "completion"} and gate not in required_roles:
            issues.append(Issue(
                "error", "nonapplicable-independent-gate",
                f"当前 gate plan 不要求 {gate}，不得启动额外独立 Agent", row_number,
            ))
        return False
    if not _is_na(applicability):
        issues.append(Issue("error", "invalid-gate-applicability", f"{gate} 的 Applicability 必须是 required 或 N/A: 原因", row_number))
        return False
    if stage in {"closure_candidate", "completion"} and gate in required_roles:
        issues.append(Issue(
            "error", "required-independent-gate-not-applicable",
            f"当前 gate plan 要求 {gate}，不得标记为不适用", row_number,
        ))
    if row["Verdict"].strip() != "not_applicable":
        issues.append(Issue("error", "invalid-gate-verdict", "不适用的独立门禁必须使用 not_applicable 结论", row_number))
    return True


def _validate_required_gate(
    gate: str,
    row: dict[str, str],
    row_number: int,
    metadata: dict[str, str],
    expected_sha: str,
    implementation_run_id: str,
    agent_run_ids: dict[str, str],
    root: Path,
    issues: list[Issue],
) -> None:
    _validate_agent_run_id(gate, row["Agent run ID"].strip(), row_number, implementation_run_id, agent_run_ids, issues)
    if row["Input baseline version"].strip() != metadata.get("Baseline version", "").strip():
        issues.append(Issue("error", "stale-gate-baseline-version", f"{gate} 的需求基线版本不一致", row_number))
    if row["Input baseline SHA-256"].strip().casefold() != expected_sha:
        issues.append(Issue("error", "stale-gate-baseline-hash", f"{gate} 的需求基线哈希不一致", row_number))
    _validate_gate_artifacts(gate, row, row_number, root, issues)
    verdict = row["Verdict"].strip()
    if verdict not in VERDICTS:
        issues.append(Issue("error", "invalid-gate-verdict", f"{gate} 的 Verdict 非法：{verdict}", row_number))
    if gate == "BLACK_BOX":
        _validate_black_box_binding(row, row_number, metadata, issues)


def _validate_agent_run_id(
    gate: str,
    run_id: str,
    row_number: int,
    implementation_run_id: str,
    run_ids: dict[str, str],
    issues: list[Issue],
) -> None:
    if not run_id:
        issues.append(Issue("error", "missing-agent-run-id", f"{gate} 缺少 Agent run ID", row_number))
    elif run_id == implementation_run_id:
        issues.append(Issue("error", "self-certified-gate", f"{gate} 使用了实现 Agent 的 run ID", row_number))
    elif run_id in run_ids:
        issues.append(Issue("error", "reused-independent-agent", f"{gate} 与 {run_ids[run_id]} 复用了同一 Agent run ID", row_number))
    else:
        run_ids[run_id] = gate


def _validate_gate_artifacts(
    gate: str,
    row: dict[str, str],
    row_number: int,
    root: Path,
    issues: list[Issue],
) -> None:
    for column in ("Input manifest", "Output evidence"):
        links = LINK_RE.findall(row[column])
        if len(links) != 1:
            issues.append(Issue("error", "invalid-gate-artifact", f"{gate} 的 {column} 必须是单个带路径链接", row_number))
        else:
            _resolve_project_path(links[0][1], root, issues, "gate-artifact", row_number)


def _validate_black_box_binding(
    row: dict[str, str],
    row_number: int,
    metadata: dict[str, str],
    issues: list[Issue],
) -> None:
    if row["Code version"].strip() != metadata.get("Code version", "").strip():
        issues.append(Issue("error", "stale-black-box-code-version", "黑盒验收的 Code version 已过期", row_number))
    if row["Build ID"].strip() != metadata.get("Build ID", "").strip():
        issues.append(Issue("error", "stale-black-box-build", "黑盒验收的 Build ID 已过期", row_number))


def _validate_finding_rows(
    finding_rows: list[dict[str, str]],
    row_numbers: list[int],
    root: Path,
    issues: list[Issue],
) -> bool:
    open_findings = False
    for row, row_number in zip(finding_rows, row_numbers):
        finding_class = row["Class"].strip()
        expected_route = FINDING_ROUTES.get(finding_class)
        if expected_route is None:
            issues.append(Issue("error", "invalid-finding-class", f"未知失败分类：{finding_class}", row_number))
        elif row["Route"].strip() != expected_route:
            issues.append(Issue("error", "wrong-finding-route", f"{finding_class} 必须路由到 {expected_route}", row_number))
        status = row["Status"].strip()
        if status not in {"open", "resolved"}:
            issues.append(Issue("error", "invalid-finding-status", f"非法问题状态：{status}", row_number))
        open_findings = open_findings or status == "open"
        links = LINK_RE.findall(row["Evidence"])
        if len(links) != 1:
            issues.append(Issue("error", "missing-finding-evidence", "问题记录必须包含单个证据链接", row_number))
        else:
            _resolve_project_path(links[0][1], root, issues, "finding-evidence", row_number)
    return open_findings


def _validate_stage(
    stage: str,
    trace_rows: list[dict[str, str]],
    gates: dict[str, dict[str, str]],
    metadata: dict[str, str],
    surfaces: set[str],
    open_findings: bool,
    issues: list[Issue],
) -> None:
    required_pass_gates = required_independent_roles(
        metadata.get("Risk level", ""), surfaces, stage,
    ) & REQUIRED_GATES
    if stage == "completion":
        if any(row.get("Status", "").strip() != "completed" for row in trace_rows):
            issues.append(Issue("error", "trace-not-completed", "completion 阶段要求所有追踪行均为 completed"))
    for gate in required_pass_gates:
        if gates.get(gate, {}).get("Verdict", "").strip() != "pass":
            issues.append(Issue("error", "gate-not-passed", f"{stage} 阶段要求 {gate}=pass"))
    if open_findings:
        issues.append(Issue("error", "open-findings", f"仍有 open 问题，不能通过 {stage} 阶段"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="失败关闭地验证需求追踪矩阵与独立验收证据")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true", help="只校验公共模板结构和 UTF-8")
    parser.add_argument("--stage", choices=VALIDATION_STAGES, default="completion")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    issues = validate_traceability(
        arguments.path,
        project_root=arguments.project_root,
        template=arguments.template,
        stage=arguments.stage,
    )
    failed = any(issue.severity == "error" for issue in issues)
    if arguments.json:
        print(
            json.dumps(
                {
                    "path": str(arguments.path),
                    "project_root": str(arguments.project_root),
                    "template": arguments.template,
                    "valid": not failed,
                    "issues": [asdict(issue) for issue in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in issues:
            location = f":{issue.row}" if issue.row else ""
            print(f"{issue.severity.upper()} {issue.code} {arguments.path}{location} {issue.message}")
        print(f"errors={sum(issue.severity == 'error' for issue in issues)} valid={str(not failed).lower()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
