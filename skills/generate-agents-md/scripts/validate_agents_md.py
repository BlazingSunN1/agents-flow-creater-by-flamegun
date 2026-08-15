from __future__ import annotations

import argparse
import ipaddress
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from agents_policy_validation import (
    REQUIRED_MACHINE_POLICY,
    _validate_password_authorization,
    _validate_root_policies,
)


PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
TODO_RE = re.compile(r"\b(?:TODO|FIXME|TBD)\b", re.IGNORECASE)
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.IPv4Network(value)
    for value in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
PERSONAL_PATH_RE = re.compile(
    r"(?:/Users/[^/\s`]+|/home/[^/\s`]+|[A-Za-z]:\\Users\\[^\\\s`]+)",
    re.IGNORECASE,
)
WINDOWS_DRIVE_RE = re.compile(r"(?<![\w])(?:[A-Za-z]:\\)(?!\{\{)[^\r\n`]+")
IDENTITY_HOST_RE = re.compile(
    r"\b(?:ssh\s+(?:-p\s+\d+\s+)?|scp\s+)?[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\b",
    re.IGNORECASE,
)
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"\b(password|passwd|token|access[_-]?token|refresh[_-]?token|secret|client[_-]?secret|"
    r"api[_-]?key|private[_-]?key|cookie|set-cookie|authorization)\b\s*[:=]\s*"
    r"(`[^`\r\n]+`|\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s#`]+)",
    re.IGNORECASE,
)
URI_CREDENTIAL_RE = re.compile(r"://[^\s/:@]+:[^\s/@]+@")
URI_CREDENTIAL_DETAIL_RE = re.compile(
    r"(?P<uri>[A-Za-z][A-Za-z0-9+.-]*://"
    r"(?P<username>[^/\s:@]+):(?P<password>[^/\s@]+)@"
    r"(?P<authority>\[[^\]]+\]|[^/\s?#]+)(?P<suffix>/[^\s]*)?)"
)
PRIVATE_KEY_HEADER_RE = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----", re.IGNORECASE)
ENVIRONMENT_REFERENCE_RE = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    line: int | None = None


def validate_bytes(
    payload: bytes,
    *,
    mode: str,
    allow_patterns: tuple[re.Pattern[str], ...] = (),
    allow_passwords: bool = False,
    scope: str = "root",
) -> list[Issue]:
    issues: list[Issue] = []
    if b"\x00" in payload:
        issues.append(Issue("error", "nul-byte", "文件包含 NUL 字节，不是有效 Markdown"))
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        issues.append(
            Issue(
                "error",
                "invalid-utf8",
                f"文件不是有效 UTF-8：字节偏移 {error.start}",
            )
        )
        return issues
    issues.extend(
        validate_text(
            text,
            mode=mode,
            allow_patterns=allow_patterns,
            allow_passwords=allow_passwords,
            scope=scope,
        )
    )
    return issues


def validate_text(
    text: str,
    *,
    mode: str,
    allow_patterns: tuple[re.Pattern[str], ...] = (),
    allow_passwords: bool = False,
    scope: str = "root",
) -> list[Issue]:
    issues = _validate_mode_scope(mode, scope, allow_passwords)
    effective_allow_passwords = allow_passwords and mode == "project"
    safe_allow_patterns = _validated_allow_patterns(allow_patterns, issues)
    issues.extend(_validate_file_format(text))
    lines = text.splitlines()
    issues.extend(_validate_headings(lines))
    scan_issues, authorized_password_present = _scan_document_lines(
        lines,
        mode=mode,
        allow_patterns=safe_allow_patterns,
        allow_passwords=effective_allow_passwords,
    )
    issues.extend(scan_issues)
    if authorized_password_present:
        issues.extend(_validate_password_authorization(text))
    if scope == "root":
        issues.extend(_validate_root_policies(text, mode))
    return _deduplicate(issues)


def _validate_mode_scope(mode: str, scope: str, allow_passwords: bool) -> list[Issue]:
    issues: list[Issue] = []
    if mode not in {"project", "public-template"}:
        issues.append(Issue("error", "invalid-mode", "mode 必须是 project 或 public-template"))
    if scope not in {"root", "scoped"}:
        issues.append(Issue("error", "invalid-scope", "scope 必须是 root 或 scoped"))
    effective_allow_passwords = allow_passwords and mode == "project"
    if allow_passwords and mode != "project":
        issues.append(
            Issue(
                "error",
                "password-allowance-mode",
                "密码授权只能用于 project 模式",
            )
        )
    return issues


def _validated_allow_patterns(
    allow_patterns: tuple[re.Pattern[str], ...],
    issues: list[Issue],
) -> tuple[re.Pattern[str], ...]:
    safe_patterns = tuple(
        pattern for pattern in allow_patterns if not _is_overbroad_allow_pattern(pattern)
    )
    if len(safe_patterns) != len(allow_patterns):
        issues.append(
            Issue(
                "error",
                "overbroad-allow-pattern",
                "--allow-pattern 不得匹配空字符串或批量覆盖不同类型的基础设施标识",
            )
        )
    return safe_patterns


def _validate_file_format(text: str) -> list[Issue]:
    issues: list[Issue] = []
    stripped = text.lstrip("\ufeff\r\n\t ")
    if stripped.startswith("{\\rtf"):
        issues.append(Issue("error", "rtf-content", "文件内容是 RTF，不是 Markdown"))
    lowered = stripped[:256].lower()
    if lowered.startswith("<!doctype html") or lowered.startswith("<html"):
        issues.append(Issue("error", "html-content", "文件内容是 HTML，不是 Markdown"))
    return issues


def _validate_headings(lines: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    if not any(line.startswith("# ") for line in lines):
        issues.append(Issue("warning", "missing-title", "缺少一级 Markdown 标题"))

    seen_headings: dict[tuple[int, str], int] = {}
    for line_number, line in enumerate(lines, start=1):
        heading_match = HEADING_RE.match(line)
        if not heading_match:
            continue
        key = (len(heading_match.group(1)), heading_match.group(2).strip().casefold())
        if key in seen_headings:
            issues.append(
                Issue(
                    "warning",
                    "duplicate-heading",
                    f"标题与第 {seen_headings[key]} 行重复：{heading_match.group(2).strip()}",
                    line_number,
                )
            )
        else:
            seen_headings[key] = line_number
    return issues


def _scan_document_lines(
    lines: list[str],
    *,
    mode: str,
    allow_patterns: tuple[re.Pattern[str], ...],
    allow_passwords: bool,
) -> tuple[list[Issue], bool]:
    issues: list[Issue] = []
    authorized_password_present = False
    for line_number, line in enumerate(lines, start=1):
        allow_infrastructure_reference = any(pattern.search(line) for pattern in allow_patterns)
        plaintext_uri_matches = tuple(
            match for match in URI_CREDENTIAL_DETAIL_RE.finditer(line)
            if not re.fullmatch(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)", match.group("password"))
        )
        authorized_uri_credentials = tuple(URI_CREDENTIAL_RE.finditer(line)) if allow_passwords and plaintext_uri_matches else ()
        if authorized_uri_credentials:
            authorized_password_present = True
        line_issues, line_has_password = _scan_line_secrets(
            line,
            line_number,
            mode=mode,
            allow_passwords=allow_passwords,
        )
        authorized_password_present = authorized_password_present or line_has_password
        issues.extend(line_issues)
        issues.extend(
            _scan_line_infrastructure(
                line,
                line_number,
                mode=mode,
                allowed=allow_infrastructure_reference,
                authorized_uri_credentials=authorized_uri_credentials,
            )
        )
    return issues, authorized_password_present


def _scan_line_secrets(
    line: str,
    line_number: int,
    *,
    mode: str,
    allow_passwords: bool,
) -> tuple[list[Issue], bool]:
    issues: list[Issue] = []
    if mode == "project" and PLACEHOLDER_RE.search(line):
        issues.append(Issue("error", "placeholder", "项目文件包含未解析占位符", line_number))
    if mode == "project" and "PUBLIC TEMPLATE" in line:
        issues.append(Issue("error", "template-marker", "项目文件残留公共模板标记", line_number))
    if TODO_RE.search(line):
        issues.append(Issue("error", "todo-marker", "文件包含 TODO/FIXME/TBD 标记", line_number))
    authorized_password = False
    for match in CREDENTIAL_ASSIGNMENT_RE.finditer(line):
        allowed = allow_passwords and match.group(1).casefold() in {"password", "passwd"}
        if allowed or _is_placeholder_secret(match.group(2)):
            authorized_password = authorized_password or allowed
        else:
            issues.append(Issue("error", "secret-value", f"疑似写入真实敏感值：{match.group(1)}", line_number))
    if PRIVATE_KEY_HEADER_RE.search(line):
        issues.append(Issue("error", "private-key", "文件包含私钥内容", line_number))
    plaintext_uri = any(
        not re.fullmatch(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)", match.group("password"))
        for match in URI_CREDENTIAL_DETAIL_RE.finditer(line)
    )
    if plaintext_uri and not allow_passwords:
        issues.append(Issue("error", "uri-credential", "连接地址疑似包含内嵌凭据；仅在用户明确授权后使用 --allow-passwords 放行", line_number))
    return issues, authorized_password


def _scan_line_infrastructure(
    line: str,
    line_number: int,
    *,
    mode: str,
    allowed: bool,
    authorized_uri_credentials: tuple[re.Match[str], ...],
) -> list[Issue]:
    if allowed:
        return []
    severity = "error" if mode == "public-template" else "warning"
    issues = [
        Issue(severity, "network-address", f"包含实际 IPv4 地址：{match.group(0)}", line_number)
        for match in IPV4_RE.finditer(line)
        if _is_sensitive_ipv4(match.group(0))
    ]
    if PERSONAL_PATH_RE.search(line):
        issues.append(Issue(severity, "personal-path", "包含个人主目录路径", line_number))
    elif WINDOWS_DRIVE_RE.search(line):
        issues.append(Issue(severity, "machine-path", "包含机器专属 Windows 绝对路径", line_number))
    for identity_match in IDENTITY_HOST_RE.finditer(line):
        if not _identity_belongs_to_authorized_uri(line, identity_match, authorized_uri_credentials):
            issues.append(Issue(severity, "identity-host", "包含用户名与主机标识", line_number))
    return issues


def _identity_belongs_to_authorized_uri(
    line: str,
    identity_match: re.Match[str],
    uri_matches: tuple[re.Match[str], ...],
) -> bool:
    return any(
        identity_match.start() < uri_match.end()
        and line.find("@", identity_match.start(), identity_match.end()) == uri_match.end() - 1
        for uri_match in uri_matches
    )


def _is_overbroad_allow_pattern(pattern: re.Pattern[str]) -> bool:
    samples = (
        "192.168.10.20",
        "/Users/example/project",
        "operator@example.internal",
    )
    return pattern.search("") is not None or all(pattern.search(value) for value in samples)


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip("\"'`")
    return bool(
        PLACEHOLDER_RE.fullmatch(normalized)
        or ENVIRONMENT_REFERENCE_RE.fullmatch(normalized)
    ) or normalized.upper() in {
        "REDACTED",
        "REMOVED",
        "***",
    }


def _is_sensitive_ipv4(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    if address.is_loopback or address.is_unspecified:
        return False
    return not any(address in network for network in DOCUMENTATION_NETWORKS)


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    unique: dict[tuple[str, str, str, int | None], Issue] = {}
    for issue in issues:
        unique[(issue.severity, issue.code, issue.message, issue.line)] = issue
    return list(unique.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验项目 AGENTS.md 或脱敏公共模板")
    parser.add_argument("path", type=Path)
    parser.add_argument("--mode", choices=("project", "public-template"), required=True)
    parser.add_argument(
        "--scope",
        choices=("root", "scoped"),
        default="root",
        help="校验根级公共规则或仅包含目录差异的子级文件",
    )
    parser.add_argument("--strict", action="store_true", help="将 warning 也视为失败")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parser.add_argument(
        "--allow-passwords",
        action="store_true",
        help="允许项目文件包含密码；仅在用户明确授权时使用",
    )
    parser.add_argument(
        "--allow-pattern",
        action="append",
        default=[],
        help="仅对匹配行的 IP、个人路径和用户@主机误报进行豁免；不影响凭据、占位符或待办扫描",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if arguments.allow_passwords and arguments.mode != "project":
        raise SystemExit("--allow-passwords 只能与 --mode project 一起使用")
    if not arguments.path.is_file():
        return _missing_path_result(arguments)
    try:
        allow_patterns = tuple(re.compile(value) for value in arguments.allow_pattern)
    except re.error as error:
        raise SystemExit(f"无效 --allow-pattern：{error}") from error
    if any(_is_overbroad_allow_pattern(pattern) for pattern in allow_patterns):
        raise SystemExit("--allow-pattern 不得匹配空字符串或批量覆盖不同类型的基础设施标识")
    issues = validate_bytes(
        arguments.path.read_bytes(),
        mode=arguments.mode,
        allow_patterns=allow_patterns,
        allow_passwords=arguments.allow_passwords,
        scope=arguments.scope,
    )
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    failed = errors > 0 or (arguments.strict and warnings > 0)
    if arguments.json:
        print(
            json.dumps(
                {
                    "path": str(arguments.path),
                    "mode": arguments.mode,
                    "allow_passwords": arguments.allow_passwords,
                    "scope": arguments.scope,
                    "valid": not failed,
                    "error_count": errors,
                    "warning_count": warnings,
                    "issues": [asdict(issue) for issue in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in issues:
            location = f":{issue.line}" if issue.line is not None else ""
            print(f"{issue.severity.upper()} {issue.code} {arguments.path}{location} {issue.message}")
        print(f"errors={errors} warnings={warnings} valid={str(not failed).lower()}")
    return 1 if failed else 0


def _missing_path_result(arguments: argparse.Namespace) -> int:
    message = f"文件不存在：{arguments.path}"
    if not arguments.json:
        raise SystemExit(message)
    issue = Issue("error", "unreadable-file", message)
    print(json.dumps({
        "path": str(arguments.path), "mode": arguments.mode,
        "allow_passwords": arguments.allow_passwords, "scope": arguments.scope,
        "valid": False, "error_count": 1, "warning_count": 0,
        "issues": [asdict(issue)],
    }, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
