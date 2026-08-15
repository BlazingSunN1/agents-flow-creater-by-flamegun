from __future__ import annotations

import re


def black_box_not_started(row: dict[str, str]) -> bool:
    return (
        not row["Agent run ID"].strip()
        and _is_na(row["Input manifest"])
        and _is_na(row["Output evidence"])
        and row["Verdict"].strip() == "pending"
    )


def pending_black_box_issues(
    row: dict[str, str], metadata: dict[str, str], expected_sha: str,
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if row["Input baseline version"].strip() != metadata.get("Baseline version", "").strip():
        issues.append(("stale-gate-baseline-version", "BLACK_BOX 的需求基线版本不一致"))
    if row["Input baseline SHA-256"].strip().casefold() != expected_sha:
        issues.append(("stale-gate-baseline-hash", "BLACK_BOX 的需求基线哈希不一致"))
    for column, field, code, message in (
        ("Code version", "Code version", "stale-black-box-code-version", "黑盒验收的 Code version 已过期"),
        ("Build ID", "Build ID", "stale-black-box-build", "黑盒验收的 Build ID 已过期"),
    ):
        if row[column].strip() != metadata.get(field, "").strip():
            issues.append((code, message))
    return issues


def _is_na(value: str) -> bool:
    return bool(re.fullmatch(r"N/A:\s*\S.+", value.strip(), re.IGNORECASE))
