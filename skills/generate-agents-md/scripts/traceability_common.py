from __future__ import annotations

import re
from dataclasses import dataclass


PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
LINK_RE = re.compile(r"\[([A-Z][A-Z0-9_-]*-\d+)\]\(([^)]+)\)")
TRACE_PREFIXES = {
    "Requirement": "REQ-",
    "Flow": "FLOW-",
    "Feature": "FEAT-",
    "UI/UX": "UI-",
    "Unit tests": "UT-",
    "Acceptance cases": "AT-",
    "Code module": "MOD-",
    "Black-box result": "BB-",
}
TRACE_COLUMNS = (*TRACE_PREFIXES, "Status")
GATE_COLUMNS = (
    "Gate", "Applicability", "Agent run ID", "Input baseline version",
    "Input baseline SHA-256", "Code version", "Build ID", "Input manifest",
    "Output evidence", "Verdict",
)
FINDING_COLUMNS = ("Finding", "Class", "Status", "Route", "Evidence")
REQUIRED_METADATA = (
    "Baseline artifact", "Baseline version", "Baseline SHA-256",
    "Authority matrix locator", "Authority matrix SHA-256", "Code version",
    "Build ID", "Acceptance environment", "Verified at", "Risk level",
    "Risk reason", "Change surfaces", "Implementation run ID",
)
RISK_ORDER = {"small": 0, "standard": 1, "high-risk": 2}
STANDARD_SURFACES = {
    "user-visible", "ui", "api", "behavior-change", "mobile", "mobile-web",
    "native-mobile", "touch", "responsive",
}
HIGH_RISK_SURFACES = {
    "auth", "security", "privacy", "migration", "persistence", "async",
    "cross-module", "data-schema", "public-api",
}
ALLOWED_SURFACES = {
    "internal", *STANDARD_SURFACES, *HIGH_RISK_SURFACES,
}
REQUIRED_GATES = {"UI_UX", "ACCEPTANCE_CASES", "BLACK_BOX"}
INDEPENDENT_ROLES = {
    "UI_UX", "ACCEPTANCE_CASES", "CHANGE_REVIEW", "BLACK_BOX",
    "REQUIREMENT_REVIEW", "SPECIALIST_REVIEW",
}
VERDICTS = {"pending", "pass", "fail", "blocked", "not_applicable"}
STATUSES = {"pending", "in_progress", "blocked", "completed"}
FINDING_ROUTES = {
    "implementation_defect": "implementation",
    "requirement_ambiguity": "requirement-baseline",
    "acceptance_case_defect": "acceptance-cases",
    "environment_blocker": "blocked",
    "approved_requirement_change": "new-baseline",
}


def required_independent_roles(risk: str, surfaces: set[str], stage: str) -> set[str]:
    """Return the single canonical independent-role plan for a delivery stage."""
    if stage not in {"closure_candidate", "completion"}:
        return set()
    if risk == "standard":
        return {"BLACK_BOX"}
    if risk != "high-risk":
        return set()
    roles = {"ACCEPTANCE_CASES", "CHANGE_REVIEW", "REQUIREMENT_REVIEW", "SPECIALIST_REVIEW"}
    if stage == "completion":
        roles.add("BLACK_BOX")
    if "ui" in surfaces:
        roles.add("UI_UX")
    return roles


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    row: int | None = None
