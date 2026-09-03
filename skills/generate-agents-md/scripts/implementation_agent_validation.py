from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from strict_json import loads as strict_json_loads


HostAttestationVerifier = Callable[[Path, dict[str, object], dict[str, object]], bool]


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_implementation_agent(
    data: dict[str, object], context: dict[str, str], root: Path,
) -> list[Issue]:
    return _validate_implementation_agent_impl(data, context, root, None)


def _test_only_validate_implementation_agent(
    data: dict[str, object], context: dict[str, str], root: Path, *,
    _test_only_host_attestation_verifier: HostAttestationVerifier,
) -> list[Issue]:
    return _validate_implementation_agent_impl(
        data, context, root, _test_only_host_attestation_verifier,
    )


def _validate_implementation_agent_impl(
    data: dict[str, object], context: dict[str, str], root: Path,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    issues: list[Issue] = []
    if (data.get("implementation_agent_provider") != "codex-native-agent"
            or data.get("implementation_agent_model") != "gpt-5.6-sol"):
        issues.append(Issue(
            "error", "invalid-implementation-agent",
            "模块长期维护实现 Agent 必须声明并绑定为 Codex 原生 gpt-5.6-sol",
        ))
    if data.get("implementation_agent_reasoning_effort") != "high":
        issues.append(Issue("error", "invalid-implementation-agent-effort",
                            "模块长期维护实现 Agent 必须使用 reasoning_effort=high"))
    modules = [item.strip().casefold() for item in context.get("Modules", "").split(",") if item.strip()]
    expected = {
        "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "recorded_reasoning_effort": "high",
        "agent_id": data.get("implementation_agent_id"),
        "run_id": data.get("implementation_run_id"), "role": "module-maintainer",
        "module": modules[0] if len(modules) == 1 else None,
        "maintainer_title": data.get("implementation_agent_title"),
    }
    issues.extend(validate_native_spawn_record(
        data=data, root=root, expected=expected,
        path_field="implementation_spawn_receipt",
        hash_field="implementation_spawn_receipt_sha256",
        code_prefix="implementation", label="维护 Agent",
        host_attestation_verifier=verifier,
    ))
    return issues


def validate_native_spawn_record(
    *, data: dict[str, object], root: Path, expected: dict[str, object],
    path_field: str, hash_field: str, code_prefix: str, label: str,
    host_attestation_verifier: HostAttestationVerifier | None,
    record_label: str = "spawn record",
    invalid_code: str | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    invalid_receipt = invalid_code or f"invalid-{code_prefix}-spawn-receipt"
    receipt = _hashed_project_file(data.get(path_field), data.get(hash_field), root, issues)
    value: object = None
    if receipt is not None:
        try:
            value = strict_json_loads(receipt.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            issues.append(Issue("error", invalid_receipt, f"{label} {record_label} 必须是无重复键 JSON"))
    valid_record = (
        isinstance(value, dict) and set(value) == set(expected)
        and type(value.get("schema_version")) is int
        and all(value.get(field) == expected_value for field, expected_value in expected.items())
    )
    if receipt is not None and value is not None and not valid_record:
        issues.append(Issue(
            "error", invalid_receipt,
            f"{label} 封闭 receipt 字段必须精确绑定声明身份与候选输出",
        ))
    validated = receipt is not None and valid_record and host_attestation_verifier is None
    if receipt is not None and valid_record and host_attestation_verifier is not None:
        try:
            validated = host_attestation_verifier(receipt, value, expected)
        except Exception:
            validated = False
    if not validated:
        issues.append(Issue(
            "error", f"{code_prefix}-receipt-not-validated",
            f"{label} {record_label} 未通过本地封闭 receipt 校验，或未通过已启用的严格宿主校验器",
        ))
    return issues


def _hashed_project_file(
    path_value: object, hash_value: object, root: Path, issues: list[Issue],
) -> Path | None:
    if type(path_value) is not str or type(hash_value) is not str:
        issues.append(Issue("error", "unsafe-agent-artifact-path", "原生 Agent receipt 路径和哈希必须是字符串"))
        return None
    candidate = Path(path_value)
    if (not path_value or candidate.is_absolute() or "\\" in path_value
            or path_value != candidate.as_posix() or ".." in candidate.parts):
        issues.append(Issue("error", "unsafe-agent-artifact-path", "原生 Agent receipt 必须是规范项目相对路径"))
        return None
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            issues.append(Issue("error", "unsafe-agent-artifact-path", "原生 Agent receipt 路径不得经过符号链接"))
            return None
    if not current.is_file():
        issues.append(Issue("error", "missing-agent-artifact", f"原生 Agent receipt 不存在：{path_value}"))
        return None
    expected = hash_value.casefold()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected) or hashlib.sha256(current.read_bytes()).hexdigest() != expected:
        issues.append(Issue("error", "stale-agent-artifact", f"原生 Agent receipt 哈希已失效：{path_value}"))
    return current
