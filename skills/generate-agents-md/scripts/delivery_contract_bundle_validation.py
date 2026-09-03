from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agents_policy_common import DEVELOPMENT_PLAN_HEADING_RE, extract_heading_section
from delivery_record_validation import _declared_path
from implementation_agent_validation import HostAttestationVerifier
from validate_context_manifest import _parse_metadata as parse_context_metadata
from validate_context_manifest import _split_paths
from validate_delivery_contract import validate_delivery_contract
from validate_requirement_questions import (
    _test_only_validate_requirement_questions,
    validate_requirement_questions,
)
from validate_traceability import _parse_metadata as parse_trace_metadata


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    source: str


def validate_contract_bundle_binding(
    *, delivery_contract_path: Path | None, agents_path: Path,
    trace_path: Path, context_path: Path, command_manifest_path: Path,
    requirement_questions_path: Path | None, project_root: Path, stage: str,
) -> list[Finding]:
    if delivery_contract_path is None:
        return [Finding(
            "error", "missing-delivery-contract",
            "聚合交付必须传入唯一 delivery contract", "delivery-bundle",
        )]
    issues = [
        Finding(item.severity, f"contract-{item.code}", item.message, str(delivery_contract_path))
        for item in validate_delivery_contract(delivery_contract_path, project_root=project_root)
    ]
    loaded = _read_binding_inputs(
        delivery_contract_path, agents_path, trace_path, context_path,
        command_manifest_path, issues,
    )
    if loaded is None:
        return issues
    data, agents_text, trace, context, commands = loaded
    if not isinstance(data, dict):
        return issues
    issues.extend(_artifact_path_issues(
        data, agents_text, trace_path, command_manifest_path,
        requirement_questions_path, project_root, delivery_contract_path,
    ))
    issues.extend(_identity_issues(data, trace, stage, delivery_contract_path))
    issues.extend(_change_issues(data, trace, context, commands, delivery_contract_path))
    return issues


def _read_binding_inputs(
    contract_path: Path, agents_path: Path, trace_path: Path,
    context_path: Path, command_manifest_path: Path, issues: list[Finding],
) -> tuple[object, str, dict[str, str], dict[str, str], object] | None:
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
        agents_text = agents_path.read_text(encoding="utf-8")
        trace = parse_trace_metadata(trace_path.read_text(encoding="utf-8"))
        context, _ = parse_context_metadata(context_path.read_text(encoding="utf-8"))
        commands = json.loads(command_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(Finding(
            "error", "contract-bundle-binding-unreadable", str(error), str(contract_path),
        ))
        return None
    return data, agents_text, trace, context, commands


def _artifact_path_issues(
    data: dict[str, object], agents_text: str, trace_path: Path,
    command_manifest_path: Path, questions_path: Path | None,
    root: Path, contract_path: Path,
) -> list[Finding]:
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    section = extract_heading_section(agents_text, DEVELOPMENT_PLAN_HEADING_RE) or ""
    plan = _declared_path(section, r"development plan|开发计划")
    progress = _declared_path(
        section, r"completion (?:index|progress)|progress (?:record|index)|完成进度|进度记录",
    )
    expected = {
        "traceability": trace_path,
        "questions": questions_path,
        "development_plan": root / plan if plan else None,
        "progress": root / progress if progress else None,
        "command_manifest": command_manifest_path,
    }
    issues: list[Finding] = []
    for name, expected_path in expected.items():
        ref = artifacts.get(name)
        raw = ref.get("path") if isinstance(ref, dict) else None
        actual = root / raw if isinstance(raw, str) and not Path(raw).is_absolute() else None
        if expected_path is None or actual is None or actual.resolve() != expected_path.resolve():
            issues.append(Finding(
                "error", "contract-artifact-path-mismatch",
                f"delivery contract 的 {name} 未绑定聚合交付实际工件", str(contract_path),
            ))
    return issues


def _identity_issues(
    data: dict[str, object], trace: dict[str, str], stage: str, contract_path: Path,
) -> list[Finding]:
    issues: list[Finding] = []
    if data.get("stage") != stage:
        issues.append(Finding(
            "error", "contract-stage-mismatch", "delivery contract 阶段与聚合阶段不一致",
            str(contract_path),
        ))
    baseline = data.get("baseline")
    if isinstance(baseline, dict) and (
        baseline.get("version") != trace.get("Baseline version")
        or baseline.get("sha256") != trace.get("Baseline SHA-256")
    ):
        issues.append(Finding(
            "error", "contract-baseline-mismatch", "delivery contract 与追踪基线不一致",
            str(contract_path),
        ))
    identity = data.get("identity")
    expected = {
        "code_version": trace.get("Code version"),
        "build_id": trace.get("Build ID"),
        "environment_id": trace.get("Acceptance environment"),
    }
    if isinstance(identity, dict) and any(identity.get(key) != value for key, value in expected.items()):
        issues.append(Finding(
            "error", "contract-candidate-identity-mismatch",
            "delivery contract 候选身份与当前追踪记录不一致", str(contract_path),
        ))
    return issues


def _change_issues(
    data: dict[str, object], trace: dict[str, str], context: dict[str, str],
    commands: object, contract_path: Path,
) -> list[Finding]:
    change = data.get("change")
    if not isinstance(change, dict):
        return []
    expected = {
        "requirement_ids": [item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()],
        "modules": [item.strip() for item in context.get("Modules", "").split(",") if item.strip()],
        "changed_files": _split_paths(context.get("Changed files", "")),
        "configuration_files": _split_paths(context.get("Configuration files", "")),
        "input_files": _split_paths(context.get("Input files", "")),
        "direct_dependency_boundaries": context.get("Direct dependency boundaries"),
        "risk_level": trace.get("Risk level"),
        "risk_reason": trace.get("Risk reason"),
        "surfaces": [item.strip().casefold() for item in trace.get("Change surfaces", "").split(",") if item.strip()],
        "frontend_applicable": isinstance(commands, dict) and commands.get("frontend_applicable") is True,
    }
    if any(change.get(key) != value for key, value in expected.items()):
        return [Finding(
            "error", "contract-change-identity-mismatch",
            "delivery contract 变更集与工作集、追踪矩阵或命令清单不一致", str(contract_path),
        )]
    return []


def validate_requirement_questions_bundle(
    path: Path | None, declared_sha: str | None,
    baseline_version: str | None, baseline_sha: str | None,
    trace_path: Path, root: Path, verifier: HostAttestationVerifier | None,
) -> list[Finding]:
    source = str(path) if path is not None else "delivery-bundle"
    if path is None or not isinstance(declared_sha, str) or re.fullmatch(r"[0-9a-f]{64}", declared_sha) is None:
        return [Finding("error", "questions-artifact-invalid", "交付包必须绑定疑问清单 locator 和 SHA-256", source)]
    try:
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != declared_sha:
            raise ValueError("missing, aliased, or stale")
        questions = json.loads(path.read_text(encoding="utf-8"))
        trace = parse_trace_metadata(trace_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [Finding("error", "questions-artifact-invalid", f"疑问清单不可读或哈希漂移：{error}", source)]
    expected = (baseline_version, baseline_sha)
    actual = (questions.get("baseline_version"), questions.get("baseline_sha256")) if isinstance(questions, dict) else (None, None)
    traced = (trace.get("Baseline version"), trace.get("Baseline SHA-256"))
    issues = [] if expected == actual == traced else [Finding(
        "error", "questions-baseline-mismatch",
        "疑问清单、交付声明和需求追踪必须绑定同一当前 baseline version/SHA-256", source,
    )]
    found = (
        validate_requirement_questions(path, project_root=root)
        if verifier is None else _test_only_validate_requirement_questions(
            path, project_root=root, _test_only_host_attestation_verifier=verifier,
        )
    )
    issues.extend(Finding(item.severity, f"questions-{item.code}", item.message, source) for item in found)
    return issues
