from __future__ import annotations

from traceability_common import Issue


def requirement_identity_issues(
    column: str, links: list[tuple[str, str]], row_number: int,
    requirement_rows: dict[str, int],
) -> list[Issue]:
    if column != "Requirement":
        return []
    identifiers = [identifier for identifier, _ in links]
    issues: list[Issue] = []
    if len(identifiers) != len(set(identifiers)):
        issues.append(Issue("error", "duplicate-requirement-link", "Requirement 单元格编号必须唯一", row_number))
    for identifier in identifiers:
        previous = requirement_rows.get(identifier)
        if previous is not None and previous != row_number:
            issues.append(Issue(
                "error", "duplicate-requirement-row",
                f"需求 {identifier} 已在第 {previous} 行声明，不能拆成多条追踪链", row_number,
            ))
        requirement_rows[identifier] = row_number
    return issues
