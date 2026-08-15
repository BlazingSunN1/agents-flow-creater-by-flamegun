from __future__ import annotations

from traceability_common import (
    LINK_RE, PLACEHOLDER_RE, REQUIRED_GATES, STATUSES, TRACE_PREFIXES, Issue,
)
from traceability_parsing import _is_na


def validate_template_tables(
    trace_rows: list[dict[str, str]], trace_numbers: list[int],
    gate_rows: list[dict[str, str]], gate_numbers: list[int],
) -> list[Issue]:
    return [
        *_trace_issues(trace_rows, trace_numbers),
        *_gate_issues(gate_rows, gate_numbers),
    ]


def _trace_issues(rows: list[dict[str, str]], numbers: list[int]) -> list[Issue]:
    issues: list[Issue] = []
    for row, number in zip(rows, numbers):
        if row.get("Status", "").strip() not in STATUSES:
            issues.append(Issue("error", "invalid-trace-status", "模板 Traceability 状态非法", number))
        for column, prefix in TRACE_PREFIXES.items():
            cell = row.get(column, "").strip()
            if column == "UI/UX" and _is_na(cell):
                continue
            links = LINK_RE.findall(cell)
            if not links:
                issues.append(Issue("error", "missing-trace-link", f"模板 {column} 缺少链接", number))
            elif any(not artifact_id.startswith(prefix) for artifact_id, _ in links):
                issues.append(Issue("error", "wrong-id-prefix", f"模板 {column} 编号前缀非法", number))
            elif column == "Requirement" and len({identifier for identifier, _ in links}) != len(links):
                issues.append(Issue("error", "duplicate-requirement-link", "模板 Requirement 单元格编号必须唯一", number))
    return issues


def _gate_issues(rows: list[dict[str, str]], numbers: list[int]) -> list[Issue]:
    issues: list[Issue] = []
    gates = [row.get("Gate", "").strip() for row in rows]
    for gate in REQUIRED_GATES - set(gates):
        issues.append(Issue("error", "missing-independent-gate", f"模板缺少独立门禁：{gate}"))
    if len(gates) != len(set(gates)):
        issues.append(Issue("error", "duplicate-gate", "模板包含重复独立门禁"))
    for row, number in zip(rows, numbers):
        gate = row.get("Gate", "").strip()
        applicability = row.get("Applicability", "").strip()
        verdict = row.get("Verdict", "").strip()
        if gate not in REQUIRED_GATES:
            issues.append(Issue("error", "invalid-gate", f"模板未知门禁：{gate}", number))
        elif gate in {"ACCEPTANCE_CASES", "BLACK_BOX"} and applicability != "required":
            issues.append(Issue("error", "invalid-gate-applicability", f"模板 {gate} 必须 required", number))
        elif gate == "UI_UX" and not _valid_ui_applicability(applicability):
            issues.append(Issue("error", "invalid-gate-applicability", "模板 UI_UX applicability 非法", number))
        if verdict not in {"pending", "not_applicable"} and not PLACEHOLDER_RE.fullmatch(verdict):
            issues.append(Issue("error", "invalid-gate-verdict", f"模板门禁不得预置 {verdict} 结论", number))
    return issues


def _valid_ui_applicability(value: str) -> bool:
    return value == "required" or bool(PLACEHOLDER_RE.fullmatch(value)) or _is_na(value)
