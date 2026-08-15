from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from delivery_record_validation import validate_declared_records
from validate_agents_md import validate_bytes
from validate_context_manifest import _parse_metadata as parse_context_metadata
from validate_context_manifest import _paths_fingerprint, _split_paths
from validate_context_manifest import validate_context_manifest
from validate_frontend_evidence import validate_frontend_evidence
from validate_multi_agent_evidence import validate_multi_agent_evidence
from validate_project_commands import validate_project_commands
from validate_swimlane_evidence import validate_swimlane_evidence
from validate_traceability import TRACE_COLUMNS, _parse_metadata as parse_trace_metadata
from validate_traceability import _parse_table as parse_trace_table
from validate_traceability import validate_traceability
from traceability_common import LINK_RE
from trace_workset_binding import (
    binding_issue_codes, encode_module_requirement_ids, module_requirement_ids,
)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    source: str


def validate_delivery_bundle(
    *,
    agents_path: Path,
    trace_path: Path,
    context_path: Path,
    command_manifest_path: Path,
    multi_agent_evidence_path: Path,
    swimlane_evidence_path: Path | None,
    project_root: Path,
    frontend_evidence_path: Path | None = None,
    stage: str = "completion",
    allow_passwords: bool = False,
) -> list[Issue]:
    issues = _validate_agents(agents_path, allow_passwords)
    issues.extend(_validate_core_evidence(
        trace_path, context_path, command_manifest_path,
        multi_agent_evidence_path, project_root, stage,
    ))
    issues.extend(_validate_swimlane_bundle(
        swimlane_evidence_path, trace_path, context_path, project_root,
    ))
    issues.extend(_validate_frontend_bundle(
        frontend_evidence_path, command_manifest_path, trace_path,
        multi_agent_evidence_path, project_root, stage, issues,
    ))
    issues.extend(_validate_cross_artifact_binding(
        agents_path, trace_path, context_path, command_manifest_path,
        multi_agent_evidence_path, swimlane_evidence_path, frontend_evidence_path,
        project_root, stage,
    ))
    return _deduplicate(issues)


def _validate_agents(path: Path, allow_passwords: bool) -> list[Issue]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        return [Issue("error", "unreadable-agents", str(error), str(path))]
    return [
        Issue(item.severity, f"agents-{item.code}", item.message, str(path))
        for item in validate_bytes(
            payload, mode="project", scope="root", allow_passwords=allow_passwords,
        )
    ]


def _validate_core_evidence(
    trace: Path, context: Path, commands: Path, agents: Path,
    root: Path, stage: str,
) -> list[Issue]:
    issues = [
        Issue(item.severity, f"trace-{item.code}", item.message, str(trace))
        for item in validate_traceability(trace, project_root=root, stage=stage)
    ]
    validators = (
        ("context", context, validate_context_manifest(context, project_root=root)),
        ("commands", commands, validate_project_commands(commands, project_root=root)),
        ("agents-evidence", agents, validate_multi_agent_evidence(
            agents, trace_path=trace, context_path=context, project_root=root, stage=stage,
        )),
    )
    for prefix, path, found in validators:
        issues.extend(Issue(item.severity, f"{prefix}-{item.code}", item.message, str(path)) for item in found)
    return issues


def _validate_swimlane_bundle(
    evidence: Path | None, trace: Path, context: Path, root: Path,
) -> list[Issue]:
    if evidence is None:
        return [Issue("error", "missing-swimlane-evidence", "代码交付缺少系统/模块泳道同步证据", "delivery-bundle")]
    return [
        Issue(item.severity, f"swimlane-{item.code}", item.message, str(evidence))
        for item in validate_swimlane_evidence(
            evidence, trace_path=trace, context_path=context, project_root=root,
        )
    ]


def _validate_frontend_bundle(
    evidence: Path | None, commands: Path, trace: Path, agents: Path,
    root: Path, stage: str, issues: list[Issue],
) -> list[Issue]:
    applicable = _frontend_applicable(commands, trace, stage, issues)
    if applicable and evidence is None:
        return [Issue("error", "missing-frontend-evidence", "前端项目缺少结构化浏览器和 E2E 证据", "delivery-bundle")]
    if evidence is None:
        return []
    found = [
        Issue(item.severity, f"frontend-{item.code}", item.message, str(evidence))
        for item in validate_frontend_evidence(
            evidence, trace_path=trace, command_manifest=commands, project_root=root,
        )
    ]
    if stage == "completion":
        found.extend(_validate_frontend_black_box_binding(evidence, agents))
    return found


def _frontend_applicable(path: Path, trace_path: Path, stage: str, issues: list[Issue]) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(Issue("error", "unreadable-command-applicability", str(error), str(path)))
        return False
    command_applicable = isinstance(data, dict) and data.get("frontend_applicable") is True
    try:
        trace = parse_trace_metadata(trace_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return command_applicable
    surfaces = {part.strip().casefold() for part in trace.get("Change surfaces", "").split(",")}
    trace_applicable = bool(surfaces & {"ui", "mobile", "touch", "responsive"})
    if trace_applicable and not command_applicable:
        issues.append(Issue("error", "frontend-applicability-mismatch", "命令清单前端适用性与追踪变更面不一致", "delivery-bundle"))
    return command_applicable or trace_applicable


def _validate_cross_artifact_binding(
    agents_path: Path,
    trace_path: Path,
    context_path: Path,
    command_manifest_path: Path,
    multi_agent_evidence_path: Path,
    swimlane_evidence_path: Path | None,
    frontend_evidence_path: Path | None,
    project_root: Path,
    stage: str,
) -> list[Issue]:
    try:
        trace_text = trace_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [Issue("error", "bundle-unreadable-metadata", str(error), "delivery-bundle")]
    trace = parse_trace_metadata(trace_text)
    context, duplicates = parse_context_metadata(context_text)
    if duplicates:
        return []
    issues = _metadata_binding_issues(trace, context, trace_text, project_root)
    record_context = _record_context(trace_text, context, project_root)
    issues.extend(validate_declared_records(
        agents_path, trace, record_context, project_root, stage,
        multi_agent_evidence_path, swimlane_evidence_path, frontend_evidence_path,
        command_manifest_path, context_path,
    ))
    expected_manifest = context.get("Command manifest fingerprint", "").casefold()
    raw_manifest_path = context.get("Command manifest", "")
    try:
        manifest_payload = command_manifest_path.read_bytes()
    except OSError as error:
        issues.append(Issue(
            "error", "bundle-command-manifest-unreadable", str(error), str(command_manifest_path),
        ))
        return issues
    file_hash = hashlib.sha256(manifest_payload).hexdigest()
    actual_manifest = hashlib.sha256(f"{raw_manifest_path}\0{file_hash}".encode("utf-8")).hexdigest()
    if expected_manifest and expected_manifest != actual_manifest:
        issues.append(Issue("error", "bundle-command-manifest-mismatch", "命令清单与工作集指纹不一致", "delivery-bundle"))
    raw_agents_paths = context.get("Effective AGENTS files", "")
    expected_agents = context.get("Effective AGENTS fingerprint", "").casefold()
    root = project_root.resolve()
    declared_agents = {(root / raw).resolve() for raw in _split_paths(raw_agents_paths)}
    if agents_path.resolve() not in declared_agents:
        issues.append(Issue("error", "bundle-agents-path-mismatch", "根 AGENTS 未列入工作集的生效规则链", "delivery-bundle"))
    actual_agents = _paths_fingerprint(raw_agents_paths, root, [], "agents-file")
    if expected_agents and expected_agents != actual_agents:
        issues.append(Issue("error", "bundle-agents-mismatch", "生效 AGENTS 规则链与工作集指纹不一致", "delivery-bundle"))
    return issues


def _record_context(trace_text: str, context: dict[str, str], root: Path) -> dict[str, str]:
    result = dict(context)
    result["_Module requirement IDs"] = encode_module_requirement_ids(
        module_requirement_ids(trace_text, context, root)
    )
    return result


def _metadata_binding_issues(
    trace: dict[str, str], context: dict[str, str], trace_text: str, root: Path,
) -> list[Issue]:
    comparisons = (
        ("Baseline version", "Baseline version", "bundle-baseline-version-mismatch"),
        ("Baseline SHA-256", "Baseline SHA-256", "bundle-baseline-hash-mismatch"),
        ("Code version", "Code version", "bundle-code-version-mismatch"),
        ("Build ID", "Build ID", "bundle-build-id-mismatch"),
        ("Implementation run ID", "Run ID", "bundle-run-id-mismatch"),
    )
    issues: list[Issue] = []
    for trace_field, context_field, code in comparisons:
        trace_value = trace.get(trace_field, "").strip().casefold()
        context_value = context.get(context_field, "").strip().casefold()
        if trace_value and context_value and trace_value != context_value:
            issues.append(Issue(
                "error", code,
                f"追踪矩阵 {trace_field} 与工作集 {context_field} 不一致",
                "delivery-bundle",
            ))
    expected_risk = [trace.get("Risk level", "").strip(), trace.get("Risk reason", "").strip()]
    context_risk = [part.strip() for part in context.get("Risk / expansion reason", "").split(";")]
    if (any(not part for part in expected_risk) or len(context_risk) != 3
            or context_risk[:2] != expected_risk or not context_risk[2]):
        issues.append(Issue(
            "error", "bundle-risk-context-mismatch",
            "工作集风险等级和原因必须绑定追踪矩阵", "delivery-bundle",
        ))
    trace_rows, _, _ = parse_trace_table(trace_text, "Traceability", TRACE_COLUMNS)
    trace_ids = {
        identifier
        for row in trace_rows or []
        for identifier, _ in LINK_RE.findall(row.get("Requirement", ""))
        if re.fullmatch(r"REQ-\d+", identifier)
    }
    context_ids = {item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()}
    if not context_ids or not context_ids <= trace_ids:
        issues.append(Issue(
            "error", "bundle-requirement-ids-mismatch",
            "工作集 Requirement IDs 必须是追踪矩阵中的非空当前需求子集",
            "delivery-bundle",
        ))
    for code in binding_issue_codes(trace_text, context, root):
        issues.append(Issue(
            "error", code,
            "当前 Changed files 必须由所选 Requirement IDs 的 Code module 工件完整覆盖",
            "delivery-bundle",
        ))
    return issues


def _validate_frontend_black_box_binding(frontend_path: Path, multi_agent_path: Path) -> list[Issue]:
    try:
        frontend = json.loads(frontend_path.read_text(encoding="utf-8"))
        agents = json.loads(multi_agent_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [Issue("error", "frontend-verifier-binding-unreadable", str(error), "delivery-bundle")]
    browser = frontend.get("browser", {}) if isinstance(frontend, dict) else {}
    gates = agents.get("gates", []) if isinstance(agents, dict) else []
    black_box = next(
        (gate for gate in gates if isinstance(gate, dict) and gate.get("role") == "BLACK_BOX"),
        None,
    )
    browser_objects = [browser]
    if isinstance(frontend, dict) and isinstance(frontend.get("mobile"), dict):
        browser_objects.append(frontend["mobile"])
    verifiers = [item.get("verifier_agent_run_id") for item in browser_objects if isinstance(item, dict)]
    if black_box is None or any(verifier != black_box.get("run_id") for verifier in verifiers):
        return [Issue(
            "error", "frontend-black-box-run-mismatch",
            "前端应用内浏览器转录必须绑定当前独立 BLACK_BOX Agent run ID",
            "delivery-bundle",
        )]
    return []


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message, item.source): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 AGENTS、追踪矩阵和工作集属于同一交付基线")
    parser.add_argument("--agents", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--command-manifest", type=Path, required=True)
    parser.add_argument("--multi-agent-evidence", type=Path, required=True)
    parser.add_argument("--swimlane-evidence", type=Path, required=True)
    parser.add_argument("--frontend-evidence", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--stage", choices=("implementation", "completion"), default="completion")
    parser.add_argument("--allow-passwords", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_delivery_bundle(
        agents_path=arguments.agents,
        trace_path=arguments.trace,
        context_path=arguments.context,
        command_manifest_path=arguments.command_manifest,
        multi_agent_evidence_path=arguments.multi_agent_evidence,
        swimlane_evidence_path=arguments.swimlane_evidence,
        project_root=arguments.project_root,
        frontend_evidence_path=arguments.frontend_evidence,
        stage=arguments.stage,
        allow_passwords=arguments.allow_passwords,
    )
    failed = any(item.severity == "error" for item in issues)
    if arguments.json:
        print(json.dumps({"valid": not failed, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            print(f"{item.severity.upper()} {item.code} {item.source} {item.message}")
        print(f"errors={sum(item.severity == 'error' for item in issues)} valid={str(not failed).lower()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
