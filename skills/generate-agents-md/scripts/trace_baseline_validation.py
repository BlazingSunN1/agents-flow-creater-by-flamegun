from __future__ import annotations

import hashlib
import re
from pathlib import Path

from traceability_common import Issue
from traceability_parsing import _resolve_project_path, _validate_iso8601


def _validate_baseline(metadata: dict[str, str], root: Path, issues: list[Issue]) -> str:
    baseline_path = _resolve_project_path(metadata.get("Baseline artifact", ""), root, issues, "baseline-artifact")
    expected_sha = metadata.get("Baseline SHA-256", "").casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        issues.append(Issue("error", "invalid-baseline-sha256", "Baseline SHA-256 必须是 64 位十六进制"))
    elif baseline_path and baseline_path.is_file():
        actual_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            issues.append(Issue("error", "stale-baseline-hash", "需求基线文件已变化，SHA-256 与追踪矩阵不一致"))
    _validate_iso8601(metadata.get("Verified at", ""), issues)
    return expected_sha
