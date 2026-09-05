"""Bind optional trace exemptions to verified planner inputs, never completion receipts."""
from __future__ import annotations

from pathlib import Path

from traceability_common import Issue, LINK_RE
from validate_delivery_contract import validate_delivery_contract_inputs


def trace_gate_applicability(
    contract_path: Path | None, trace_path: Path, metadata: dict[str, str],
    root: Path, stage: str, issues: list[Issue],
) -> tuple[set[str], set[str]]:
    if contract_path is None:
        return set(), set()
    data, contract_issues = validate_delivery_contract_inputs(contract_path, project_root=root)
    issues.extend(Issue(item.severity, f"contract-{item.code}", item.message) for item in contract_issues)
    if data is None:
        return set(), set()
    baseline, identity, change = data["baseline"], data["identity"], data["change"]
    expected = {
        "Baseline artifact": baseline["path"], "Baseline version": baseline["version"],
        "Baseline SHA-256": baseline["sha256"], "Code version": identity["code_version"],
        "Build ID": identity["build_id"], "Acceptance environment": identity["environment_id"],
        "Risk level": change["risk_level"], "Risk reason": change["risk_reason"],
    }
    if (data["stage"] != stage
            or (root / data["artifacts"]["traceability"]["path"]).resolve() != trace_path.resolve()
            or any(metadata.get(key) != value for key, value in expected.items())
            or {item.strip() for item in metadata.get("Change surfaces", "").split(",")} != set(change["surfaces"])):
        issues.append(Issue("error", "contract-trace-mismatch", "追踪矩阵与交付契约的路径、阶段或候选元数据不一致"))
        return set(), set()
    columns = set()
    if change["swimlane_applicable"] is False and change["flow_impact"] == "none":
        columns.add("Flow")
    if "BLACK_BOX" not in data["gate_plan"]["independent_roles"]:
        columns.add("Black-box result")
    return columns, set(change["requirement_ids"])


def trace_na_issues(
    row: dict[str, str], column: str, row_number: int, surfaces: set[str],
    optional_columns: set[str] | None, selected_requirements: set[str] | None,
) -> list[Issue]:
    if column == "UI/UX":
        return ([Issue("error", "ui-artifact-required", "实际 UI 变更不能把 UI/UX 工件标记为 N/A", row_number)]
                if "ui" in surfaces else [])
    requirements = {identifier for identifier, _ in LINK_RE.findall(row["Requirement"])}
    if (column in (optional_columns or set()) and requirements
            and requirements <= (selected_requirements or set())):
        return []
    return [Issue("error", "invalid-na", f"{column} 不允许 N/A", row_number)]
