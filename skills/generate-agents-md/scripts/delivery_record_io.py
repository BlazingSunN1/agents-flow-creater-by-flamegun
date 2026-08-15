from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    source: str


CLOSED_VALUES = {
    "findings": {"none", "closed", "no actionable findings", "无", "无可执行问题"},
    "remaining work": {"none", "closed", "no remaining work", "无", "无剩余事项"},
    "remaining risks": {"none", "closed", "no remaining risks", "无", "无剩余风险"},
}
RECORD_SCHEMAS = {
    "development-plan": {"baseline version", "baseline sha-256", "objective", "scope", "ordered steps", "verification criteria", "known risks"},
    "progress-record": {"run id", "code version", "modules", "module run records", "module latest records", "completion date", "delivered result", "validation performed", "remaining work", "status"},
    "progress-index": {"run id", "code version", "modules", "module run records", "module latest records", "completion date", "delivered result", "validation performed", "remaining work", "status"},
    "automated-review": {"run id", "code version", "code fingerprint", "command manifest fingerprint", "scope", "changed files", "review command id", "review command argv sha-256", "review exit code", "review evidence path", "review evidence sha-256", "findings", "rerun command ids", "rerun exit codes", "verdict"},
    "execution-run": {"run id", "module", "status", "code version", "context cache key", "baseline version and sha-256", "build id and acceptance environment", "risk level and reason", "traceability ids", "changed files", "delivered result", "context workset manifest and reused evidence fingerprints", "automated review evidence", "independent review evidence", "swimlane evidence", "frontend evidence", "classified findings and routes", "verification evidence", "frontend interaction evidence", "swimlane diagrams and validated evidence", "remaining risks"},
    "module-latest": {"module", "run id", "code version", "status", "record", "delivered result", "verification evidence", "swimlane evidence", "remaining risks"},
}
STATIC_HEADINGS = {
    "development-plan": r"(?:Development Plan|开发计划)",
    "progress-record": r"(?:Completion Progress|完成进度)",
    "progress-index": r"(?:Completion Progress|完成进度)",
    "automated-review": r"(?:Automated Review Evidence|自动审查证据)",
}


def split_record_paths(value: str) -> list[str]:
    return [item.strip().strip("`") for item in value.split(",") if item.strip()]


def _relative_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _validate_record(
    raw_path: str | None, root: Path, label: str, expected: dict[str, str],
    required: tuple[str, ...], allowed_statuses: set[str] | None = None,
    closed_field: str | None = None,
) -> list[Issue]:
    path_issue, text = _read_record(raw_path, root, label)
    if path_issue:
        return [path_issue]
    fields, duplicates, unexpected, heading = _record_fields(text)
    if duplicates:
        return [Issue("error", f"bundle-{label}-duplicate-field", "记录字段不得重复", raw_path or "")]
    heading_pattern = _heading_pattern(label, expected)
    if heading_pattern and (heading is None or not re.fullmatch(heading_pattern, heading, re.IGNORECASE)):
        unexpected.append(heading or "missing-h1")
    unknown = set(fields) - RECORD_SCHEMAS.get(label, set())
    if unexpected or unknown:
        return [Issue("error", f"bundle-{label}-unexpected-content", "记录包含正文或未声明字段", raw_path or "")]
    if any(not fields.get(field.casefold(), "").strip() for field in required):
        return [Issue("error", f"bundle-{label}-incomplete", "记录缺少必填交付字段", raw_path or "")]
    if any(not value or fields.get(field.casefold(), "") != value for field, value in expected.items()):
        return [Issue("error", f"bundle-{label}-stale", "记录未绑定当前基线、run、代码或模块", raw_path or "")]
    status = fields.get("status") or fields.get("verdict")
    if allowed_statuses is not None and status not in allowed_statuses:
        return [Issue("error", f"bundle-{label}-stage-mismatch", "记录状态与当前交付阶段不一致", raw_path or "")]
    if closed_field and fields.get(closed_field.casefold(), "").casefold() not in CLOSED_VALUES[closed_field.casefold()]:
        suffix = "open-findings" if closed_field == "Findings" else "open-work"
        return [Issue("error", f"bundle-{label}-{suffix}", "记录仍声明未关闭问题", raw_path or "")]
    return []


def _heading_pattern(label: str, expected: dict[str, str]) -> str | None:
    if label == "execution-run":
        value = re.escape(expected.get("Run ID", ""))
        return rf"(?:Run|执行)\s+{value}" if value else None
    if label == "module-latest":
        value = re.escape(expected.get("Module", ""))
        return rf"(?:Latest|最新)\s+{value}" if value else None
    return STATIC_HEADINGS.get(label)


def _read_record(raw_path: str | None, root: Path, label: str) -> tuple[Issue | None, str]:
    if not raw_path:
        return Issue("error", f"bundle-{label}-path-unresolved", "AGENTS 未声明可解析的记录路径", "delivery-bundle"), ""
    resolved_root, candidate = root.resolve(), Path(raw_path)
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return Issue("error", f"bundle-{label}-unsafe", "记录路径必须位于项目内", raw_path), ""
    if candidate.is_absolute() or _has_symlink_component(resolved_root, candidate) or not resolved.is_file():
        return Issue("error", f"bundle-{label}-missing", "记录缺失或不是普通文件", raw_path), ""
    try:
        payload = resolved.read_bytes()
        if b"\x00" in payload:
            return Issue("error", f"bundle-{label}-nul-byte", "记录包含 NUL 字节", raw_path), ""
        return None, payload.decode("utf-8")
    except (OSError, UnicodeError) as error:
        return Issue("error", f"bundle-{label}-unreadable", str(error), raw_path), ""


def _record_fields(text: str) -> tuple[dict[str, str], set[str], list[str], str | None]:
    fields: dict[str, str] = {}
    duplicates: set[str] = set()
    unexpected: list[str] = []
    heading: str | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            match = re.fullmatch(r"#\s+(.+?)\s*", line)
            if match and heading is None:
                heading = match.group(1)
            else:
                unexpected.append(line)
            continue
        match = re.match(r"^-\s+([^:]+):\s*(.*?)\s*$", line)
        if not match:
            unexpected.append(line)
            continue
        field, value = match.group(1).strip().casefold(), match.group(2).strip()
        if field in fields:
            duplicates.add(field)
        fields[field] = value.strip("`")
    return fields, duplicates, unexpected, heading


def _has_symlink_component(root: Path, candidate: Path) -> bool:
    if candidate.is_absolute():
        return True
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False
