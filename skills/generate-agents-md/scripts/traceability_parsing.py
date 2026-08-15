from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from traceability_common import GATE_COLUMNS, Issue, LINK_RE


def _parse_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^-\s+([^:]+):\s*(.+?)\s*$", line)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip().strip("`")
    return metadata


def _metadata_duplicates(text: str) -> list[tuple[str, int]]:
    seen: set[str] = set()
    duplicates: list[tuple[str, int]] = []
    for row, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^-\s+([^:]+):\s*(.+?)\s*$", line)
        if match:
            field = match.group(1).strip()
            if field in seen:
                duplicates.append((field, row))
            seen.add(field)
    return duplicates


def _findings_none_is_mixed(text: str) -> bool:
    match = re.search(r"^##\s+Open Findings\s*$([\s\S]*?)(?=^#{1,2}\s+|\Z)", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return False
    section = match.group(1)
    has_none = bool(re.search(r"^\s*-\s+None\s*$", section, re.MULTILINE | re.IGNORECASE))
    has_other_content = any(
        line.strip() and not re.match(r"^\s*-\s+None\s*$", line, re.IGNORECASE)
        for line in section.splitlines()
    )
    return has_none and has_other_content


def _parse_table(
    text: str,
    heading: str,
    expected_columns: tuple[str, ...],
    *,
    allow_none: bool = False,
) -> tuple[list[dict[str, str]] | None, list[int], list[Issue]]:
    lines, start = text.splitlines(), None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(heading)}\s*$", line, re.IGNORECASE):
            start = index + 1
            break
    if start is None:
        return None, [], []
    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^#{1,2}\s+", lines[index]):
            end = index
            break
    section = lines[start:end]
    if allow_none and any(re.match(r"^-\s+None\s*$", line, re.IGNORECASE) for line in section):
        return [], [], []
    header_index = next((index for index, line in enumerate(section) if line.strip().startswith("|")), None)
    if header_index is None or header_index + 1 >= len(section):
        return None, [], []
    headers = _split_table_row(section[header_index])
    if tuple(headers) != expected_columns:
        return None, [], []
    return _parse_table_rows(section, header_index, headers, start, heading)


def _parse_table_rows(
    section: list[str], header_index: int, headers: list[str], start: int, heading: str,
) -> tuple[list[dict[str, str]], list[int], list[Issue]]:
    rows: list[dict[str, str]] = []
    row_numbers: list[int] = []
    parse_issues: list[Issue] = []
    separator = _split_table_row(section[header_index + 1])
    if len(separator) != len(headers) or any(
        not re.fullmatch(r":?-{3,}:?", value) for value in separator
    ):
        parse_issues.append(Issue(
            "error", "invalid-table-separator", f"{heading} 表格分隔行无效",
            start + header_index + 2,
        ))
    for relative_index, line in enumerate(section[header_index + 2 :], start=header_index + 2):
        if not line.strip().startswith("|"):
            if line.strip():
                remaining = section[relative_index + 1:]
                if not rows or any(item.strip().startswith("|") for item in remaining):
                    parse_issues.append(Issue(
                        "error", "unexpected-table-content",
                        f"{heading} 表格数据区包含非表格内容或重复表格",
                        start + relative_index + 1,
                    ))
                break
            continue
        values = _split_table_row(line)
        if len(values) != len(headers):
            parse_issues.append(
                Issue(
                    "error",
                    "malformed-table-row",
                    f"{heading} 表格行列数错误：期望 {len(headers)}，实际 {len(values)}",
                    start + relative_index + 1,
                )
            )
            continue
        rows.append(dict(zip(headers, values)))
        row_numbers.append(start + relative_index + 1)
    return rows, row_numbers, parse_issues


def _split_table_row(line: str) -> list[str]:
    return [value.strip() for value in line.strip().strip("|").split("|")]


def _is_na(value: str) -> bool:
    return bool(re.fullmatch(r"N/A:\s*\S.+", value, re.IGNORECASE))


def _resolve_project_path(
    raw_path: str,
    root: Path,
    issues: list[Issue],
    code: str,
    row: int | None = None,
) -> Path | None:
    value = raw_path.strip().strip("`")
    if not value:
        issues.append(Issue("error", f"missing-{code}", "缺少项目内路径", row))
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径必须位于项目内：{value}", row))
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径越出项目根：{value}", row))
        return None
    if not resolved.exists():
        issues.append(Issue("error", f"missing-{code}", f"引用路径不存在：{value}", row))
    elif not resolved.is_file():
        issues.append(Issue("error", f"nonfile-{code}", f"引用路径必须是普通文件：{value}", row))
        return None
    return resolved


def _validate_iso8601(value: str, issues: list[Issue]) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.append(Issue("error", "invalid-verified-at", "Verified at 必须是 ISO-8601 时间"))
        return
    if parsed.tzinfo is None:
        issues.append(Issue("error", "missing-verified-at-timezone", "Verified at 必须包含时区"))


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    unique: dict[tuple[str, str, str, int | None], Issue] = {}
    for issue in issues:
        unique[(issue.severity, issue.code, issue.message, issue.row)] = issue
    return list(unique.values())
