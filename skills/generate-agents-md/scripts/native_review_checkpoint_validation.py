from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from implementation_agent_validation import HostAttestationVerifier, validate_native_spawn_record
from strict_json import loads as strict_json_loads


WRAPPER_FIELDS = {"current_checkpoint_locator", "current_checkpoint_sha256", "checkpoint"}
CHECKPOINT_FIELDS = {
    "schema_version", "workflow_id", "run_id", "round", "scope_sha256",
    "candidate_sha256", "code_version", "build_id", "input_sha256", "output_sha256",
    "completed_gates", "pending_defects", "next_action", "created_at",
    "previous_checkpoint_locator", "previous_checkpoint_sha256", "recovery_required",
    "recovery_receipt", "recovery_receipt_sha256",
}
REQUIRED_COMPLETED_GATES = {"solution-author", "black-box-reviewer", "coordinator-adjudication"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_checkpoint_chain(
    bundle: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    issues: list[Issue] = []
    chain = bundle.get("checkpoint_chain")
    candidates = bundle.get("candidates")
    if not isinstance(chain, list) or not chain:
        return [Issue("error", "missing-native-loop-checkpoint", "native review 必须保留非空 checkpoint chain")]
    if not isinstance(candidates, list) or len(chain) != len(candidates) or len(chain) > 6:
        issues.append(Issue("error", "invalid-native-loop-checkpoint-count", "每个候选轮次必须有且仅有一个 checkpoint"))
    previous_locator: str | None = None
    previous_sha: str | None = None
    previous_created: datetime | None = None
    for index, wrapper in enumerate(chain, start=1):
        candidate = candidates[index - 1] if isinstance(candidates, list) and index <= len(candidates) else None
        previous_created = _validate_checkpoint(
            wrapper, candidate, index, bundle, root, verifier,
            previous_locator, previous_sha, previous_created, issues,
        )
        if isinstance(wrapper, dict):
            previous_locator = _string(wrapper.get("current_checkpoint_locator"))
            previous_sha = _string(wrapper.get("current_checkpoint_sha256"))
    return issues


def _validate_checkpoint(
    wrapper: object, candidate: object, index: int, bundle: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None, previous_locator: str | None,
    previous_sha: str | None, previous_created: datetime | None, issues: list[Issue],
) -> datetime | None:
    if not isinstance(wrapper, dict) or set(wrapper) != WRAPPER_FIELDS:
        issues.append(Issue("error", "invalid-native-loop-checkpoint-fields", "checkpoint wrapper 必须封闭"))
        return previous_created
    checkpoint = wrapper.get("checkpoint")
    if not isinstance(checkpoint, dict) or set(checkpoint) != CHECKPOINT_FIELDS:
        issues.append(Issue("error", "invalid-native-loop-checkpoint-fields", "checkpoint 内容必须封闭"))
        return previous_created
    path = _hashed_file(
        wrapper.get("current_checkpoint_locator"), wrapper.get("current_checkpoint_sha256"), root, issues,
    )
    if path is not None:
        try:
            persisted = strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            persisted = None
        if persisted != checkpoint:
            issues.append(Issue("error", "stale-native-loop-checkpoint", "checkpoint locator 内容与 bundle 摘要不一致"))
    _validate_binding(checkpoint, candidate, index, bundle, previous_locator, previous_sha, issues)
    created = _parse_timestamp(checkpoint.get("created_at"), issues)
    if created is not None and previous_created is not None and created <= previous_created:
        issues.append(Issue("error", "nonmonotonic-native-loop-checkpoint", "checkpoint created_at 必须严格递增"))
    recovery_required = checkpoint.get("recovery_required")
    if type(recovery_required) is not bool:
        issues.append(Issue("error", "invalid-native-loop-recovery-state", "recovery_required 必须是布尔值"))
    if index > 1 and recovery_required is not True:
        issues.append(Issue("error", "missing-native-loop-recovery-receipt", "恢复轮次必须声明并证明 recovery"))
    if recovery_required is True:
        _validate_recovery_receipt(checkpoint, wrapper, bundle, root, verifier, issues)
    elif checkpoint.get("recovery_receipt") is not None or checkpoint.get("recovery_receipt_sha256") is not None:
        issues.append(Issue("error", "unexpected-native-loop-recovery-receipt", "未恢复 checkpoint 不得携带 recovery receipt"))
    return created or previous_created


def _validate_binding(
    checkpoint: dict[str, object], candidate: object, index: int,
    bundle: dict[str, object], previous_locator: str | None, previous_sha: str | None,
    issues: list[Issue],
) -> None:
    author = candidate.get("solution_author") if isinstance(candidate, dict) else None
    expected = {
        "schema_version": 1, "workflow_id": bundle.get("workflow_id"),
        "run_id": bundle.get("adjudicator_run_id"), "round": index,
        "scope_sha256": bundle.get("scope_sha256"),
        "candidate_sha256": candidate.get("candidate_sha256") if isinstance(candidate, dict) else None,
        "code_version": bundle.get("code_version"), "build_id": bundle.get("build_id"),
        "input_sha256": author.get("input_sha256") if isinstance(author, dict) else None,
        "output_sha256": candidate.get("candidate_sha256") if isinstance(candidate, dict) else None,
        "previous_checkpoint_locator": previous_locator,
        "previous_checkpoint_sha256": previous_sha,
    }
    if any(checkpoint.get(field) != value for field, value in expected.items()):
        issues.append(Issue("error", "stale-native-loop-checkpoint", "checkpoint 未绑定当前 workflow/run/round/candidate/code/build/链"))
    completed = checkpoint.get("completed_gates")
    if (not isinstance(completed, list) or any(type(item) is not str or not item.strip() for item in completed)
            or len(set(completed)) != len(completed) or not REQUIRED_COMPLETED_GATES <= set(completed)):
        issues.append(Issue("error", "invalid-native-loop-completed-gates", "checkpoint 缺少本轮完成门禁"))
    if not isinstance(checkpoint.get("pending_defects"), list):
        issues.append(Issue("error", "invalid-native-loop-pending-defects", "pending_defects 必须是数组"))
    if type(checkpoint.get("next_action")) is not str or not checkpoint.get("next_action", "").strip():
        issues.append(Issue("error", "missing-native-loop-next-action", "checkpoint 必须给出 next_action"))


def _validate_recovery_receipt(
    checkpoint: dict[str, object], wrapper: dict[str, object], bundle: dict[str, object],
    root: Path, verifier: HostAttestationVerifier | None, issues: list[Issue],
) -> None:
    if checkpoint.get("recovery_receipt") is None or checkpoint.get("recovery_receipt_sha256") is None:
        issues.append(Issue("error", "missing-native-loop-recovery-receipt", "恢复必须提供封闭 receipt；严格模式追加宿主证明"))
        return
    expected = {
        "schema_version": 1, "receipt_kind": "codex-native-recovery-result",
        "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol", "agent_id": bundle.get("adjudicator_agent_id"),
        "requested_reasoning_effort": "xhigh", "recorded_reasoning_effort": "xhigh",
        "run_id": bundle.get("adjudicator_run_id"), "role": "coordinator-adjudicator",
        "module": bundle.get("module"), "maintainer_title": "coordinator-adjudicator",
        "workflow_id": bundle.get("workflow_id"), "round": checkpoint.get("round"),
        "previous_checkpoint_locator": checkpoint.get("previous_checkpoint_locator"),
        "previous_checkpoint_sha256": checkpoint.get("previous_checkpoint_sha256"),
        "scope_sha256": checkpoint.get("scope_sha256"),
        "candidate_sha256": checkpoint.get("candidate_sha256"),
        "code_version": checkpoint.get("code_version"), "build_id": checkpoint.get("build_id"),
        "verdict": "resumed",
    }
    proxy = {
        "recovery_receipt": checkpoint.get("recovery_receipt"),
        "recovery_receipt_sha256": checkpoint.get("recovery_receipt_sha256"),
    }
    for item in validate_native_spawn_record(
        data=proxy, root=root, expected=expected, path_field="recovery_receipt",
        hash_field="recovery_receipt_sha256", code_prefix="native-loop-recovery",
        label="native loop 恢复", host_attestation_verifier=verifier,
        record_label="recovery result", invalid_code="invalid-native-loop-recovery-receipt",
    ):
        issues.append(Issue(item.severity, item.code, item.message))


def _hashed_file(path_value: object, hash_value: object, root: Path, issues: list[Issue]) -> Path | None:
    if type(path_value) is not str or type(hash_value) is not str:
        issues.append(Issue("error", "unsafe-native-loop-checkpoint-path", "checkpoint locator/hash 必须是字符串"))
        return None
    path = Path(path_value)
    if not path_value or path.is_absolute() or path.as_posix() != path_value or ".." in path.parts:
        issues.append(Issue("error", "unsafe-native-loop-checkpoint-path", "checkpoint 必须是规范项目相对路径"))
        return None
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            issues.append(Issue("error", "unsafe-native-loop-checkpoint-path", "checkpoint 路径不得经过符号链接"))
            return None
    if not current.is_file():
        issues.append(Issue("error", "missing-native-loop-checkpoint", f"checkpoint 不存在：{path_value}"))
        return None
    digest = hashlib.sha256(current.read_bytes()).hexdigest()
    if len(hash_value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in hash_value) or digest != hash_value.casefold():
        issues.append(Issue("error", "stale-native-loop-checkpoint", f"checkpoint SHA 失效：{path_value}"))
    return current


def _parse_timestamp(value: object, issues: list[Issue]) -> datetime | None:
    if type(value) is not str or not value.endswith("Z"):
        issues.append(Issue("error", "invalid-native-loop-checkpoint-time", "created_at 必须是 UTC RFC3339 时间"))
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        issues.append(Issue("error", "invalid-native-loop-checkpoint-time", "created_at 必须是 UTC RFC3339 时间"))
        return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None
