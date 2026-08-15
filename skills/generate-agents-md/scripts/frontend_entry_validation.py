from __future__ import annotations

import json
from pathlib import Path

from browser_page_validation import page_identity_issues
from strict_json import loads as strict_json_loads


def frontend_entry(path: Path) -> tuple[str, str, str] | None:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("frontend_applicable") is not True:
        return None
    values = tuple(data.get(field) for field in (
        "frontend_preview_url", "frontend_preview_root", "frontend_entry_artifact",
    ))
    if any(type(value) is not str or not value.strip() for value in values):
        return None
    return values


def frontend_page_issues(
    evidence: dict[str, object], transcript: dict[str, object], root: Path,
    label: str, expected: tuple[str, str, str] | None,
) -> list[tuple[str, str]]:
    return page_identity_issues(
        evidence, transcript, root, code=f"{label}-page-artifact-mismatch",
        expected_url=expected[0] if expected else None,
        expected_preview_root=expected[1] if expected else None,
        expected_path=expected[2] if expected else None,
    )
