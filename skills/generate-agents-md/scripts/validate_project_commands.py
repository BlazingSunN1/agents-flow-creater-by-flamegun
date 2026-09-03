from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from strict_json import loads as strict_json_loads
from browser_url_validation import is_http_browser_url


PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
REQUIRED_COMMANDS = {
    "delivery_contract",
    "targeted_tests",
    "full_test_or_build",
    "code_standards",
    "automated_review",
    "traceability",
    "context_manifest",
    "multi_agent_evidence",
    "swimlane_evidence",
    "swimlane_freshness",
    "native_mobile_tests",
    "atomic_record_update",
    "delivery_bundle",
}
CONDITIONAL_FRONTEND_COMMANDS = {"frontend_e2e", "frontend_evidence"}
FORBIDDEN_EXECUTABLES = {"true", "echo", "printf", "env", "command", "xargs", "bash", "sh", "zsh", "cmd", "powershell", "pwsh"}
FORBIDDEN_ARGUMENTS = {"||", "&&", ";", "--no-verify", "-c"}
SHELL_OPERATOR_RE = re.compile(r"(?:\||&&|[;\r\n])")
SHELL_EXECUTABLES = {"bash", "sh", "zsh", "cmd", "powershell", "pwsh"}
FRONTEND_ENTRY_FIELDS = {"frontend_preview_url", "frontend_preview_root", "frontend_entry_artifact"}
TOP_LEVEL_FIELDS = {"schema_version", "frontend_applicable", "commands"} | FRONTEND_ENTRY_FIELDS
COMMAND_FIELDS = {
    "id", "argv", "source", "source_selector", "source_command",
    "working_directory", "applicability",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_project_commands(path: Path, *, project_root: Path, template: bool = False) -> list[Issue]:
    data, issues = _read_json(path)
    if data is None:
        return issues
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issues.append(Issue("error", "invalid-schema-version", "命令清单 schema_version 必须是 1"))
    if set(data) != TOP_LEVEL_FIELDS:
        issues.append(Issue("error", "invalid-command-manifest-fields", "命令清单含缺失或未知字段"))
    commands = data.get("commands")
    if not isinstance(commands, list):
        issues.append(Issue("error", "missing-commands", "commands 必须是数组"))
        return _deduplicate(issues)
    ids = [item.get("id") for item in commands if isinstance(item, dict)]
    for command_id in REQUIRED_COMMANDS - set(ids):
        issues.append(Issue("error", "missing-command", f"缺少必需命令：{command_id}"))
    if len(ids) != len(set(ids)):
        issues.append(Issue("error", "duplicate-command-id", "命令清单包含重复 id"))
    if template:
        _validate_template_commands(data, issues)
        return _deduplicate(issues)
    text = path.read_text(encoding="utf-8")
    if PLACEHOLDER_RE.search(text):
        issues.append(Issue("error", "placeholder", "项目命令清单包含未解析占位符"))
    frontend = data.get("frontend_applicable")
    if not isinstance(frontend, bool):
        issues.append(Issue("error", "invalid-frontend-applicability", "frontend_applicable 必须是布尔值"))
    root = project_root.resolve()
    _validate_frontend_entry(data, root, issues)
    command_map = {item.get("id"): item for item in commands if isinstance(item, dict)}
    if frontend is True:
        for command_id in CONDITIONAL_FRONTEND_COMMANDS:
            if command_map.get(command_id, {}).get("applicability") != "required":
                issues.append(Issue("error", "missing-frontend-command", f"前端项目必须启用 {command_id} 命令"))
    for item in commands:
        if isinstance(item, dict):
            _validate_command(item, root, issues)
        else:
            issues.append(Issue("error", "invalid-command-entry", "命令条目必须是对象"))
    return _deduplicate(issues)


def _validate_template_commands(data: dict[str, object], issues: list[Issue]) -> None:
    frontend = data.get("frontend_applicable")
    if type(frontend) is not bool and not (type(frontend) is str and PLACEHOLDER_RE.fullmatch(frontend)):
        issues.append(Issue("error", "invalid-frontend-applicability", "模板 frontend_applicable 必须是布尔值或单一占位符"))
    for field in FRONTEND_ENTRY_FIELDS:
        value = data.get(field)
        if type(value) is not str or not value.strip():
            issues.append(Issue("error", "invalid-frontend-entry", f"模板 {field} 必须是非空字符串"))
    url = data.get("frontend_preview_url")
    preview = data.get("frontend_preview_root")
    artifact = data.get("frontend_entry_artifact")
    if (type(url) is str and not PLACEHOLDER_RE.fullmatch(url) and not is_http_browser_url(url)):
        issues.append(Issue("error", "invalid-frontend-entry", "模板前端 URL 必须是 HTTP(S) 或单一占位符"))
    if (type(preview) is str and not PLACEHOLDER_RE.fullmatch(preview)
            and not _safe_template_entry_path(preview, allow_dot=True)):
        issues.append(Issue("error", "invalid-frontend-entry", "模板预览根目录必须是安全项目相对路径"))
    if (type(artifact) is str and not PLACEHOLDER_RE.fullmatch(artifact)
            and not _safe_template_entry_path(artifact, allow_dot=False)):
        issues.append(Issue("error", "invalid-frontend-entry", "模板入口工件必须是安全项目相对文件路径"))
    commands = data.get("commands")
    if not isinstance(commands, list):
        return
    for item in commands:
        if not isinstance(item, dict):
            issues.append(Issue("error", "invalid-command-entry", "命令条目必须是对象"))
            continue
        if set(item) != COMMAND_FIELDS:
            issues.append(Issue("error", "invalid-command-fields", "命令条目含缺失或未知字段"))
        strings = COMMAND_FIELDS - {"argv"}
        if any(type(item.get(field)) is not str or not item.get(field, "").strip() for field in strings):
            issues.append(Issue("error", "invalid-command-field-types", "模板命令字段必须是非空字符串"))
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or any(type(value) is not str or not value for value in argv):
            issues.append(Issue("error", "invalid-command-argv", "模板 argv 必须是非空字符串数组"))
            continue
        executable = Path(argv[0]).name.casefold()
        unsafe = executable in FORBIDDEN_EXECUTABLES or any(
            value in FORBIDDEN_ARGUMENTS or SHELL_OPERATOR_RE.search(value)
            or Path(value).name.casefold() in SHELL_EXECUTABLES for value in argv[1:]
        )
        if unsafe:
            issues.append(Issue("error", "unsafe-command", "模板命令不得吞错、使用 Shell 包装或绕过参数"))


def _validate_frontend_entry(data: dict[str, object], root: Path, issues: list[Issue]) -> None:
    values = {field: data.get(field) for field in FRONTEND_ENTRY_FIELDS}
    if any(type(value) is not str or not value.strip() for value in values.values()):
        issues.append(Issue("error", "invalid-frontend-entry", "前端预览 URL、根目录和入口工件必须是非空字符串"))
        return
    if data.get("frontend_applicable") is not True:
        if any(not re.fullmatch(r"N/A:\s*\S.+", str(value), re.IGNORECASE) for value in values.values()):
            issues.append(Issue("error", "unexpected-frontend-entry", "非前端项目的预览入口字段必须使用 N/A: 原因"))
        return
    if not is_http_browser_url(values["frontend_preview_url"]):
        issues.append(Issue("error", "invalid-frontend-preview-url", "前端预览 URL 必须是无内嵌凭据的 HTTP(S) URL"))
    preview = _resolve_path(str(values["frontend_preview_root"]), root, issues, "frontend-preview-root", require_directory=True)
    entry = _resolve_path(str(values["frontend_entry_artifact"]), root, issues, "frontend-entry-artifact", require_directory=False)
    if entry is not None and not entry.is_file():
        issues.append(Issue("error", "invalid-frontend-entry-artifact", "前端入口工件必须是普通文件"))
    if preview is not None and entry is not None:
        try:
            entry.relative_to(preview)
        except ValueError:
            issues.append(Issue("error", "frontend-entry-outside-preview", "前端入口工件必须位于预览根目录内"))


def _safe_template_entry_path(value: str, *, allow_dot: bool) -> bool:
    if "\\" in value or (value == "." and not allow_dot):
        return False
    candidate = Path(value)
    return bool(value) and not candidate.is_absolute() and all(part not in {"", ".."} for part in candidate.parts)


def _read_json(path: Path) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        payload = path.read_text(encoding="utf-8")
        data = strict_json_loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [Issue("error", "invalid-command-manifest", str(error))]
    if not isinstance(data, dict):
        return None, [Issue("error", "invalid-command-manifest", "命令清单根节点必须是对象")]
    return data, []


def _validate_command(item: dict[str, object], root: Path, issues: list[Issue]) -> None:
    if set(item) != COMMAND_FIELDS:
        issues.append(Issue("error", "invalid-command-fields", "命令条目含缺失或未知字段"))
    string_fields = COMMAND_FIELDS - {"argv"}
    if any(type(item.get(field)) is not str or not item.get(field, "").strip() for field in string_fields):
        issues.append(Issue("error", "invalid-command-field-types", "命令身份、来源、目录和适用性必须是非空字符串"))
    command_id = str(item.get("id", "")).strip()
    applicability = str(item.get("applicability", "")).strip()
    if applicability != "required":
        if not re.fullmatch(r"N/A:\s*\S.+", applicability, re.IGNORECASE):
            issues.append(Issue("error", "invalid-command-applicability", f"{command_id} 的 applicability 非法"))
        return
    argv = item.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(value, str) or not value for value in argv):
        issues.append(Issue("error", "invalid-command-argv", f"{command_id} 的 argv 必须是非空字符串数组"))
        return
    executable = Path(argv[0]).name.casefold()
    inline_code = executable.startswith("python") and any(value == "-c" or value.startswith("-c") for value in argv[1:])
    shell_syntax = any(value in FORBIDDEN_ARGUMENTS or SHELL_OPERATOR_RE.search(value) for value in argv[1:])
    indirect_shell = any(Path(value).name.casefold() in SHELL_EXECUTABLES for value in argv[1:])
    if executable in FORBIDDEN_EXECUTABLES or inline_code or shell_syntax or indirect_shell:
        issues.append(Issue("error", "unsafe-command", f"{command_id} 使用了吞错、Shell 包装或绕过参数"))
    elif "/" in argv[0]:
        _resolve_path(argv[0], root, issues, "command-executable", require_directory=False)
    elif shutil.which(argv[0]) is None:
        issues.append(Issue("error", "missing-executable", f"{command_id} 的可执行文件不存在：{argv[0]}"))
    working_directory = _resolve_path(str(item.get("working_directory", "")), root, issues, "working-directory", require_directory=True)
    source = _resolve_path(str(item.get("source", "")), root, issues, "command-source", require_directory=False)
    selector = str(item.get("source_selector", "")).strip()
    source_command = str(item.get("source_command", "")).strip()
    if not selector:
        issues.append(Issue("error", "missing-source-selector", f"{command_id} 缺少 source_selector"))
    elif source and source.is_file() and selector not in source.read_text(encoding="utf-8", errors="replace"):
        issues.append(Issue("error", "undeclared-command", f"{command_id} 的声明来源不包含 selector：{selector}"))
    if not source_command or source is None or not source.is_file():
        issues.append(Issue("error", "missing-source-command", f"{command_id} 缺少完整声明命令"))
    else:
        try:
            declared_argv = shlex.split(source_command)
        except ValueError:
            declared_argv = []
        if declared_argv != argv or source_command not in source.read_text(encoding="utf-8", errors="replace"):
            issues.append(Issue("error", "command-declaration-mismatch", f"{command_id} 的 argv 未绑定来源中的完整命令"))
    if working_directory and not working_directory.is_dir():
        issues.append(Issue("error", "invalid-working-directory", f"{command_id} 的工作目录不是目录"))


def _resolve_path(
    value: str,
    root: Path,
    issues: list[Issue],
    code: str,
    *,
    require_directory: bool,
) -> Path | None:
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径必须位于项目内：{value}"))
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径越出项目根：{value}"))
        return None
    if not resolved.exists():
        issues.append(Issue("error", f"missing-{code}", f"引用路径不存在：{value}"))
        return None
    if require_directory and not resolved.is_dir():
        issues.append(Issue("error", f"invalid-{code}", f"路径必须是目录：{value}"))
    return resolved


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证项目命令来自真实配置且不使用恒定成功或吞错包装")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_project_commands(arguments.path, project_root=arguments.project_root, template=arguments.template)
    failed = any(item.severity == "error" for item in issues)
    if arguments.json:
        print(json.dumps({"valid": not failed, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            print(f"{item.severity.upper()} {item.code} {item.message}")
        print(f"errors={sum(item.severity == 'error' for item in issues)} valid={str(not failed).lower()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
