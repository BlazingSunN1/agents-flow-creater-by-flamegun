from __future__ import annotations

import re
from pathlib import Path

from agents_policy_common import normative_markdown_view


STABLE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
DEVELOPMENT_PLAN_PATH = "development_plan"
PROGRESS_RECORD_PATH = "progress_record"
AUTOMATED_REVIEW_EVIDENCE_PATH = "automated_review_evidence"
MODULE_EXECUTION_LOG_TEMPLATE = "module_execution_log_template"
PATH_FIELD_PATTERNS = {
    DEVELOPMENT_PLAN_PATH: re.compile(
        r"^\s*-\s*(?:Development plan path|开发计划路径)\s*:\s*`([^`\r\n]+)`\s*$",
        re.IGNORECASE,
    ),
    PROGRESS_RECORD_PATH: re.compile(
        r"^\s*-\s*(?:Completion progress path|完成进度路径)\s*:\s*`([^`\r\n]+)`\s*$",
        re.IGNORECASE,
    ),
    AUTOMATED_REVIEW_EVIDENCE_PATH: re.compile(
        r"^\s*-\s*(?:Automated review evidence path|自动审查证据路径)\s*:\s*`([^`\r\n]+)`\s*$",
        re.IGNORECASE,
    ),
    MODULE_EXECUTION_LOG_TEMPLATE: re.compile(
        r"^\s*-\s*(?:Immutable module run template path|不可变模块运行模板路径)\s*:\s*`([^`\r\n]+)`\s*$",
        re.IGNORECASE,
    ),
}


def modules(context: dict[str, str]) -> list[str]:
    values = sorted({item.strip() for item in context.get("Modules", "").split(",") if item.strip()})
    return values if values and all(STABLE_ID_RE.fullmatch(value) for value in values) else []


def declared_paths(section: str, field: str) -> list[str]:
    pattern = PATH_FIELD_PATTERNS.get(field)
    if pattern is None:
        return []
    normative = normative_markdown_view(section)
    return [
        match.group(1).strip()
        for line in normative.splitlines()
        if (match := pattern.fullmatch(line))
    ]


def declared_path(section: str, field: str) -> str | None:
    values = declared_paths(section, field)
    return values[0] if len(values) == 1 else None


def normalize_template(template: str, module: str, run_id: str) -> str:
    return Path(template.replace("<module>", module).replace("<run_id>", run_id)).as_posix()


def context_record_path(raw_path: str | None, context: dict[str, str]) -> str | None:
    if raw_path is None:
        return None
    has_module = "<module>" in raw_path
    has_run_id = "<run_id>" in raw_path
    if not has_module and not has_run_id:
        return raw_path
    if not has_module or not has_run_id:
        return None
    context_modules = modules(context)
    run_id = context.get("Run ID", "")
    if len(context_modules) != 1 or not STABLE_ID_RE.fullmatch(run_id):
        return None
    return normalize_template(raw_path, context_modules[0], run_id)
