from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from strict_json import loads as strict_json_loads


TOP_FIELDS = {"schema_version", "baseline_version", "baseline_sha256", "questions", "gate_reruns"}
BASE_QUESTION_FIELDS = {
    "question_id", "impact_scope", "risk", "proposed_default", "safe_fallback",
    "answer_status", "delivery_disposition", "assumption", "owner", "review_due",
}
ANSWER_FIELDS = {
    "human_answer", "answer_evidence_locator", "answer_evidence_sha256",
    "pre_answer_baseline_version", "pre_answer_baseline_sha256",
}
RERUN_FIELDS = {
    "question_id", "baseline_version", "baseline_sha256", "affected_scope", "status",
    "receipt_locator", "receipt_sha256",
}
RISKS = {
    "small", "standard", "high-risk", "legal", "security",
    "irreversible-destruction", "missing-required-permission",
}
HostAttestationVerifier = Callable[[Path, dict[str, object], dict[str, object]], bool]


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_requirement_questions(path: Path, *, project_root: Path | None = None) -> list[Issue]:
    return _validate_requirement_questions_impl(path, project_root or path.parent, None)


def _test_only_validate_requirement_questions(
    path: Path, *, project_root: Path,
    _test_only_host_attestation_verifier: HostAttestationVerifier,
) -> list[Issue]:
    return _validate_requirement_questions_impl(
        path, project_root, _test_only_host_attestation_verifier,
    )


def _validate_requirement_questions_impl(
    path: Path, project_root: Path, verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        return [Issue("error", "invalid-question-list", str(error))]
    if not isinstance(data, dict) or set(data) != TOP_FIELDS:
        return [Issue("error", "invalid-question-list-fields", "疑问清单顶层字段必须精确匹配 schema")]
    issues: list[Issue] = []
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        issues.append(Issue("error", "invalid-question-schema-version", "schema_version 必须精确为整数 1"))
    baseline_version = data.get("baseline_version")
    baseline_sha = data.get("baseline_sha256")
    if not isinstance(baseline_version, str) or not baseline_version.strip():
        issues.append(Issue("error", "invalid-question-baseline", "baseline_version 不能为空"))
    if not isinstance(baseline_sha, str) or re.fullmatch(r"[0-9a-f]{64}", baseline_sha) is None:
        issues.append(Issue("error", "invalid-question-baseline", "baseline_sha256 必须是 64 位小写十六进制"))
    questions = data.get("questions")
    reruns = data.get("gate_reruns")
    if not isinstance(questions, list) or not isinstance(reruns, list):
        return issues + [Issue("error", "invalid-question-list", "questions 和 gate_reruns 必须是数组")]
    seen: set[str] = set()
    for question in questions:
        issues.extend(_question_issues(question, seen, project_root, baseline_version, baseline_sha))
    rerun_map = _rerun_map(reruns, issues)
    for question in questions:
        if isinstance(question, dict) and question.get("answer_status") == "ANSWERED":
            rerun = rerun_map.get(str(question.get("question_id")))
            if not _current_rerun(rerun, question, baseline_version, baseline_sha):
                issues.append(Issue(
                    "error", "answered-question-rerun-required",
                    "人工答案到达后必须更新当前需求/目标基线并完成全部受影响门禁重跑",
                ))
            elif not _verified_rerun(rerun, project_root, verifier):
                issues.append(Issue(
                    "error", "question-rerun-receipt-not-validated",
                    "门禁重跑必须通过本地封闭 receipt 校验；严格模式还必须通过宿主可信验证器",
                ))
    return _deduplicate(issues)


def _question_issues(
    value: object, seen: set[str], project_root: Path,
    baseline_version: object, baseline_sha: object,
) -> list[Issue]:
    if not isinstance(value, dict):
        return [Issue("error", "invalid-question-fields", "每条疑问必须包含且仅包含规定字段")]
    status = value.get("answer_status")
    expected_fields = BASE_QUESTION_FIELDS | (ANSWER_FIELDS if status == "ANSWERED" else set())
    if set(value) != expected_fields:
        return [Issue("error", "invalid-question-fields", "每条疑问必须包含且仅包含状态规定字段")]
    issues: list[Issue] = []
    question_id = value.get("question_id")
    if not isinstance(question_id, str) or re.fullmatch(r"Q-[0-9]{3,}", question_id) is None or question_id in seen:
        issues.append(Issue("error", "invalid-question-id", "question_id 必须唯一并使用 Q-数字"))
    else:
        seen.add(question_id)
    scope = value.get("impact_scope")
    if not _unique_strings(scope):
        issues.append(Issue("error", "invalid-question-impact-scope", "impact_scope 必须是非空唯一字符串数组"))
    risk = value.get("risk")
    if risk not in RISKS:
        issues.append(Issue("error", "invalid-question-risk", "risk 不在允许枚举中"))
    if status not in {"ANSWERED", "NOT_PROVIDED"}:
        issues.append(Issue("error", "invalid-question-answer-status", "answer_status 枚举非法"))
    if value.get("delivery_disposition") != "NON_BLOCKING_P2":
        issues.append(Issue(
            "error", "invalid-question-delivery-disposition",
            "疑问只能作为 NON_BLOCKING_P2 异步提交人工确认，不得阻塞交付",
        ))
    for field in ("proposed_default", "safe_fallback", "assumption", "owner"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            issues.append(Issue("error", "invalid-question-safe-default", f"{field} 不能为空"))
    if not _timezone_aware(value.get("review_due")):
        issues.append(Issue("error", "invalid-question-review-due", "review_due 必须是含时区 ISO-8601"))
    if status == "ANSWERED":
        issues.extend(_answered_question_issues(value, project_root, baseline_version, baseline_sha))
    return issues


def _answered_question_issues(
    value: dict[str, object], root: Path,
    baseline_version: object, baseline_sha: object,
) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(value.get("human_answer"), str) or not str(value["human_answer"]).strip():
        issues.append(Issue("error", "invalid-human-answer", "ANSWERED 必须包含非空人工答案"))
    pre_version = value.get("pre_answer_baseline_version")
    pre_sha = value.get("pre_answer_baseline_sha256")
    if not isinstance(pre_version, str) or not pre_version.strip() or not _sha(pre_sha):
        issues.append(Issue("error", "invalid-pre-answer-baseline", "ANSWERED 必须绑定回答前需求基线版本和 SHA-256"))
    if pre_version == baseline_version or pre_sha == baseline_sha:
        issues.append(Issue("error", "answered-question-baseline-not-updated", "回答后当前需求基线必须同时更新版本与 SHA-256"))
    evidence = _hashed_json(value.get("answer_evidence_locator"), value.get("answer_evidence_sha256"), root)
    expected = {
        "schema_version": 1, "evidence_kind": "human-requirement-answer",
        "question_id": value.get("question_id"), "human_answer": value.get("human_answer"),
        "pre_answer_baseline_version": pre_version, "pre_answer_baseline_sha256": pre_sha,
        "post_answer_baseline_version": baseline_version, "post_answer_baseline_sha256": baseline_sha,
    }
    if evidence is None:
        issues.append(Issue("error", "invalid-answer-evidence", "人工答案证据 locator/SHA 必须指向项目内封闭 JSON"))
    else:
        _, record = evidence
        if set(record) != set(expected) or any(record.get(key) != expected_value for key, expected_value in expected.items()):
            issues.append(Issue("error", "invalid-answer-evidence", "人工答案证据必须绑定 question、内容及回答前后基线"))
    return issues


def _rerun_map(values: list[object], issues: list[Issue]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in values:
        if not isinstance(value, dict) or set(value) != RERUN_FIELDS:
            issues.append(Issue("error", "invalid-question-rerun", "门禁重跑记录字段不完整或含未知字段"))
            continue
        question_id = value.get("question_id")
        if not isinstance(question_id, str) or question_id in result:
            issues.append(Issue("error", "invalid-question-rerun", "门禁重跑 question_id 必须唯一"))
            continue
        result[question_id] = value
    return result


def _current_rerun(
    rerun: dict[str, object] | None, question: dict[str, object],
    baseline_version: object, baseline_sha: object,
) -> bool:
    return bool(
        rerun and rerun.get("baseline_version") == baseline_version
        and rerun.get("baseline_sha256") == baseline_sha
        and rerun.get("status") == "COMPLETED"
        and _unique_strings(rerun.get("affected_scope"))
        and set(rerun["affected_scope"]) == set(question.get("impact_scope", []))
    )


def _verified_rerun(
    rerun: dict[str, object], root: Path,
    verifier: HostAttestationVerifier | None,
) -> bool:
    evidence = _hashed_json(rerun.get("receipt_locator"), rerun.get("receipt_sha256"), root)
    if evidence is None:
        return False
    path, record = evidence
    expected = {
        "schema_version": 1, "receipt_kind": "requirement-gate-rerun",
        "question_id": rerun.get("question_id"),
        "baseline_version": rerun.get("baseline_version"),
        "baseline_sha256": rerun.get("baseline_sha256"),
        "affected_scope": rerun.get("affected_scope"), "status": "COMPLETED",
    }
    if set(record) != set(expected) or any(record.get(key) != expected_value for key, expected_value in expected.items()):
        return False
    if verifier is None:
        return True
    try:
        return verifier(path, record, expected) is True
    except Exception:
        return False


def _hashed_json(path_value: object, hash_value: object, root: Path) -> tuple[Path, dict[str, object]] | None:
    if not isinstance(path_value, str) or not _sha(hash_value):
        return None
    relative = Path(path_value)
    if (not path_value or relative.is_absolute() or "\\" in path_value
            or path_value != relative.as_posix() or ".." in relative.parts):
        return None
    path = root.joinpath(relative)
    try:
        current = root
        if root.is_symlink():
            return None
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return None
        if not path.is_file() or path.resolve().relative_to(root.resolve()) is None:
            return None
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != hash_value:
            return None
        value = strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return (path, value) if isinstance(value, dict) else None


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _unique_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    ) and len(value) == len(set(value))


def _timezone_aware(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证非阻塞 P2 需求疑问、默认继续和答案到达后的门禁重跑")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--project-root", type=Path,
        help="证据 locator 的项目根目录；省略时沿用清单所在目录",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    issues = validate_requirement_questions(args.path, project_root=args.project_root)
    if args.json:
        print(json.dumps({"valid": not issues, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            print(f"{item.severity.upper()} {item.code} {item.message}")
        print(f"errors={len(issues)} valid={str(not issues).lower()}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
