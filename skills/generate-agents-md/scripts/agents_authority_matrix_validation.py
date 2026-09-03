from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from agents_policy_common import Issue, extract_heading_section


AUTHORITY_MATRIX_HEADING_RE = re.compile(
    r"(?:机器强制权限矩阵|machine-enforced authority matrix)", re.IGNORECASE
)
ACTORS = (
    "dispatcher",
    "module-maintainer",
    "independent-reviewer",
    "system-aggregation",
    "implementation",
    "system-governance-bootstrap",
)
ACTIONS = (
    "route", "write", "design", "implement", "review", "black-box",
    "accept", "release", "close", "aggregate", "issue_independent_verdict",
    "write_module_artifacts", "record_completion_after_verified_gates",
    "write_system_manifest", "orchestrate_read_validate",
    "bootstrap_system_governance",
)
ACTION_OBJECTS = {
    "route": "module-delivery",
    "write": "project-record",
    "design": "module-delivery",
    "implement": "module-delivery",
    "review": "module-delivery",
    "black-box": "module-delivery",
    "accept": "module-delivery",
    "release": "module-delivery",
    "close": "module-delivery",
    "aggregate": "system-delivery",
    "issue_independent_verdict": "gate-verdict",
    "write_module_artifacts": "module-artifacts",
    "record_completion_after_verified_gates": "module-delivery",
    "write_system_manifest": "system-manifest",
    "orchestrate_read_validate": "system-delivery",
    "bootstrap_system_governance": "system-governance",
}
ALLOWED_POLICIES = {
    "dispatcher": {"route": "allow", "orchestrate_read_validate": "allow"},
    "module-maintainer": {
        "write": "allow", "design": "allow", "implement": "allow",
        "write_module_artifacts": "allow",
        "record_completion_after_verified_gates": "independent-only",
    },
    "independent-reviewer": {
        "review": "allow", "black-box": "allow", "accept": "allow",
        "issue_independent_verdict": "allow",
    },
    "system-aggregation": {"aggregate": "allow", "write_system_manifest": "allow"},
    "implementation": {
        "write": "allow", "design": "allow", "implement": "allow",
        "write_module_artifacts": "allow",
    },
    "system-governance-bootstrap": {
        "bootstrap_system_governance": "external-explicit-only",
    },
}
GATE_PROOF_CONTRACT = {
    "agent_identity": "distinct-from-writer-and-other-gates",
    "run_identity": "distinct-current-coordination-run",
    "status": "completed",
    "verdict": "pass",
    "receipt_path": "required-project-relative-path",
    "receipt_sha256": "required-sha256",
    "candidate_sha256": "required-sha256",
    "code_version": "required",
    "build_id": "required",
    "host_verifier": "optional-strict-security",
}


def _expected_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for actor in ACTORS:
        for action in ACTIONS:
            bootstrap_allow = (
                actor == "system-governance-bootstrap"
                and action == "bootstrap_system_governance"
            )
            rows.append({
                "actor": actor,
                "action": action,
                "object": ACTION_OBJECTS[action],
                "policy": ALLOWED_POLICIES[actor].get(action, "deny"),
                "scope": (
                    "exact-external-authorized-targets" if bootstrap_allow else "repository"
                ),
                "module_binding": (
                    "pending-stable-module-registration"
                    if bootstrap_allow else "registered-module-key"
                ),
                "run_binding": (
                    "local-coordination-or-host-attested-or-explicit-local-controlled-bootstrap-receipt"
                    if bootstrap_allow else "local-coordination-or-host-attested-receipt"
                ),
            })
    return rows


EXPECTED_AUTHORITY_MATRIX: dict[str, Any] = {
    "schema_version": 1,
    "scope_binding": "effective-root-agents",
    "module_binding": "registered-module-key-and-owned-paths",
    "run_binding": "local-coordination-or-host-attested-receipts",
    "independent_gate_proof": GATE_PROOF_CONTRACT,
    "rows": _expected_rows(),
}

# The project-facing declaration keeps the same expanded v1 capability semantics while
# avoiding 96 repetitive rows in every root AGENTS.md. Validators expand this closed
# declaration before hashing; existing expanded v1 documents remain readable.
EXPECTED_AUTHORITY_DECLARATION: dict[str, Any] = {
    "schema_version": 2,
    "contract": "expanded-authority-matrix-v1",
    "scope_binding": EXPECTED_AUTHORITY_MATRIX["scope_binding"],
    "module_binding": EXPECTED_AUTHORITY_MATRIX["module_binding"],
    "run_binding": EXPECTED_AUTHORITY_MATRIX["run_binding"],
    "independent_gate_proof": GATE_PROOF_CONTRACT,
    "default": {
        "policy": "deny",
        "scope": "repository",
        "module_binding": "registered-module-key",
        "run_binding": "local-coordination-or-host-attested-receipt",
    },
    "actions": ACTION_OBJECTS,
    "policy_overrides": ALLOWED_POLICIES,
    "binding_overrides": {
        "system-governance-bootstrap.bootstrap_system_governance": {
            "scope": "exact-external-authorized-targets",
            "module_binding": "pending-stable-module-registration",
            "run_binding": (
                "local-coordination-or-host-attested-or-explicit-local-controlled-"
                "bootstrap-receipt"
            ),
        },
    },
}


def canonical_matrix_sha256(value: dict[str, Any] = EXPECTED_AUTHORITY_MATRIX) -> str:
    normalized = EXPECTED_AUTHORITY_MATRIX if value == EXPECTED_AUTHORITY_DECLARATION else value
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


AUTHORITY_MATRIX_SHA256 = canonical_matrix_sha256()
TOP_LEVEL_FIELDS = tuple(EXPECTED_AUTHORITY_MATRIX)
ROW_FIELDS = tuple(EXPECTED_AUTHORITY_MATRIX["rows"][0])
GATE_PROOF_FIELDS = tuple(GATE_PROOF_CONTRACT)


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = item
    return value


def _parse_matrix(section: str) -> tuple[dict[str, Any] | None, str | None]:
    blocks = re.findall(r"```json\s*\n([\s\S]*?)\n```", section)
    if len(blocks) != 1:
        return None, "权限矩阵章节必须且只能包含一个 JSON 块"
    try:
        value = json.loads(blocks[0], object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, _DuplicateKey) as error:
        return None, f"权限矩阵不是唯一键严格 JSON：{error}"
    if not isinstance(value, dict):
        return None, "权限矩阵根值必须是对象"
    return value, None


def _matrix_hash_declared(text: str) -> str | None:
    match = re.search(r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def _row_projection(row: Any) -> tuple[Any, ...] | None:
    if not isinstance(row, dict) or tuple(row) != ROW_FIELDS:
        return None
    return (
        row.get("actor"),
        row.get("action"),
        row.get("object"),
        row.get("policy"),
        row.get("scope"),
        row.get("module_binding"),
        row.get("run_binding"),
    )


def _rows_are_canonical(rows: Any) -> bool:
    if not isinstance(rows, list):
        return False
    actual = tuple(_row_projection(row) for row in rows)
    expected = tuple(_row_projection(row) for row in EXPECTED_AUTHORITY_MATRIX["rows"])
    return actual == expected


def _proof_identity_is_canonical(proof: dict[str, Any]) -> bool:
    return (
        proof.get("agent_identity") == GATE_PROOF_CONTRACT["agent_identity"]
        and proof.get("run_identity") == GATE_PROOF_CONTRACT["run_identity"]
    )


def _proof_outcome_is_canonical(proof: dict[str, Any]) -> bool:
    return (
        proof.get("status") == "completed"
        and proof.get("verdict") == "pass"
    )


def _proof_receipt_is_canonical(proof: dict[str, Any]) -> bool:
    fields = ("receipt_path", "receipt_sha256", "candidate_sha256", "code_version", "build_id")
    return all(proof.get(field) == GATE_PROOF_CONTRACT[field] for field in fields)


def _proof_is_canonical(proof: Any) -> bool:
    return (
        isinstance(proof, dict)
        and tuple(proof) == GATE_PROOF_FIELDS
        and _proof_identity_is_canonical(proof)
        and _proof_outcome_is_canonical(proof)
        and _proof_receipt_is_canonical(proof)
        and proof.get("host_verifier") == GATE_PROOF_CONTRACT["host_verifier"]
    )


def _matrix_is_canonical(value: dict[str, Any]) -> bool:
    expanded_is_canonical = (
        tuple(value) == TOP_LEVEL_FIELDS
        and type(value.get("schema_version")) is int
        and value.get("schema_version") == 1
        and value.get("scope_binding") == "effective-root-agents"
        and value.get("module_binding") == "registered-module-key-and-owned-paths"
        and value.get("run_binding") == EXPECTED_AUTHORITY_MATRIX["run_binding"]
        and _proof_is_canonical(value.get("independent_gate_proof"))
        and _rows_are_canonical(value.get("rows"))
    )
    return expanded_is_canonical or value == EXPECTED_AUTHORITY_DECLARATION


PROSE_ACTOR_RE = re.compile(
    r"(?:module\s+(?:maintenance\s+Agent|maintainer)|implementation\s+Agent|implementer|"
    r"模块维护 Agent|维护 Agent|实现 Agent|维护者|实现者|Dispatcher)", re.IGNORECASE
)
PROSE_OBJECT_RE = re.compile(
    r"(?:its\s+own|their\s+own|own|module|自己的|自身的|模块).{0,24}(?:delivery|交付)", re.IGNORECASE
)
PROSE_AUTHORITY_RE = re.compile(
    r"(?:\b(?:may|can|has|holds|gets|receives)\b|可以|能够|拥有|获得).{0,32}"
    r"(?:green[- ]light|go[- ]ahead|放行|拍板|最终决定权)", re.IGNORECASE
)


def _prose_conflicts(text: str) -> bool:
    for segment in re.split(r"[\r\n。；;]+", text):
        if (PROSE_ACTOR_RE.search(segment) and PROSE_OBJECT_RE.search(segment)
                and PROSE_AUTHORITY_RE.search(segment)):
            return True
    return False


def validate_authority_matrix(text: str) -> list[Issue]:
    section = extract_heading_section(text, AUTHORITY_MATRIX_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-authority-matrix", "缺少机器强制权限矩阵")]
    value, parse_error = _parse_matrix(section)
    if parse_error:
        return [Issue("error", "invalid-authority-matrix", parse_error)]
    assert value is not None
    issues: list[Issue] = []
    if not _matrix_is_canonical(value):
        issues.append(Issue(
            "error", "invalid-authority-matrix",
            "权限矩阵必须逐字段匹配固定 actor/action/object/policy 与 gate-proof 合约",
        ))
    if _matrix_hash_declared(text) != canonical_matrix_sha256(value):
        issues.append(Issue(
            "error", "authority-matrix-hash-mismatch",
            "Machine Policy 中的权限矩阵 SHA-256 与规范 JSON 不一致",
        ))
    if _prose_conflicts(text):
        issues.append(Issue(
            "error", "contradictory-authority-matrix-policy",
            "自然语言规则不得向维护者、实现者或 Dispatcher 反向授予固定 deny 权限",
        ))
    return issues
