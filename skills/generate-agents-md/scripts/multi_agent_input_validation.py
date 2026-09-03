from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from implementation_agent_validation import HostAttestationVerifier
from validate_requirement_questions import _validate_requirement_questions_impl


SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_gate_input(
    path: Path, role: str, gate: dict[str, object], evidence: dict[str, object],
    context: dict[str, str], allowed_paths: set[str], root: Path,
    verifier: HostAttestationVerifier | None,
    expected_requirement_questions_locator: str | None,
    expected_requirement_questions_sha256: str | None,
) -> list[Issue]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return [Issue("error", "invalid-agent-input", f"{role} 输入必须是无重复键的结构化 JSON")]
    requirement_ids = sorted(item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip())
    expected = {
        "schema_version": 1, "role": role, "run_id": gate.get("run_id"),
        "baseline_version": evidence.get("baseline_version"),
        "baseline_sha256": evidence.get("baseline_sha256"),
        "requirement_ids": requirement_ids,
        "includes_full_chat": False, "includes_other_agent_reasoning": False,
        "includes_implementation_self_report": False,
    }
    required_keys = {
        *expected, "artifacts", "requirement_questions_locator", "requirement_questions_sha256",
    }
    if not isinstance(data, dict) or set(data) != required_keys:
        return [Issue("error", "invalid-agent-input", f"{role} 输入结构不完整或含未知字段")]
    issues: list[Issue] = []
    artifacts = data.get("artifacts")
    strings = (
        "role", "run_id", "baseline_version", "baseline_sha256",
        "requirement_questions_locator", "requirement_questions_sha256",
    )
    if (type(data.get("schema_version")) is not int
            or any(type(data.get(field)) is not str for field in strings)
            or type(data.get("requirement_ids")) is not list
            or any(type(data.get(field)) is not bool for field in (
                "includes_full_chat", "includes_other_agent_reasoning",
                "includes_implementation_self_report",
            ))
            or not isinstance(artifacts, list) or not artifacts):
        return [Issue("error", "invalid-agent-input", f"{role} 输入字段类型不合法")]
    if any(data.get(key) != value for key, value in expected.items()):
        issues.append(Issue("error", "stale-agent-input", f"{role} 输入未绑定当前角色、run、基线或需求"))
    if not _valid_input_artifacts(artifacts, allowed_paths, root):
        issues.append(Issue("error", "invalid-agent-input-paths", f"{role} 输入工件必须精确覆盖角色所需路径并绑定当前 SHA-256"))
    issues.extend(_requirement_question_issues(
        data, evidence, root, verifier, expected_requirement_questions_locator,
        expected_requirement_questions_sha256,
    ))
    return issues


def _requirement_question_issues(
    data: dict[str, object], evidence: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
    expected_locator: str | None, expected_sha256: str | None,
) -> list[Issue]:
    if type(expected_locator) is not str or type(expected_sha256) is not str or SHA256_RE.fullmatch(expected_sha256) is None:
        return [Issue("error", "missing-canonical-requirement-questions", "缺少可信调用方提供的 canonical Requirement Questions locator/SHA")]
    if (data.get("requirement_questions_locator") != expected_locator
            or str(data.get("requirement_questions_sha256", "")).casefold() != expected_sha256.casefold()):
        return [Issue("error", "noncanonical-requirement-questions", "gate input 未精确绑定 canonical Requirement Questions locator/SHA")]
    path = _hashed_project_file(
        data.get("requirement_questions_locator"), data.get("requirement_questions_sha256"), root,
    )
    if path is None:
        return [Issue("error", "stale-requirement-questions", "Requirement Questions locator/SHA 缺失或漂移")]
    issues = [Issue(item.severity, f"questions-{item.code}", item.message) for item in
              _validate_requirement_questions_impl(path, root, verifier)]
    try:
        questions = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return issues + [Issue("error", "invalid-requirement-questions", "Requirement Questions 必须是封闭 JSON")]
    if (not isinstance(questions, dict)
            or questions.get("baseline_version") != evidence.get("baseline_version")
            or str(questions.get("baseline_sha256", "")).casefold()
            != str(evidence.get("baseline_sha256", "")).casefold()):
        issues.append(Issue("error", "stale-requirement-questions-baseline", "Requirement Questions 未绑定当前 requirement baseline"))
    return issues


def _valid_input_artifacts(artifacts: list[object], allowed_paths: set[str], root: Path) -> bool:
    paths: list[str] = []
    identities: set[tuple[int, int]] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            return False
        raw_path, expected = artifact.get("path"), artifact.get("sha256")
        if type(raw_path) is not str or type(expected) is not str:
            return False
        current = _hashed_project_file(raw_path, expected, root)
        if current is None:
            return False
        identity = (current.stat().st_dev, current.stat().st_ino)
        if identity in identities:
            return False
        paths.append(raw_path)
        identities.add(identity)
    if len(paths) != len(set(paths)) or set(paths) - allowed_paths:
        return False
    if allowed_paths - set(paths):
        return False
    return True


def _hashed_project_file(path_value: object, hash_value: object, root: Path) -> Path | None:
    if type(path_value) is not str or type(hash_value) is not str or SHA256_RE.fullmatch(hash_value) is None:
        return None
    relative = Path(path_value)
    if (not path_value or relative.is_absolute() or "\\" in path_value
            or path_value != relative.as_posix() or ".." in relative.parts):
        return None
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None
    if not current.is_file():
        return None
    if hashlib.sha256(current.read_bytes()).hexdigest() != hash_value.casefold():
        return None
    return current


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-key")
        result[key] = value
    return result
