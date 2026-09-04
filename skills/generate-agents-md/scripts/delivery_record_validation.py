from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents_policy_common import (
    AUTOMATED_REVIEW_HEADING_RE,
    DEVELOPMENT_PLAN_HEADING_RE,
    MODULAR_LOG_HEADING_RE,
    extract_heading_section,
)
from delivery_record_io import (
    _has_symlink_component,
    _read_record,
    _record_fields,
    _relative_path,
    split_record_paths,
    _validate_record,
)
from delivery_record_paths import (
    AUTOMATED_REVIEW_EVIDENCE_PATH,
    DEVELOPMENT_PLAN_PATH,
    MODULE_EXECUTION_LOG_TEMPLATE,
    PROGRESS_RECORD_PATH,
    STABLE_ID_RE,
    context_record_path as _context_record_path,
    declared_path as _declared_path,
    modules as _modules,
    normalize_template as _normalize_template,
)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    source: str


SWIMLANE_GATE_IDS = frozenset({"swimlane_evidence", "swimlane_freshness"})


def validate_declared_records(
    agents_path: Path, trace: dict[str, str], context: dict[str, str], root: Path,
    stage: str, multi_agent_path: Path, swimlane_path: Path | None,
    frontend_path: Path | None, command_manifest_path: Path, context_path: Path,
    planned_command_ids: set[str] | None,
) -> list[Issue]:
    try:
        text = agents_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [Issue("error", "bundle-declared-record-unreadable", str(error), str(agents_path))]
    issues = _validate_plan_progress(text, trace, context, root, stage)
    evidence_paths = {
        "Independent review evidence": _relative_path(multi_agent_path, root),
    }
    if _swimlane_evidence_required(planned_command_ids):
        evidence_paths["Swimlane evidence"] = _relative_path(swimlane_path, root)
    if frontend_path is not None:
        evidence_paths["Frontend evidence"] = _relative_path(frontend_path, root)
    module_paths, module_issues = _validate_module_records(
        text, trace, context, context_path, root, stage, evidence_paths, swimlane_path,
        planned_command_ids,
    )
    issues.extend(module_issues)
    issues.extend(_validate_review_record(
        text, context, root, command_manifest_path, planned_command_ids,
    ))
    issues.extend(_validate_progress_index(text, context, root, stage, module_paths))
    issues.extend(_record_alias_issues(text, context, module_paths, root))
    return issues


def _validate_plan_progress(
    text: str, trace: dict[str, str], context: dict[str, str], root: Path, stage: str,
) -> list[Issue]:
    section = extract_heading_section(text, DEVELOPMENT_PLAN_HEADING_RE) or ""
    plan = _declared_path(section, DEVELOPMENT_PLAN_PATH)
    progress = _declared_path(section, PROGRESS_RECORD_PATH)
    progress = _context_record_path(progress, context)
    issues = _validate_record(
        plan, root, "development-plan",
        {"Baseline version": trace.get("Baseline version", ""),
         "Baseline SHA-256": trace.get("Baseline SHA-256", "")},
        ("Objective", "Scope", "Ordered steps", "Verification criteria", "Known risks"),
    )
    required = ("Status",)
    statuses = {"pending", "in_progress", "blocked"}
    if stage == "completion":
        required = ("Completion date", "Delivered result", "Validation performed", "Remaining work", "Status")
        statuses = {"completed"}
    issues.extend(_validate_record(
        progress, root, "progress-record",
        {"Run ID": context.get("Run ID", ""), "Code version": context.get("Code version", "")},
        required, statuses, "Remaining work" if stage == "completion" else None,
    ))
    return issues


def _validate_module_records(
    text: str, trace: dict[str, str], context: dict[str, str], context_path: Path,
    root: Path, stage: str,
    evidence_paths: dict[str, str], swimlane_path: Path | None,
    planned_command_ids: set[str] | None,
) -> tuple[dict[str, tuple[str, str]], list[Issue]]:
    section = extract_heading_section(text, MODULAR_LOG_HEADING_RE) or ""
    template = _declared_path(section, MODULE_EXECUTION_LOG_TEMPLATE)
    raw_modules = [item.strip() for item in context.get("Modules", "").split(",") if item.strip()]
    if not raw_modules or any(not STABLE_ID_RE.fullmatch(item) for item in raw_modules):
        return {}, [Issue("error", "bundle-execution-run-unsafe-module", "Module 不是安全的单段标识符", "delivery-bundle")]
    modules = _modules(context)
    if template is None or "<module>" not in template or "<run_id>" not in template:
        return {}, [Issue("error", "bundle-execution-run-path-unresolved", "AGENTS 模块日志模板不可解析", "delivery-bundle")]
    run_id = context.get("Run ID", "")
    if not STABLE_ID_RE.fullmatch(run_id):
        return {}, [Issue("error", "bundle-execution-run-unsafe-id", "Run ID 不是安全的单段标识符", "delivery-bundle")]
    statuses = {"completed"} if stage == "completion" else {"pending", "in_progress", "blocked"}
    paths: dict[str, tuple[str, str]] = {}
    issues: list[Issue] = []
    for module in modules:
        run_path = _normalize_template(template, module, run_id)
        latest_path = str(Path(run_path).parent / "latest.md")
        paths[module] = (run_path, latest_path)
        issues.extend(_module_record_issues(
            text, trace, context, context_path, root, stage, module, run_path, latest_path,
            evidence_paths, swimlane_path, statuses,
            planned_command_ids,
        ))
    return paths, issues


def _module_record_issues(
    text: str, trace: dict[str, str], context: dict[str, str], context_path: Path,
    root: Path, stage: str, module: str,
    run_path: str, latest_path: str, evidence_paths: dict[str, str],
    swimlane_path: Path | None, statuses: set[str],
    planned_command_ids: set[str] | None,
) -> list[Issue]:
    expected = _module_run_expected(
        text, trace, context, context_path, root, module, evidence_paths,
    )
    required_fields = ["Context cache key", "Baseline version and SHA-256", "Build ID and acceptance environment",
                       "Context workset manifest and reused evidence fingerprints", "Risk level and reason",
                       "Delivered result", "Verification evidence", "Remaining risks", "Status"]
    if _swimlane_evidence_required(planned_command_ids):
        required_fields.append("Swimlane diagrams and validated evidence")
    issues = _validate_record(run_path, root, "execution-run", expected, tuple(required_fields),
                              statuses, "Remaining risks" if stage == "completion" else None)
    verification_paths = {
        value for key, value in evidence_paths.items()
        if key in {"Swimlane evidence", "Frontend evidence"} and value
    }
    required_paths = {"Verification evidence": verification_paths} if verification_paths else {}
    if _swimlane_evidence_required(planned_command_ids):
        required_paths["Swimlane diagrams and validated evidence"] = {
            evidence_paths.get("Swimlane evidence", ""), *_swimlane_diagram_paths(swimlane_path),
        }
    if not _record_paths_include(run_path, root, required_paths):
        issues.append(Issue("error", "bundle-execution-run-evidence-stale", "模块 run 未绑定当前验证和泳道路径", run_path))
    if stage != "completion":
        return issues
    latest_expected = {"Module": module, "Run ID": context.get("Run ID", ""),
                       "Code version": context.get("Code version", ""), "Status": "completed",
                       "Record": run_path}
    latest_required = ["Delivered result", "Verification evidence", "Remaining risks"]
    if _swimlane_evidence_required(planned_command_ids):
        latest_expected["Swimlane evidence"] = evidence_paths.get("Swimlane evidence", "")
        latest_required.append("Swimlane evidence")
    issues.extend(_validate_record(
        latest_path, root, "module-latest",
        latest_expected, tuple(latest_required),
        {"completed"}, "Remaining risks",
    ))
    latest_verification = {
        value for key, value in evidence_paths.items()
        if key in {"Swimlane evidence", "Frontend evidence"} and value
    }
    if not _record_paths_include(latest_path, root, {"Verification evidence": latest_verification}):
        issues.append(Issue("error", "bundle-module-latest-evidence-stale", "latest 未绑定当前验证证据", latest_path))
    return issues


def _module_run_expected(
    text: str, trace: dict[str, str], context: dict[str, str], context_path: Path,
    root: Path, module: str, evidence_paths: dict[str, str],
) -> dict[str, str]:
    return {
        "Run ID": context.get("Run ID", ""), "Module": module,
        "Code version": context.get("Code version", ""),
        "Context cache key": context.get("Evidence cache key", ""),
        "Traceability IDs": _module_requirement_ids(context, module),
        "Changed files": _module_changed_files(context, module),
        "Baseline version and SHA-256": f'{trace.get("Baseline version", "")} / {trace.get("Baseline SHA-256", "")}',
        "Build ID and acceptance environment": f'{trace.get("Build ID", "")} / {trace.get("Acceptance environment", "")}',
        "Context workset manifest and reused evidence fingerprints": (
            f'{_relative_path(context_path, root)} / {context.get("Evidence cache key", "")}'
        ),
        "Risk level and reason": context.get("Risk / expansion reason", ""),
        "Automated review evidence": _review_path(text, context), **evidence_paths,
    }


def _module_changed_files(context: dict[str, str], module: str) -> str:
    for item in context.get("Module changed files", "").split(";"):
        key, separator, paths = item.strip().partition("=")
        if separator and key.strip() == module:
            return ", ".join(path.strip() for path in paths.split(",") if path.strip())
    return ""


def _module_requirement_ids(context: dict[str, str], module: str) -> str:
    for item in context.get("_Module requirement IDs", "").split(";"):
        key, separator, requirement_ids = item.strip().partition("=")
        if separator and key.strip() == module:
            return ", ".join(value.strip() for value in requirement_ids.split(",") if value.strip())
    return ""


def _validate_review_record(
    text: str, context: dict[str, str], root: Path, command_manifest_path: Path,
    planned_command_ids: set[str] | None,
) -> list[Issue]:
    path = _review_path(text, context)
    issues = _validate_record(
        path, root, "automated-review",
        {"Run ID": context.get("Run ID", ""), "Code version": context.get("Code version", ""),
         "Code fingerprint": context.get("Code fingerprint", ""),
         "Command manifest fingerprint": context.get("Command manifest fingerprint", ""),
         "Changed files": context.get("Changed files", "")},
        ("Code fingerprint", "Command manifest fingerprint", "Review trigger", "Human trigger reference",
         "Scope", "Review command ID", "Review command argv SHA-256", "Review exit code",
         "Review evidence path", "Review evidence SHA-256", "Findings",
         "Rerun command IDs", "Rerun exit codes", "Verdict"),
        {"pass"}, "Findings",
    )
    if issues:
        return issues
    _, payload = _read_record(path, root, "automated-review")
    fields, _, _, _ = _record_fields(payload)
    if (not _review_scope_valid(fields, planned_command_ids) or not _review_trigger_valid(fields)
            or not _review_execution_valid(
                fields, command_manifest_path, root, planned_command_ids,
            )):
        return [Issue(
            "error", "bundle-automated-review-unexecuted",
            "自动审查命令和重跑结果必须明确执行成功", path,
        )]
    return []


def _review_trigger_valid(fields: dict[str, str]) -> bool:
    trigger = fields.get("review trigger", "")
    reference = fields.get("human trigger reference", "").strip()
    return ((trigger == "module_closure_candidate" and reference == "N/A")
            or (trigger == "human_requested" and bool(reference) and reference.casefold() != "n/a"))


def _review_scope_valid(
    fields: dict[str, str], planned_command_ids: set[str] | None,
) -> bool:
    scope = fields.get("scope", "")
    negative = r"(?i)\b(?:n/?a|none|skipped?|not\s+(?:run|executed)|unexecuted|without\s+execution|never\s+executed|(?:no\s+)?execution\s+omitted|no\s+execution)\b"
    if re.search(negative, scope):
        return False
    normalized = {item.strip().casefold() for item in re.split(r"[,;]", scope) if item.strip()}
    required = {"callers", "callees", "interfaces", "configuration", "tests", "traceability"}
    if _planned_swimlane_gates(planned_command_ids):
        required.add("swimlanes")
    changed = {item.strip().casefold() for item in fields.get("changed files", "").split(",") if item.strip()}
    return required <= normalized and changed <= normalized


def _review_execution_valid(
    fields: dict[str, str], manifest_path: Path, root: Path,
    planned_command_ids: set[str] | None,
) -> bool:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    commands = data.get("commands") if isinstance(data, dict) else None
    if not isinstance(commands, list):
        return False
    command_map = {item.get("id"): item for item in commands if isinstance(item, dict)}
    review_id = fields.get("review command id", "")
    review = command_map.get(review_id)
    if review_id != "automated_review" or not isinstance(review, dict):
        return False
    if fields.get("review command argv sha-256", "") != _argv_hash(review.get("argv")):
        return False
    if fields.get("review exit code") != "0" or not _artifact_matches(fields, root):
        return False
    rerun_ids = {item.strip() for item in fields.get("rerun command ids", "").split(",") if item.strip()}
    planned_swimlane = _planned_swimlane_gates(planned_command_ids)
    required = {"targeted_tests", "code_standards", "traceability", "automated_review", *planned_swimlane}
    exit_codes = _key_value_list(fields.get("rerun exit codes", ""))
    return (rerun_ids & SWIMLANE_GATE_IDS == planned_swimlane
            and required <= rerun_ids <= set(command_map)
            and set(exit_codes) == rerun_ids and set(exit_codes.values()) == {"0"})


def _planned_swimlane_gates(planned_command_ids: set[str] | None) -> set[str]:
    if planned_command_ids is None:
        return {"swimlane_evidence"}
    return set(SWIMLANE_GATE_IDS & planned_command_ids)


def _swimlane_evidence_required(planned_command_ids: set[str] | None) -> bool:
    return "swimlane_evidence" in _planned_swimlane_gates(planned_command_ids)


def _argv_hash(value: object) -> str:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        return ""
    return hashlib.sha256("\0".join(value).encode("utf-8")).hexdigest()


def _artifact_matches(fields: dict[str, str], root: Path) -> bool:
    raw_path = fields.get("review evidence path", "")
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or _has_symlink_component(root.resolve(), candidate):
        return False
    resolved = (root.resolve() / candidate).resolve()
    if _aliases_changed_file(resolved, fields.get("changed files", ""), root):
        return False
    try:
        resolved.relative_to(root.resolve())
        payload = resolved.read_bytes()
    except (ValueError, OSError):
        return False
    if hashlib.sha256(payload).hexdigest() != fields.get("review evidence sha-256", "").casefold():
        return False
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return False
    reruns = _key_value_list(fields.get("rerun exit codes", ""))
    try:
        rerun_results = {key: int(value) for key, value in reruns.items()}
    except ValueError:
        return False
    expected = {
        "schema_version": 1, "implementation_run_id": fields.get("run id"),
        "code_version": fields.get("code version"), "command_id": fields.get("review command id"),
        "code_fingerprint": fields.get("code fingerprint"),
        "command_manifest_fingerprint": fields.get("command manifest fingerprint"),
        "review_trigger": fields.get("review trigger"),
        "human_trigger_reference": fields.get("human trigger reference"),
        "changed_files": sorted(item.strip() for item in fields.get("changed files", "").split(",") if item.strip()),
        "argv_sha256": fields.get("review command argv sha-256"), "exit_code": 0,
        "findings": [], "reruns": rerun_results,
    }
    return _review_transcript_matches(data, expected) and _valid_time_range(data)


def _review_transcript_matches(data: object, expected: dict[str, object]) -> bool:
    required_keys = {*expected, "started_at", "ended_at"}
    if not isinstance(data, dict) or set(data) != required_keys:
        return False
    string_fields = ("implementation_run_id", "code_version", "code_fingerprint", "command_manifest_fingerprint",
                     "review_trigger", "human_trigger_reference", "command_id", "argv_sha256")
    if any(type(data.get(field)) is not str for field in string_fields):
        return False
    if type(data.get("schema_version")) is not int or type(data.get("exit_code")) is not int:
        return False
    reruns = data.get("reruns")
    if not isinstance(reruns, dict) or any(type(value) is not int for value in reruns.values()):
        return False
    if type(data.get("findings")) is not list or any(type(item) is not dict for item in data["findings"]):
        return False
    return all(data.get(key) == value for key, value in expected.items())


def _aliases_changed_file(evidence: Path, raw_changed: str, root: Path) -> bool:
    try:
        evidence_identity = (evidence.stat().st_dev, evidence.stat().st_ino)
    except OSError:
        return True
    for raw_path in (item.strip() for item in raw_changed.split(",") if item.strip()):
        candidate = root.resolve() / raw_path
        try:
            if (candidate.stat().st_dev, candidate.stat().st_ino) == evidence_identity:
                return True
        except OSError:
            return True
    return False


def _key_value_list(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(","):
        key, separator, raw = item.strip().partition("=")
        if not separator or not key or key in result:
            return {}
        result[key] = raw
    return result


def _valid_time_range(data: dict[str, object]) -> bool:
    try:
        start = datetime.fromisoformat(str(data["started_at"]))
        end = datetime.fromisoformat(str(data["ended_at"]))
    except (KeyError, ValueError):
        return False
    return start.tzinfo is not None and end.tzinfo is not None and start <= end


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def _swimlane_diagram_paths(path: Path | None) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    diagrams = data.get("diagrams") if isinstance(data, dict) else None
    return {
        item.get("path") for item in diagrams or []
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }


def _record_paths_include(
    raw_path: str, root: Path, requirements: dict[str, set[str]],
) -> bool:
    issue, text = _read_record(raw_path, root, "record-path-binding")
    if issue:
        return False
    fields, _, _, _ = _record_fields(text)
    for field, required in requirements.items():
        tokens = set(split_record_paths(fields.get(field.casefold(), "")))
        if not required or "" in required or required != tokens:
            return False
    return True


def _validate_progress_index(
    text: str, context: dict[str, str], root: Path, stage: str,
    paths: dict[str, tuple[str, str]],
) -> list[Issue]:
    section = extract_heading_section(text, DEVELOPMENT_PLAN_HEADING_RE) or ""
    progress = _declared_path(section, PROGRESS_RECORD_PATH)
    progress = _context_record_path(progress, context)
    modules = sorted(paths)
    run_links = ", ".join(f"{module}={paths[module][0]}" for module in modules)
    expected = {"Modules": ", ".join(modules), "Module run records": run_links}
    required: tuple[str, ...] = ()
    if stage == "completion":
        expected["Module latest records"] = ", ".join(
            f"{module}={paths[module][1]}" for module in modules
        )
        required = ("Module latest records",)
    return _validate_record(progress, root, "progress-index", expected, required)


def _review_path(text: str, context: dict[str, str]) -> str:
    section = extract_heading_section(text, AUTOMATED_REVIEW_HEADING_RE) or ""
    raw_path = _declared_path(section, AUTOMATED_REVIEW_EVIDENCE_PATH)
    return _context_record_path(raw_path, context) or ""


def _record_alias_issues(
    text: str, context: dict[str, str],
    module_paths: dict[str, tuple[str, str]], root: Path,
) -> list[Issue]:
    plan_section = extract_heading_section(text, DEVELOPMENT_PLAN_HEADING_RE) or ""
    paths = [
        _declared_path(plan_section, DEVELOPMENT_PLAN_PATH),
        _context_record_path(
            _declared_path(plan_section, PROGRESS_RECORD_PATH),
            context,
        ),
        _review_path(text, context),
        *(path for pair in module_paths.values() for path in pair),
    ]
    identities: dict[tuple[int, int], str] = {}
    for raw_path in (value for value in paths if value):
        candidate = root.resolve() / raw_path
        try:
            identity = (candidate.stat().st_dev, candidate.stat().st_ino)
        except OSError:
            continue
        if identity in identities:
            return [Issue("error", "bundle-declared-record-alias", "不同记录角色不得共享同一文件或硬链接", raw_path)]
        identities[identity] = raw_path
    return []
