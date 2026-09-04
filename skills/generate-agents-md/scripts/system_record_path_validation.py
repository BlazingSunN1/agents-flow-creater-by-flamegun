from __future__ import annotations

from pathlib import Path

from agents_policy_common import (
    AUTOMATED_REVIEW_HEADING_RE,
    DEVELOPMENT_PLAN_HEADING_RE,
    extract_heading_section,
)
from delivery_record_paths import declared_path
from delivery_record_paths import AUTOMATED_REVIEW_EVIDENCE_PATH, PROGRESS_RECORD_PATH


def invalid_cross_module_record_templates(agents_text: str) -> list[str]:
    plan_section = extract_heading_section(agents_text, DEVELOPMENT_PLAN_HEADING_RE) or ""
    review_section = extract_heading_section(agents_text, AUTOMATED_REVIEW_HEADING_RE) or ""
    paths = {
        "进度记录": declared_path(
            plan_section, PROGRESS_RECORD_PATH,
        ),
        "自动审查证据": declared_path(
            review_section, AUTOMATED_REVIEW_EVIDENCE_PATH,
        ),
    }
    return [label for label, path in paths.items() if not _isolated_record_template(path)]


def cross_module_record_template_error(agents_text: str) -> str | None:
    invalid = invalid_cross_module_record_templates(agents_text)
    return (f"跨模块聚合的{'、'.join(invalid)}路径必须各包含一次字面量 <module> 和 <run_id>，"
            "且二者分别位于不同且不含路径遍历的安全组件"
            if invalid else None)


def _isolated_record_template(path: str | None) -> bool:
    if path is None or "<module>" not in path or "<run_id>" not in path:
        return False
    candidate = Path(path)
    module_parts = [part for part in candidate.parts if "<module>" in part]
    run_parts = [part for part in candidate.parts if "<run_id>" in part]
    return (not candidate.is_absolute() and "\\" not in path
            and all(part not in {".", ".."} for part in candidate.parts)
            and path.count("<module>") == 1 and path.count("<run_id>") == 1
            and len(module_parts) == 1 and len(run_parts) == 1
            and module_parts[0] != run_parts[0])
