from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from authority_binding_validation import authority_binding_issues, authority_metadata_issues
from context_cache_validation import _cache_key_from_requirement_ids

PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
REQUIREMENT_ID_RE = re.compile(r"REQ-\d+")
STABLE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REQUIRED_FIELDS = (
    "Run ID",
    "Baseline artifact",
    "Baseline version",
    "Baseline SHA-256",
    "Authority matrix locator",
    "Authority matrix SHA-256",
    "Code version",
    "Build ID",
    "Risk / expansion reason",
    "Requirement IDs",
    "Modules",
    "Module changed files",
    "Changed files",
    "Configuration files",
    "Input files",
    "Direct dependency boundaries",
    "Required commands",
    "Effective AGENTS files",
    "Effective AGENTS fingerprint",
    "Command manifest",
    "Command manifest fingerprint",
    "Code fingerprint",
    "Command fingerprint",
    "Configuration fingerprint",
    "Environment ID",
    "Input fingerprint",
    "Evidence fingerprint",
    "Evidence cache key",
    "Reuse decision",
    "Reuse record",
    "Evidence paths",
)
FINGERPRINT_FIELDS = (
    "Code fingerprint",
    "Command fingerprint",
    "Effective AGENTS fingerprint",
    "Command manifest fingerprint",
    "Configuration fingerprint",
    "Input fingerprint",
    "Evidence fingerprint",
)


def _cache_key(metadata: dict[str, str]) -> str:
    requirement_ids = ",".join(sorted(
        item.strip().casefold()
        for item in metadata.get("Requirement IDs", "").split(",")
        if item.strip()
    ))
    cache_scope = (
        metadata.get("Baseline artifact", ""),
        metadata.get("Baseline version", ""),
        metadata.get("Baseline SHA-256", "").casefold(),
        _canonical_module_file_map(metadata.get("Module changed files", "")),
        metadata.get("Risk / expansion reason", ""),
        metadata.get("Direct dependency boundaries", ""),
        metadata.get("Code version", ""),
        metadata.get("Build ID", ""),
    )
    return _cache_key_from_requirement_ids(metadata, requirement_ids, cache_scope)

@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    line: int | None = None

def validate_context_manifest(
    path: Path,
    *,
    project_root: Path,
    template: bool = False,
) -> list[Issue]:
    text, read_issues = _read_manifest(path)
    if text is None:
        return read_issues
    metadata, duplicate_fields = _parse_metadata(text)
    issues = read_issues + _validate_manifest_structure(text, metadata, duplicate_fields, template)
    if template:
        issues.extend(_validate_template_values(metadata))
        issues.extend(Issue("error", code, message) for code, message in authority_metadata_issues(metadata))
        return _deduplicate(issues)
    if issues:
        return _deduplicate(issues)
    root = project_root.resolve()
    _validate_baseline(metadata, root, issues)
    issues.extend(
        Issue("error", code, message)
        for code, message in authority_binding_issues(
            metadata, root, effective_agents=_split_paths(metadata["Effective AGENTS files"]),
        )
    )
    _validate_fingerprints(metadata, root, issues)
    _validate_reuse(metadata, root, issues)
    return _deduplicate(issues)

def _validate_template_values(metadata: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    placeholder = lambda value: bool(PLACEHOLDER_RE.fullmatch(value.strip()))
    run_id = metadata.get("Run ID", "")
    if run_id and not placeholder(run_id) and not STABLE_ID_RE.fullmatch(run_id):
        issues.append(Issue("error", "invalid-run-id", "模板 Run ID 必须是稳定单段标识符或占位符"))
    requirement_ids = metadata.get("Requirement IDs", "")
    if requirement_ids and not placeholder(requirement_ids):
        values = [item.strip() for item in requirement_ids.split(",") if item.strip()]
        if not values or any(not REQUIREMENT_ID_RE.fullmatch(item) for item in values):
            issues.append(Issue("error", "invalid-requirement-ids", "模板 Requirement IDs 格式非法"))
    modules = metadata.get("Modules", "")
    if modules and not placeholder(modules):
        values = [item.strip() for item in modules.split(",") if item.strip()]
        if not values or len(values) != len(set(values)) or any(not STABLE_ID_RE.fullmatch(item) for item in values):
            issues.append(Issue("error", "invalid-modules", "模板 Modules 格式非法"))
    module_map = metadata.get("Module changed files", "")
    if module_map and not placeholder(module_map) and not _parse_module_file_map(module_map):
        issues.append(Issue("error", "invalid-module-changed-files", "模板 Module changed files 格式非法"))
    baseline = metadata.get("Baseline artifact", "").strip()
    if baseline and not placeholder(baseline) and not _safe_template_path(baseline):
        issues.append(Issue("error", "unsafe-baseline-artifact", "模板 Baseline artifact 必须是安全项目相对路径"))
    reuse = metadata.get("Reuse decision", "").strip()
    if reuse and not placeholder(reuse) and reuse != "rerun":
        issues.append(Issue("error", "invalid-template-reuse", "公共模板不得预先复用未绑定当前基线的旧证据"))
    return issues

def _safe_template_path(raw: str) -> bool:
    if "\\" in raw or raw.startswith("/"):
        return False
    parts = raw.split("/")
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)

def _read_manifest(path: Path) -> tuple[str | None, list[Issue]]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        return None, [Issue("error", "unreadable-file", f"无法读取工作集清单：{error}")]
    if b"\x00" in payload:
        return None, [Issue("error", "nul-byte", "工作集清单包含 NUL 字节")]
    try:
        return payload.decode("utf-8"), []
    except UnicodeDecodeError as error:
        return None, [Issue("error", "invalid-utf8", f"工作集清单不是有效 UTF-8：{error.start}")]

def _validate_manifest_structure(
    text: str,
    metadata: dict[str, str],
    duplicate_fields: list[tuple[str, int]],
    template: bool,
) -> list[Issue]:
    issues = [
        Issue("error", "duplicate-field", f"工作集字段重复：{field}", line)
        for field, line in duplicate_fields
    ]
    for field in REQUIRED_FIELDS:
        if not metadata.get(field, "").strip():
            issues.append(Issue("error", "missing-field", f"缺少工作集字段：{field}"))
    if not template and PLACEHOLDER_RE.search(text):
        issues.append(Issue("error", "placeholder", "项目工作集清单包含未解析占位符"))
    return issues

def _validate_baseline(metadata: dict[str, str], root: Path, issues: list[Issue]) -> None:
    baseline = _resolve_path(metadata["Baseline artifact"], root, issues, "baseline-artifact")
    expected_baseline_sha = metadata["Baseline SHA-256"].casefold()
    if not SHA256_RE.fullmatch(expected_baseline_sha):
        issues.append(Issue("error", "invalid-baseline-sha256", "Baseline SHA-256 必须是 64 位十六进制"))
    elif baseline and baseline.is_file():
        actual = hashlib.sha256(baseline.read_bytes()).hexdigest()
        if actual != expected_baseline_sha:
            issues.append(Issue("error", "stale-baseline-hash", "需求基线哈希已经失效"))

def _validate_fingerprints(metadata: dict[str, str], root: Path, issues: list[Issue]) -> None:
    for field in FINGERPRINT_FIELDS:
        if not SHA256_RE.fullmatch(metadata[field]):
            issues.append(Issue("error", "invalid-fingerprint", f"{field} 必须是 64 位 SHA-256",))

    requirement_ids = [item.strip() for item in metadata["Requirement IDs"].split(",") if item.strip()]
    if (not requirement_ids or len(requirement_ids) != len(set(requirement_ids))
            or any(not REQUIREMENT_ID_RE.fullmatch(item) for item in requirement_ids)):
        issues.append(Issue("error", "invalid-requirement-ids", "Requirement IDs 必须是逗号分隔的 REQ-数字"))
    if not STABLE_ID_RE.fullmatch(metadata["Run ID"]):
        issues.append(Issue("error", "invalid-run-id", "Run ID 必须是稳定的单段标识符"))
    risk_parts = [part.strip() for part in metadata["Risk / expansion reason"].split(";")]
    if len(risk_parts) != 3 or any(not part for part in risk_parts):
        issues.append(Issue("error", "invalid-risk-expansion", "风险字段必须恰好包含等级、原因和工作集扩展原因三段"))
    for field in ("Changed files", "Configuration files", "Input files", "Effective AGENTS files", "Evidence paths"):
        paths = _split_paths(metadata[field])
        if len(paths) != len(set(paths)):
            issues.append(Issue("error", "duplicate-workset-path", f"{field} 不得重复声明同一路径"))
    issues.extend(_module_mapping_issues(metadata, root))

    calculated_fingerprints = {
        "Code fingerprint": _paths_fingerprint(metadata["Changed files"], root, issues, "changed-file"),
        "Command fingerprint": hashlib.sha256(metadata["Required commands"].encode("utf-8")).hexdigest(),
        "Effective AGENTS fingerprint": _paths_fingerprint(
            metadata["Effective AGENTS files"], root, issues, "agents-file"
        ),
        "Command manifest fingerprint": _paths_fingerprint(metadata["Command manifest"], root, issues, "command-manifest"),
        "Configuration fingerprint": _paths_fingerprint(metadata["Configuration files"], root, issues, "configuration-file"),
        "Input fingerprint": _paths_fingerprint(metadata["Input files"], root, issues, "input-file"),
        "Evidence fingerprint": _paths_fingerprint(metadata["Evidence paths"], root, issues, "reuse-evidence"),
    }
    for field, actual in calculated_fingerprints.items():
        if SHA256_RE.fullmatch(metadata[field]) and metadata[field].casefold() != actual:
            issues.append(Issue("error", f"stale-{field.casefold().replace(' ', '-')}", f"{field} 与当前文件或命令内容不一致"))

    declared_agents = set(_split_paths(metadata["Effective AGENTS files"]))
    discovered_agents = _discover_effective_agents(metadata, root, issues)
    if declared_agents != discovered_agents:
        issues.append(Issue("error", "stale-effective-agents-set", "Effective AGENTS files 未完整覆盖当前工作集的生效规则链"))

    expected_cache_key = _cache_key(metadata)
    if metadata["Evidence cache key"].casefold() != expected_cache_key:
        issues.append(Issue("error", "stale-evidence-cache-key", "证据缓存键与当前代码、命令、配置、环境或输入指纹不一致"))


def _validate_reuse(metadata: dict[str, str], root: Path, issues: list[Issue]) -> None:
    reuse = metadata["Reuse decision"].strip()
    if reuse == "rerun":
        if not _is_na(metadata["Reuse record"]):
            issues.append(Issue("error", "invalid-reuse-record", "rerun 时 Reuse record 必须是 N/A: 原因"))
        return
    if not re.fullmatch(r"reuse:\s*[A-Za-z0-9._-]+", reuse):
        issues.append(Issue("error", "invalid-reuse-decision", "Reuse decision 必须是 rerun 或 reuse: <run_id>"))
        return
    reused_run_id = reuse.split(":", 1)[1].strip()
    modules = [item.strip() for item in metadata.get("Modules", "").split(",") if item.strip()]
    if len(modules) != 1:
        issues.append(Issue(
            "error", "multi-module-reuse-requires-rerun",
            "单一复用源记录只能证明一个模块；多模块工作集必须重新运行验证",
        ))
    if reused_run_id == metadata.get("Run ID", "").strip():
        issues.append(Issue("error", "reuse-current-run", "当前 Run ID 不能复用自身，必须引用已完成的既往 run"))
    evidence_paths = _split_paths(metadata["Evidence paths"])
    if not evidence_paths or _is_na(metadata["Evidence paths"]):
        issues.append(Issue("error", "missing-reuse-evidence", "复用证据时必须提供已有项目内证据路径"))
    else:
        for raw_path in evidence_paths:
            _resolve_path(raw_path, root, issues, "reuse-evidence")
    _validate_reuse_record(metadata, root, reused_run_id, issues)


def _validate_reuse_record(
    metadata: dict[str, str], root: Path, reused_run_id: str, issues: list[Issue],
) -> None:
    record = _resolve_path(metadata["Reuse record"], root, issues, "reuse-record")
    if record is None:
        return
    try:
        from strict_json import loads as strict_json_loads
        data = strict_json_loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        issues.append(Issue("error", "invalid-reuse-record", "Reuse record 必须是无重复键的 UTF-8 JSON"))
        return
    expected_paths = []
    for raw_path in sorted(_split_paths(metadata["Evidence paths"])):
        resolved = _resolve_path(raw_path, root, issues, "reuse-evidence")
        if resolved is not None and resolved.is_file():
            expected_paths.append({"path": raw_path, "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()})
    expected = {
        "schema_version": 1,
        "run_id": reused_run_id,
        "status": "passed",
        "evidence_cache_key": _cache_key(metadata),
        "source_run_record": data.get("source_run_record") if isinstance(data, dict) else None,
        "evidence_paths": expected_paths,
    }
    if not _valid_reuse_record_types(data) or data != expected:
        issues.append(Issue("error", "stale-reuse-record", "Reuse record 必须绑定成功 run、当前缓存键和全部证据哈希"))
        return
    _validate_reuse_source_run(
        data["source_run_record"], reused_run_id, expected["evidence_cache_key"],
        expected_paths, metadata, root, issues,
    )


def _valid_reuse_record_types(data: object) -> bool:
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "run_id", "status", "evidence_cache_key", "source_run_record", "evidence_paths",
    }:
        return False
    source = data.get("source_run_record")
    evidence = data.get("evidence_paths")
    return (
        type(data.get("schema_version")) is int and data.get("schema_version") == 1
        and all(type(data.get(field)) is str for field in ("run_id", "status", "evidence_cache_key"))
        and isinstance(source, dict) and set(source) == {"module", "path", "sha256", "context_path", "context_sha256"}
        and all(type(source.get(field)) is str for field in ("module", "path", "sha256", "context_path", "context_sha256"))
        and isinstance(evidence, list) and all(
            isinstance(item, dict) and set(item) == {"path", "sha256"}
            and all(type(item.get(field)) is str for field in ("path", "sha256")) for item in evidence
        )
    )


def _validate_reuse_source_run(
    source: dict[str, object], run_id: str, cache_key: object,
    evidence_paths: list[dict[str, str]], metadata: dict[str, str], root: Path, issues: list[Issue],
) -> None:
    modules = [item.strip() for item in metadata.get("Modules", "").split(",") if item.strip()]
    if len(modules) != 1 or source.get("module") != modules[0]:
        issues.append(Issue("error", "stale-reuse-source-run", "复用源 run 必须精确绑定当前唯一模块"))
        return
    raw_path = str(source["path"])
    record = _resolve_path(raw_path, root, issues, "reuse-source-run")
    if record is None or not record.is_file():
        issues.append(Issue("error", "missing-reuse-source-run", "复用必须绑定现存的不可变成功 run 记录"))
        return
    if not SHA256_RE.fullmatch(str(source["sha256"])) or hashlib.sha256(record.read_bytes()).hexdigest() != str(source["sha256"]).casefold():
        issues.append(Issue("error", "stale-reuse-source-run", "复用源 run 记录哈希失效"))
        return
    from reuse_source_run_validation import valid_reuse_source_run
    if not valid_reuse_source_run(raw_path, root, run_id, cache_key, evidence_paths, metadata, source):
        issues.append(Issue("error", "stale-reuse-source-run", "复用源 run 必须为当前缓存键下已完成且证据集合一致的记录"))


def _parse_module_file_map(value: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in value.split(";"):
        module, separator, raw_paths = item.strip().partition("=")
        path_items = [path.strip() for path in raw_paths.split(",") if path.strip()]
        paths = set(path_items)
        if not separator or len(path_items) != len(paths) or not STABLE_ID_RE.fullmatch(module) or module in result:
            return {}
        result[module] = paths
    return result


def _module_mapping_issues(metadata: dict[str, str], root: Path) -> list[Issue]:
    modules = [item.strip() for item in metadata["Modules"].split(",") if item.strip()]
    if not modules or len(modules) != len(set(modules)) or any(not STABLE_ID_RE.fullmatch(item) for item in modules):
        return [Issue("error", "invalid-modules", "Modules 必须是逗号分隔的稳定单段标识符")]
    mapping = _parse_module_file_map(metadata.get("Module changed files", ""))
    changed = set(_split_paths(metadata.get("Changed files", "")))
    if set(mapping) != set(modules) or any(not paths for paths in mapping.values()):
        return [Issue("error", "invalid-module-changed-files", "Module changed files 必须逐模块声明非空文件集合")]
    if set().union(*mapping.values()) != changed:
        return [Issue("error", "stale-module-changed-files", "模块文件映射必须精确覆盖 Changed files")]
    owners: dict[tuple[int, int], str] = {}
    raw_owners: dict[str, str] = {}
    for module, paths in mapping.items():
        for raw_path in paths:
            candidate = Path(raw_path)
            if candidate.is_absolute() or raw_path != candidate.as_posix() or ".." in candidate.parts:
                return [Issue("error", "unsafe-module-changed-file", f"模块文件路径必须规范且位于项目内：{raw_path}")]
            try:
                identity = ((root / candidate).stat().st_dev, (root / candidate).stat().st_ino)
            except OSError:
                continue
            if raw_path in raw_owners or identity in owners:
                return [Issue("error", "ambiguous-module-changed-file", f"变更文件不得归属多个模块：{raw_path}")]
            raw_owners[raw_path], owners[identity] = module, module
    return []


def _canonical_module_file_map(value: str) -> str:
    mapping = _parse_module_file_map(value)
    return ";".join(f'{module}={",".join(sorted(mapping[module]))}' for module in sorted(mapping))


def _parse_metadata(text: str) -> tuple[dict[str, str], list[tuple[str, int]]]:
    metadata: dict[str, str] = {}
    duplicates: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^-\s+([^:]+):\s*(.*?)\s*$", line)
        if not match:
            continue
        field = match.group(1).strip()
        value = match.group(2).strip().strip("`")
        if field in metadata:
            duplicates.append((field, line_number))
        else:
            metadata[field] = value
    return metadata, duplicates


def _split_paths(value: str) -> list[str]:
    if _is_na(value):
        return []
    return [item.strip().strip("`") for item in value.split(",") if item.strip()]


def _paths_fingerprint(
    value: str,
    root: Path,
    issues: list[Issue],
    code: str,
) -> str:
    entries: list[str] = []
    for raw_path in sorted(_split_paths(value)):
        resolved = _resolve_path(raw_path, root, issues, code)
        if resolved and resolved.is_file():
            entries.append(f"{raw_path}\0{hashlib.sha256(resolved.read_bytes()).hexdigest()}")
    return hashlib.sha256("\0".join(entries).encode("utf-8")).hexdigest()


def _discover_effective_agents(
    metadata: dict[str, str],
    root: Path,
    issues: list[Issue],
) -> set[str]:
    discovered: set[str] = set()
    workset_paths: list[str] = []
    for field in ("Changed files", "Configuration files", "Input files"):
        workset_paths.extend(_split_paths(metadata.get(field, "")))
    for raw_path in workset_paths:
        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        if (root / candidate).is_symlink():
            issues.append(Issue("error", "unsafe-workset-symlink", f"工作集文件不得是符号链接：{raw_path}"))
            continue
        parent_parts = candidate.parent.parts
        for depth in range(len(parent_parts) + 1):
            directory = root / Path(*parent_parts[:depth])
            if directory.is_symlink():
                issues.append(Issue("error", "unsafe-workset-symlink", f"工作集文件的父目录不得是符号链接：{raw_path}"))
                break
            relative = Path(*parent_parts[:depth], "AGENTS.md")
            resolved = root / relative
            if resolved.is_symlink():
                issues.append(Issue("error", "unsafe-effective-agents-symlink", f"生效 AGENTS.md 不得是符号链接：{relative.as_posix()}"))
            elif resolved.is_file():
                discovered.add(relative.as_posix())
    return discovered


def _is_na(value: str) -> bool:
    return bool(re.fullmatch(r"N/A:\s*\S.+", value.strip(), re.IGNORECASE))


def _resolve_path(raw_path: str, root: Path, issues: list[Issue], code: str) -> Path | None:
    value = raw_path.strip().strip("`")
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径必须位于项目内：{value}"))
        return None
    declared = root / candidate
    if any((root / Path(*candidate.parts[:depth])).is_symlink() for depth in range(1, len(candidate.parts) + 1)):
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径不得包含符号链接：{value}"))
        return None
    resolved = declared.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径越出项目根：{value}"))
        return None
    if not resolved.exists():
        issues.append(Issue("error", f"missing-{code}", f"引用路径不存在：{value}"))
    elif not resolved.is_file():
        issues.append(Issue("error", f"nonfile-{code}", f"引用路径必须是普通文件：{value}"))
        return None
    return resolved


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message, item.line): item for item in issues}.values())

def main() -> int:
    parser = argparse.ArgumentParser(description="失败关闭地验证最小工作集和证据缓存指纹")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_context_manifest(
        arguments.path,
        project_root=arguments.project_root,
        template=arguments.template,
    )
    failed = any(issue.severity == "error" for issue in issues)
    if arguments.json:
        print(json.dumps({"valid": not failed, "issues": [asdict(issue) for issue in issues]}, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            location = f":{issue.line}" if issue.line else ""
            print(f"{issue.severity.upper()} {issue.code} {arguments.path}{location} {issue.message}")
        print(f"errors={sum(issue.severity == 'error' for issue in issues)} valid={str(not failed).lower()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
