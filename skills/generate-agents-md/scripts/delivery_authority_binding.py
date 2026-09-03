from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from agents_authority_matrix_validation import EXPECTED_AUTHORITY_MATRIX, validate_authority_matrix
from agents_policy_common import REQUIRED_MACHINE_POLICY
from strict_json import loads as strict_json_loads


AUTHORITY_LOCATOR = REQUIRED_MACHINE_POLICY["authority_matrix_path"]
AUTHORITY_SHA256 = REQUIRED_MACHINE_POLICY["authority_matrix_sha256"]
ROW_FIELDS = {"role", "action", "policy"}

MODULE_ROWS = (
    ("module-maintainer", "write_module_artifacts", "allow"),
    ("module-maintainer", "record_completion_after_verified_gates", "independent-only"),
    ("independent-reviewer", "issue_independent_verdict", "allow"),
)
SYSTEM_ROWS = (
    ("system-aggregation", "write_system_manifest", "allow"),
    ("dispatcher", "orchestrate_read_validate", "allow"),
)


def expected_authority_binding(scope: Literal["module", "system"]) -> dict[str, object]:
    rows = MODULE_ROWS if scope == "module" else SYSTEM_ROWS
    return {
        "locator": AUTHORITY_LOCATOR,
        "sha256": AUTHORITY_SHA256,
        "required_rows": [
            {"role": role, "action": action, "policy": policy}
            for role, action, policy in rows
        ],
    }


def authority_binding_valid(value: object, scope: Literal["module", "system"]) -> bool:
    if value != expected_authority_binding(scope):
        return False
    assert isinstance(value, dict)
    rows = value["required_rows"]
    if not isinstance(rows, list):
        return False
    matrix_rows = EXPECTED_AUTHORITY_MATRIX["rows"]
    return all(
        isinstance(row, dict)
        and set(row) == ROW_FIELDS
        and any(
            matrix["actor"] == row["role"]
            and matrix["action"] == row["action"]
            and matrix["policy"] == row["policy"]
            for matrix in matrix_rows
        )
        for row in rows
    )


def agents_declares_authority_binding(text: str, binding: object) -> bool:
    if not isinstance(binding, dict):
        return False
    locator = re.search(r"^authority_matrix_path:\s*(\S+)\s*$", text, re.MULTILINE)
    sha256 = re.search(r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$", text, re.MULTILINE)
    return bool(
        locator and sha256
        and locator.group(1) == binding.get("locator") == AUTHORITY_LOCATOR
        and sha256.group(1) == binding.get("sha256") == AUTHORITY_SHA256
        and not validate_authority_matrix(text)
    )


def receipt_repeats_authority_binding(path: Path, binding: object) -> bool:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    return isinstance(value, dict) and value.get("authority_binding") == binding
