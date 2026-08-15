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
    "Baseline artifact", "Baseline version", "Baseline SHA-256", "Code version",
    "Build ID", "Acceptance environment", "Verified at", "Risk level",
    "Risk reason", "Change surfaces", "Implementation run ID",
)
RISK_ORDER = {"small": 0, "standard": 1, "high-risk": 2}
STANDARD_SURFACES = {"user-visible", "ui", "api", "behavior-change"}
CONDITIONAL_FRONTEND_SURFACES = {"mobile", "touch", "responsive"}
HIGH_RISK_SURFACES = {
    "auth", "security", "privacy", "migration", "persistence", "async",
    "cross-module", "data-schema", "public-api",
}
ALLOWED_SURFACES = {
    "internal", *STANDARD_SURFACES, *CONDITIONAL_FRONTEND_SURFACES,
    *HIGH_RISK_SURFACES,
}
REQUIRED_GATES = {"UI_UX", "ACCEPTANCE_CASES", "BLACK_BOX"}
VERDICTS = {"pending", "pass", "fail", "blocked", "not_applicable"}
STATUSES = {"pending", "in_progress", "blocked", "completed"}
FINDING_ROUTES = {
    "implementation_defect": "implementation",
    "requirement_ambiguity": "requirement-baseline",
    "acceptance_case_defect": "acceptance-cases",
    "environment_blocker": "blocked",
    "approved_requirement_change": "new-baseline",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    row: int | None = None
