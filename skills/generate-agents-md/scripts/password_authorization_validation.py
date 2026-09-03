from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from agents_policy_common import (
    Issue,
    PASSWORD_AUTHORIZATION_HEADING_RE,
    PLACEHOLDER_RE,
    URI_CREDENTIAL_DETAIL_RE,
    extract_heading_section,
)


PASSWORD_ASSIGNMENT_RE = re.compile(
    r"\b(?:password|passwd)\b\s*[:=]\s*"
    r"(`[^`\r\n]+`|\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s#`]+)",
    re.IGNORECASE,
)
ENVIRONMENT_REFERENCE_RE = re.compile(
    r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)"
)
INVALID_BOUNDARY_RE = re.compile(
    r"^(?:tbd|todo|later|unknown|everyone|anyone|all|待定|以后|所有人|任意)$",
    re.IGNORECASE,
)
DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class EndpointScope:
    scheme: str
    host: str
    port: int | None
    path: str


def plaintext_password_present(text: str) -> bool:
    if any(
        not _is_placeholder_secret(match.group("password"))
        for match in URI_CREDENTIAL_DETAIL_RE.finditer(text)
    ):
        return True
    return any(
        not _is_placeholder_secret(match.group(1))
        for match in PASSWORD_ASSIGNMENT_RE.finditer(text)
    )


def validate_password_authorization(text: str) -> list[Issue]:
    section = extract_heading_section(text, PASSWORD_AUTHORIZATION_HEADING_RE)
    if section is None:
        return [Issue(
            "error",
            "missing-password-authorization",
            "项目文件记录明文密码时必须包含 Password Authorization 章节",
        )]
    fields, duplicates = _authorization_fields(section)
    if duplicates:
        return [Issue(
            "error",
            "duplicate-password-authorization-field",
            f"密码授权字段不得重复：{', '.join(sorted(set(duplicates)))}",
        )]
    boundary_issue = _password_boundary_issue(fields)
    if boundary_issue:
        return [boundary_issue]
    return _password_endpoint_issues(text, fields)


def _authorization_fields(section: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    duplicates: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^-\s+([^:：]+)[:：]\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.group(1).strip().casefold(), match.group(2).strip()
        if key in fields:
            duplicates.append(key)
        else:
            fields[key] = value
    return fields, duplicates


def _password_boundary_issue(fields: dict[str, str]) -> Issue | None:
    access_boundary = fields.get("access boundary", fields.get("访问边界", "")).strip()
    if not access_boundary:
        return Issue(
            "error",
            "invalid-password-authorization",
            "密码授权缺少非空边界字段：access boundary",
        )
    supplied_values = [value for value in fields.values() if value.strip()]
    if any(
        PLACEHOLDER_RE.search(value) or INVALID_BOUNDARY_RE.fullmatch(value.strip())
        for value in supplied_values
    ):
        return Issue(
            "error",
            "invalid-password-authorization",
            "密码授权字段不得使用占位符、待定值或无限制访问边界",
        )
    return None


def _password_endpoint_issues(text: str, fields: dict[str, str]) -> list[Issue]:
    actual = [
        _endpoint_scope(match.group("uri"), allow_userinfo=True)
        for match in URI_CREDENTIAL_DETAIL_RE.finditer(text)
        if not _is_placeholder_secret(match.group("password"))
    ]
    if not actual:
        return []
    if any(scope is None for scope in actual):
        return [Issue(
            "error",
            "invalid-password-uri-endpoint",
            "URI 内嵌密码端点格式无效或路径包含不安全编码",
        )]
    raw_endpoints = fields.get("authorized endpoints", fields.get("授权端点", ""))
    raw_items = [item.strip() for item in raw_endpoints.split(",") if item.strip()]
    authorized = [_endpoint_scope(item, allow_userinfo=False) for item in raw_items]
    if not raw_items or any(scope is None for scope in authorized):
        return [Issue(
            "error",
            "invalid-authorized-password-endpoint",
            "URI 内嵌密码必须提供不含凭据的有效 Authorized endpoints",
        )]
    allowed_scopes = [scope for scope in authorized if scope is not None]
    actual_scopes = [scope for scope in actual if scope is not None]
    if any(not any(_scope_contains(rule, endpoint) for rule in allowed_scopes) for endpoint in actual_scopes):
        return [Issue(
            "error",
            "unauthorized-password-endpoint",
            "URI 内嵌密码端点必须匹配已授权的协议、主机、有效端口和路径边界",
        )]
    return []


def _endpoint_scope(raw_value: str, *, allow_userinfo: bool) -> EndpointScope | None:
    value = raw_value.strip().strip("`'\".,;")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    if not scheme or not host:
        return None
    if not allow_userinfo and (parsed.query or parsed.fragment):
        return None
    if not allow_userinfo and (parsed.username is not None or parsed.password is not None):
        return None
    if "\\" in parsed.path or re.search(r"%(?:2e|2f|5c)", parsed.path, re.IGNORECASE):
        return None
    effective_port = port if port is not None else DEFAULT_PORTS.get(scheme)
    path = posixpath.normpath(parsed.path or "/")
    if not path.startswith("/"):
        path = f"/{path}"
    return EndpointScope(scheme, host.casefold(), effective_port, path)


def _scope_contains(rule: EndpointScope, endpoint: EndpointScope) -> bool:
    if rule.scheme != endpoint.scheme:
        return False
    if (rule.host, rule.port) != (endpoint.host, endpoint.port):
        return False
    return rule.path == "/" or endpoint.path == rule.path or endpoint.path.startswith(f"{rule.path}/")


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip("\"'`")
    return bool(
        PLACEHOLDER_RE.fullmatch(normalized)
        or ENVIRONMENT_REFERENCE_RE.fullmatch(normalized)
    ) or normalized.upper() in {"REDACTED", "REMOVED", "***"}
