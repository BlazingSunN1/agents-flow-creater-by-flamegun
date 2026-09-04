from __future__ import annotations

import re
from dataclasses import dataclass


PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
URI_CREDENTIAL_DETAIL_RE = re.compile(
    r"(?P<uri>[A-Za-z][A-Za-z0-9+.-]*://"
    r"(?P<username>[^/\s:@]+):(?P<password>[^/\s@]+)@"
    r"(?P<authority>\[[^\]]+\]|[^/\s?#]+)(?P<suffix>/[^\s]*)?)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MODULAR_LOG_HEADING_RE = re.compile(
    r"(?:模块化执行日志|modular execution logs?)", re.IGNORECASE
)
DEVELOPMENT_PLAN_HEADING_RE = re.compile(
    r"(?:开发计划与完成进度|development plan and progress)", re.IGNORECASE
)
SWIMLANE_HEADING_RE = re.compile(
    r"(?:泳道图同步|swimlane diagram synchronization)", re.IGNORECASE
)
FRONTEND_VERIFICATION_HEADING_RE = re.compile(
    r"(?:前端交互验证|frontend interaction verification)", re.IGNORECASE
)
TRACEABILITY_HEADING_RE = re.compile(
    r"(?:需求追踪与交付门禁|requirement traceability and delivery gates?)",
    re.IGNORECASE,
)
AUTOMATED_REVIEW_HEADING_RE = re.compile(
    r"(?:自动代码审查|automated code review)", re.IGNORECASE
)
CONTEXT_BUDGET_HEADING_RE = re.compile(
    r"(?:上下文与 Token 预算|context and token budget)", re.IGNORECASE
)
MACHINE_POLICY_HEADING_RE = re.compile(
    r"(?:机器强制策略|machine-enforced policy)", re.IGNORECASE
)
PASSWORD_AUTHORIZATION_HEADING_RE = re.compile(
    r"(?:密码授权|password authorization)", re.IGNORECASE
)
DISPATCHER_OWNERSHIP_HEADING_RE = re.compile(
    r"(?:模块 Agent 所有权与调度|module agent ownership and dispatcher)",
    re.IGNORECASE,
)

REQUIRED_MACHINE_POLICY = {
    "schema_version": "1",
    "delivery_sequence": "result_candidate_then_affected_checks_then_freeze_then_mapped_hardening",
    "pre_result_gate_policy": "correctness_and_irreversible_only",
    "post_freeze_regression_replay": "required",
    "security_gate_policy": "mapped_surface_or_explicit_only",
    "automated_review": "required_at_module_closure_candidate_or_human_trigger",
    "context_manifest_validation": "required_before_expansion_or_reuse",
    "traceability_validation": "required_before_handoff_and_completion",
    "delivery_bundle_validation": "required_before_handoff_and_completion",
    "documentation_after_black_box": "required",
    "project_command_validation": "required_before_evidenced_gate_or_completion",
    "frontend_evidence_validation": "required_after_frontend_change",
    "multi_agent_evidence_validation": "required_before_handoff_and_completion",
    "swimlane_evidence_validation": "required_before_downstream_use_and_stage_completion",
    "atomic_record_updates": "required_for_shared_mutable_records",
    "single_writer_model": "implementation_agent_only",
    "authorization_mode": "delivery-first-local-coordination",
    "strict_security_mode": "explicit_or_mapped_high_risk_only",
    "requirement_questions": "non_blocking_p2",
    "major_module_closure": "required",
    "maintainer_self_acceptance": "forbidden",
    "affected_module_aggregation": "required_before_system_completion",
    "module_ownership_binding": "required_before_handoff_and_completion",
    "swimlane_sync": "required_for_verified_flow_change",
    "frontend_click_verification": "required_after_frontend_change",
    "local_browser_preview": "http_or_https_only",
    "mobile_verification": "conditional_on_approved_scope",
    "ui_ux_agent": "conditional_on_mapped_high_risk_ui",
    "sensitive_connection_values": "explicit_project_authorization_only",
    "authority_matrix_path": "AGENTS.md#machine-enforced-authority-matrix",
    "authority_matrix_sha256": "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643",
    "authority_matrix_validation": "required_before_delegation_and_completion",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    line: int | None = None


def extract_heading_section(text: str, title_pattern: re.Pattern[str]) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading_match = HEADING_RE.match(line)
        if not heading_match or not title_pattern.search(heading_match.group(2)):
            continue
        level = len(heading_match.group(1))
        end = len(lines)
        for candidate_index in range(index + 1, len(lines)):
            candidate = HEADING_RE.match(lines[candidate_index])
            if candidate and len(candidate.group(1)) <= level:
                end = candidate_index
                break
        return "\n".join(lines[index:end])
    return None


def section_has_line(section: str, required_patterns: tuple[str, ...]) -> bool:
    return any(
        all(re.search(pattern, line, re.IGNORECASE) for pattern in required_patterns)
        for line in section.splitlines()
    )


def section_has_contradiction(section: str, *, action: str) -> bool:
    negation = r"(?:\bdo\s+not\b|\bdon't\b|\bmust\s+not\b|\bnever\b|不得|不能|禁止|不要)"
    return any(
        re.search(rf"{negation}.{{0,80}}{action}", line, re.IGNORECASE)
        or re.search(rf"{action}.{{0,80}}{negation}", line, re.IGNORECASE)
        for line in section.splitlines()
    )


def document_path_pattern(mode: str) -> str:
    concrete = r"`[^`]*(?:/|\|\.md|\.html|\.puml|\.bpmn|\.mmd)[^`]*`"
    if mode == "public-template":
        return rf"(?:`\{{\{{[^`]+PATH\}}\}}`|{concrete})"
    return concrete
