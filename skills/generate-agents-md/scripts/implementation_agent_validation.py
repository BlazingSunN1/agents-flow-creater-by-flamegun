from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from strict_json import loads as strict_json_loads
from agents_dispatcher_policy_validation import module_ownership_mapping
from delivery_authority_binding import AUTHORITY_SHA256


HostAttestationVerifier = Callable[[Path, dict[str, object], dict[str, object]], bool]


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


@dataclass
class ReceiptReplayState:
    paths: set[str]
    inodes: set[tuple[int, int]]
    hashes: set[str]

    @classmethod
    def empty(cls) -> "ReceiptReplayState":
        return cls(set(), set(), set())

    def reused(self, relative: str, path: Path) -> bool:
        metadata = os.stat(path)
        inode = (metadata.st_dev, metadata.st_ino)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        duplicate = (
            relative in self.paths or inode in self.inodes or digest in self.hashes
        )
        self.paths.add(relative)
        self.inodes.add(inode)
        self.hashes.add(digest)
        return duplicate


def validate_implementation_agent(
    data: dict[str, object], context: dict[str, str], root: Path,
) -> list[Issue]:
    return _validate_implementation_agent_impl(data, context, root, None, None)


def _test_only_validate_implementation_agent(
    data: dict[str, object], context: dict[str, str], root: Path, *,
    _test_only_host_attestation_verifier: HostAttestationVerifier,
) -> list[Issue]:
    return _validate_implementation_agent_impl(
        data, context, root, _test_only_host_attestation_verifier, None,
    )


def _validate_implementation_agent_impl(
    data: dict[str, object], context: dict[str, str], root: Path,
    verifier: HostAttestationVerifier | None,
    receipt_replay_state: ReceiptReplayState | None,
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
    schema_version = data.get("schema_version", 1)
    expected = _implementation_expected(data, modules, schema_version)
    if schema_version == 2:
        issues.extend(validate_v2_binding_source(
            data, root, require_active_lease=True, allow_empty_owned_paths=False,
            code_prefix="implementation",
        ))
        expected.update(_v2_expected_bindings(
            data, read_only=False, include_active_lease=True,
        ))
        issues.extend(_validate_v2_project_binding(data, context, root, modules))
    elif schema_version != 1:
        issues.append(Issue(
            "error", "invalid-implementation-runtime-binding",
            "实现 Agent receipt schema_version 必须是整数 1 或 2",
        ))
    issues.extend(validate_native_spawn_record(
        data=data, root=root, expected=expected,
        path_field="implementation_spawn_receipt",
        hash_field="implementation_spawn_receipt_sha256",
        code_prefix="implementation", label="维护 Agent",
        host_attestation_verifier=verifier,
        receipt_replay_state=receipt_replay_state,
    ))
    return issues


def _implementation_expected(
    data: dict[str, object], modules: list[str], schema_version: object,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "receipt_kind": "codex-native-spawn-result",
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "recorded_reasoning_effort": "high",
        "agent_id": data.get("implementation_agent_id"),
        "run_id": data.get("implementation_run_id"), "role": "module-maintainer",
        "module": modules[0] if len(modules) == 1 else None,
        "maintainer_title": data.get("implementation_agent_title"),
    }


def validate_native_spawn_record(
    *, data: dict[str, object], root: Path, expected: dict[str, object],
    path_field: str, hash_field: str, code_prefix: str, label: str,
    host_attestation_verifier: HostAttestationVerifier | None,
    record_label: str = "spawn record",
    invalid_code: str | None = None,
    receipt_replay_state: ReceiptReplayState | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    invalid_receipt = invalid_code or f"invalid-{code_prefix}-spawn-receipt"
    if expected.get("schema_version") == 2 and not _lower_sha256(data.get(hash_field)):
        issues.append(Issue("error", f"invalid-{code_prefix}-receipt-sha256",
                            f"{label} schema-v2 receipt SHA-256 必须是 64 位小写十六进制"))
    receipt = _hashed_project_file(data.get(path_field), data.get(hash_field), root, issues)
    value: object = None
    if receipt is not None:
        try:
            value = strict_json_loads(receipt.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            issues.append(Issue("error", invalid_receipt, f"{label} {record_label} 必须是无重复键 JSON"))
    replayed = False
    if receipt is not None and receipt_replay_state is not None:
        replayed = receipt_replay_state.reused(str(data.get(path_field)), receipt)
        if replayed:
            issues.append(Issue("error", "reused-native-receipt",
                                f"{label} receipt 路径、inode 或内容哈希不得复用"))
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
    local_valid = receipt is not None and valid_record and not replayed and not issues
    validated = local_valid and host_attestation_verifier is None
    if local_valid and host_attestation_verifier is not None:
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


def validate_v2_binding_source(
    data: dict[str, object], root: Path, *, require_active_lease: bool,
    allow_empty_owned_paths: bool, code_prefix: str,
) -> list[Issue]:
    issues: list[Issue] = []
    for field in ("authority_matrix_sha256", "baseline_sha256", "candidate_sha256"):
        if not _lower_sha256(data.get(field)):
            issues.append(Issue(
                "error", f"invalid-{code_prefix}-runtime-binding",
                f"schema-v2 {field} 必须是 64 位小写 SHA-256",
            ))
    for field in ("code_version", "build_id"):
        if type(data.get(field)) is not str or not str(data[field]).strip():
            issues.append(Issue(
                "error", f"invalid-{code_prefix}-runtime-binding",
                f"schema-v2 {field} 必须是非空字符串",
            ))
    owned_paths = data.get("owned_paths")
    if not _valid_owned_paths(owned_paths, allow_empty=allow_empty_owned_paths):
        issues.append(Issue(
            "error", f"invalid-{code_prefix}-runtime-binding",
            "schema-v2 owned_paths 必须是按所有权行顺序排列的规范项目相对路径唯一数组",
        ))
    lease = data.get("active_write_lease")
    if require_active_lease:
        if not _valid_active_write_lease(lease):
            issues.append(Issue(
                "error", f"invalid-{code_prefix}-runtime-binding",
                "schema-v2 active_write_lease 必须精确包含 lease_id/path/sha256",
            ))
        else:
            assert isinstance(lease, dict)
            lease_issues: list[Issue] = []
            lease_path = _hashed_project_file(
                lease["path"], lease["sha256"], root, lease_issues,
            )
            if lease_path is None or lease_issues:
                issues.append(Issue(
                    "error", f"invalid-{code_prefix}-runtime-binding",
                    "schema-v2 active_write_lease locator/sha256 未绑定当前项目文件",
                ))
    elif "active_write_lease" in data:
        issues.append(Issue(
            "error", f"invalid-{code_prefix}-runtime-binding",
            "只读 schema-v2 角色不得携带 active_write_lease",
        ))
    return issues


def _v2_expected_bindings(
    data: dict[str, object], *, read_only: bool, include_active_lease: bool,
) -> dict[str, object]:
    result = {
        "read_only": read_only,
        "authority_matrix_sha256": data.get("authority_matrix_sha256"),
        "owned_paths": data.get("owned_paths"),
        "baseline_sha256": data.get("baseline_sha256"),
        "code_version": data.get("code_version"),
        "build_id": data.get("build_id"),
        "candidate_sha256": data.get("candidate_sha256"),
    }
    if include_active_lease:
        result["active_write_lease"] = data.get("active_write_lease")
    return result


def _validate_v2_project_binding(
    data: dict[str, object], context: dict[str, str], root: Path,
    modules: list[str],
) -> list[Issue]:
    issues: list[Issue] = []
    agents_path = root / "AGENTS.md"
    try:
        agents_text = agents_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [Issue(
            "error", "invalid-implementation-runtime-binding",
            "schema-v2 必须绑定可读的项目根 AGENTS.md",
        )]
    sha_match = re.search(
        r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$",
        agents_text, re.MULTILINE,
    )
    ownership = module_ownership_mapping(agents_text)
    module = modules[0] if len(modules) == 1 else ""
    row = ownership.get(module)
    if (sha_match is None or sha_match.group(1) != AUTHORITY_SHA256
            or data.get("authority_matrix_sha256") != AUTHORITY_SHA256):
        issues.append(Issue(
            "error", "invalid-implementation-runtime-binding",
            "schema-v2 authority_matrix_sha256 必须匹配当前 canonical 根 AGENTS",
        ))
    if (row is None or data.get("owned_paths") != list(row[0])
            or data.get("implementation_agent_title") != row[1]):
        issues.append(Issue(
            "error", "invalid-implementation-runtime-binding",
            "schema-v2 owned_paths/title 必须精确匹配当前模块所有权行及顺序",
        ))
    return issues


def _lower_sha256(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_relative_path(value: object) -> bool:
    if type(value) is not str:
        return False
    path = Path(value)
    return bool(
        value and not path.is_absolute() and "\\" not in value
        and value == path.as_posix() and ".." not in path.parts
    )


def _valid_owned_paths(value: object, *, allow_empty: bool) -> bool:
    return bool(
        isinstance(value, list)
        and (allow_empty or value)
        and len(value) == len(set(value))
        and all(_canonical_relative_path(item) for item in value)
    )


def _valid_active_write_lease(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"lease_id", "path", "sha256"}
        and type(value.get("lease_id")) is str
        and str(value["lease_id"]).strip()
        and _canonical_relative_path(value.get("path"))
        and _lower_sha256(value.get("sha256"))
    )


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
