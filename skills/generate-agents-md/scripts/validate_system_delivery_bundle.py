from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from agents_dispatcher_policy_validation import module_ownership_mapping
from strict_json import loads as strict_json_loads
from validate_context_manifest import _parse_metadata, _parse_module_file_map
from validate_delivery_bundle import validate_delivery_bundle
from implementation_agent_validation import (
    HostAttestationVerifier, _test_only_validate_implementation_agent,
    validate_implementation_agent,
)
from system_actor_validation import validate_module_gate_actors, validate_system_actors
from system_aggregate_validation import validate_system_aggregate_sets
from system_delivery_cli import main as system_delivery_main
from system_delivery_path_validation import normalized_project_path as _normalized_project_path
from system_record_path_validation import cross_module_record_template_error
from delivery_authority_binding import agents_declares_authority_binding, authority_binding_valid, receipt_repeats_authority_binding
from system_delivery_schema import (ARTIFACT_FIELDS, ARTIFACT_HASH_FIELDS, ENTRY_FIELDS,
                                    LEGACY_SYSTEM_FIELDS, MODULE_FIELDS, OPTIONAL_ARTIFACT_FIELDS, SYSTEM_FIELDS)
@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    source: str
@dataclass(frozen=True)
class ModuleResult:
    module: str
    requirement_ids: frozenset[str]
    changed_files: frozenset[str]
    maintainer_agent_id: str
    implementation_run_id: str
    reviewer_agent_ids: frozenset[str]
    reviewer_run_ids: frozenset[str]
def validate_system_delivery_bundle(
    *, manifest_path: Path, project_root: Path, stage: str = "completion",
    allow_passwords: bool = False,
) -> list[Issue]:
    return _validate_system_delivery_bundle_impl(
        manifest_path=manifest_path, project_root=project_root, stage=stage,
        allow_passwords=allow_passwords,
        module_validator=validate_delivery_bundle, host_attestation_verifier=None,
    )
def _test_only_validate_system_delivery_bundle(
    *, manifest_path: Path, project_root: Path, stage: str = "completion",
    allow_passwords: bool = False,
    _test_only_module_validator: Callable[..., list[object]],
    _test_only_host_attestation_verifier: HostAttestationVerifier,
) -> list[Issue]:
    return _validate_system_delivery_bundle_impl(
        manifest_path=manifest_path, project_root=project_root, stage=stage,
        allow_passwords=allow_passwords,
        module_validator=_test_only_module_validator,
        host_attestation_verifier=_test_only_host_attestation_verifier,
    )
def _validate_system_delivery_bundle_impl(
    *, manifest_path: Path, project_root: Path, stage: str, allow_passwords: bool,
    module_validator: Callable[..., list[object]],
    host_attestation_verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    if stage not in {"closure_candidate", "completion"}:
        return [_issue("system-stage-invalid", "系统聚合阶段只能是 closure_candidate 或 completion", manifest_path)]
    root = project_root.resolve()
    manifest, issues = _read_object(manifest_path, "system-delivery-bundle")
    if issues:
        return issues
    issues.extend(_validate_system_shape(manifest, str(manifest_path)))
    if issues:
        return _deduplicate(issues)
    agents_path, path_issue = _project_file(root, manifest["agents_path"], "agents")
    if path_issue:
        return [path_issue]
    agents_text = agents_path.read_text(encoding="utf-8")
    issues.extend(_validate_agents_identity(manifest, agents_path))
    template_error = cross_module_record_template_error(agents_text)
    if template_error:
        issues.append(_issue("system-module-record-path-template", template_error, agents_path))
    if not agents_declares_authority_binding(
        agents_text, manifest["authority_binding"],
    ):
        issues.append(_issue(
            "system-agents-authority-binding",
            "系统清单 authority locator/sha 必须逐字段绑定根 AGENTS 的生效权限矩阵",
            agents_path,
        ))
    issues.extend(
        _issue(item.code, item.message, str(manifest_path))
        for item in validate_system_actors(manifest, root, host_attestation_verifier)
    )
    issues.extend(_validate_aggregation_receipt_authority(manifest, root))
    canonical = module_ownership_mapping(agents_text)
    if not canonical:
        issues.append(_issue("system-module-ownership-invalid", "根 AGENTS 所有权映射不可解析", agents_path))
        return _deduplicate(issues)
    affected, changed_files = _affected_modules(manifest, canonical, issues)
    results = _validate_module_entries(
        manifest, root, canonical, stage, allow_passwords, module_validator, issues,
        host_attestation_verifier,
    )
    issues.extend(
        _issue(item.code, item.message, "system-delivery-bundle")
        for item in validate_system_aggregate_sets(manifest, affected, changed_files, results)
    )
    return _deduplicate(issues)
def _read_object(path: Path, source: str) -> tuple[dict[str, object], list[Issue]]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return {}, [_issue("system-bundle-unreadable", str(error), source)]
    if not isinstance(value, dict):
        return {}, [_issue("system-bundle-invalid-json", "交付清单必须是单一 JSON 对象", source)]
    return value, []
def _validate_system_shape(value: dict[str, object], source: str) -> list[Issue]:
    runtime_receipt_schema = value.get("runtime_receipt_schema_version")
    expected_fields = SYSTEM_FIELDS if runtime_receipt_schema == 2 else LEGACY_SYSTEM_FIELDS
    issues = _exact_fields(value, expected_fields, "system-bundle-schema", source)
    if runtime_receipt_schema is not None and runtime_receipt_schema != 2:
        issues.append(_issue(
            "system-runtime-receipt-schema",
            "runtime_receipt_schema_version 省略时使用 legacy receipt schema 1；显式值只能为 2",
            source,
        ))
    if (type(value.get("schema_version")) is not int or value.get("schema_version") != 2
            or value.get("dispatcher_mode") != "read-only"
            or value.get("aggregation_writer_role") != "SYSTEM_AGGREGATION"):
        issues.append(_issue("system-bundle-authority", "系统清单必须由独立 SYSTEM_AGGREGATION 写者生成；Dispatcher 只读调用 schema_version 2", source))
    if not authority_binding_valid(value.get("authority_binding"), "system"):
        issues.append(_issue(
            "system-authority-binding",
            "系统清单必须精确绑定 authority locator/sha 及 Dispatcher/聚合写者所需 role/action/policy",
            source,
        ))
    for field in ("requirement_ids", "system_changed_files", "affected_modules"):
        if not _unique_strings(value.get(field), minimum=1):
            issues.append(_issue("system-bundle-invalid-list", f"{field} 必须是非空唯一字符串数组", source))
    if not _unique_strings(value.get("open_findings"), minimum=0) or value.get("open_findings"):
        issues.append(_issue("system-bundle-open-finding", "系统聚合不得包含开放 finding", source))
    if not isinstance(value.get("module_bundles"), list) or len(value.get("module_bundles", [])) < 2:
        issues.append(_issue("system-bundle-insufficient-modules", "跨模块聚合至少需要两个模块交付包", source))
    for field in (
        "code_version", "build_id", "agents_path", "agents_sha256",
        "dispatcher_title", "dispatcher_provider", "dispatcher_model",
        "dispatcher_agent_id", "dispatcher_run_id",
        "dispatcher_spawn_receipt", "dispatcher_spawn_receipt_sha256",
        "aggregation_writer_title", "aggregation_writer_provider", "aggregation_writer_model",
        "aggregation_writer_agent_id", "aggregation_writer_run_id",
        "aggregation_spawn_receipt", "aggregation_spawn_receipt_sha256",
    ):
        if not isinstance(value.get(field), str) or not value[field].strip():
            issues.append(_issue("system-bundle-invalid-identity", f"{field} 必须是非空字符串", source))
    return issues
def _validate_agents_identity(value: dict[str, object], path: Path) -> list[Issue]:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    declared = str(value.get("agents_sha256", "")).casefold()
    if len(declared) != 64 or declared != actual:
        return [_issue("system-agents-hash-mismatch", "根 AGENTS SHA-256 与系统清单不一致", path)]
    return []
def _validate_aggregation_receipt_authority(value: dict[str, object], root: Path) -> list[Issue]:
    path, path_issue = _project_file(
        root, value.get("aggregation_spawn_receipt"), "aggregation-output-receipt",
    )
    if path_issue:
        return [path_issue]
    if not receipt_repeats_authority_binding(path, value.get("authority_binding")):
        return [_issue("system-aggregation-authority-binding",
                       "聚合 output receipt 必须逐字段重复系统候选的 authority locator/sha/required rows", path)]
    return []
def _affected_modules(
    value: dict[str, object], canonical: dict[str, tuple[tuple[str, ...], str]], issues: list[Issue],
) -> tuple[set[str], set[str]]:
    affected: set[str] = set()
    normalized_files: set[str] = set()
    for raw in value.get("system_changed_files", []):
        normalized = _normalized_project_path(raw)
        owners = set() if normalized is None else {
            module for module, (paths, _) in canonical.items()
            if any(normalized == path or normalized.startswith(path.rstrip("/") + "/") for path in paths)
        }
        if normalized is None or len(owners) != 1:
            issues.append(_issue("system-changed-file-owner-mismatch", f"系统变更文件未唯一归属模块：{raw}", "system-delivery-bundle"))
            continue
        normalized_files.add(normalized)
        affected.update(owners)
    return affected, normalized_files
def _validate_module_entries(
    value: dict[str, object], root: Path, canonical: dict[str, tuple[tuple[str, ...], str]],
    stage: str, allow_passwords: bool, module_validator: Callable[..., list[object]], issues: list[Issue],
    host_attestation_verifier: HostAttestationVerifier | None,
) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    seen_paths: set[Path] = set()
    seen_hashes: set[str] = set()
    for entry in value.get("module_bundles", []):
        result = _validate_module_entry(
            entry, value, root, canonical, stage, allow_passwords, module_validator,
            seen_paths, seen_hashes, issues, host_attestation_verifier,
        )
        if result is not None:
            results.append(result)
    return results
def _validate_module_entry(
    entry: object, system: dict[str, object], root: Path,
    canonical: dict[str, tuple[tuple[str, ...], str]], stage: str, allow_passwords: bool,
    module_validator: Callable[..., list[object]], seen_paths: set[Path],
    seen_hashes: set[str], issues: list[Issue],
    host_attestation_verifier: HostAttestationVerifier | None,
) -> ModuleResult | None:
    if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
        issues.append(_issue("system-module-entry-schema", "模块交付条目字段不完整或含未知字段", "system-delivery-bundle"))
        return None
    if not all(isinstance(entry[field], str) and entry[field].strip() for field in ENTRY_FIELDS):
        issues.append(_issue("system-module-entry-schema", "模块交付条目字段必须是非空字符串", "system-delivery-bundle"))
        return None
    declared_hash = str(entry["bundle_manifest_sha256"]).casefold()
    if len(declared_hash) != 64 or any(char not in "0123456789abcdef" for char in declared_hash):
        issues.append(_issue("system-module-bundle-hash-invalid", "模块交付清单必须声明 64 位 SHA-256", "system-delivery-bundle"))
        return None
    path, path_issue = _project_file(root, entry["bundle_manifest_path"], "module-bundle-manifest")
    if path_issue:
        issues.append(path_issue)
        return None
    if path in seen_paths:
        issues.append(_issue("system-module-bundle-duplicate", "模块交付清单路径必须唯一", path))
        return None
    seen_paths.add(path)
    if declared_hash in seen_hashes:
        issues.append(_issue("system-module-bundle-duplicate", "模块交付清单 SHA-256 必须唯一", path))
        return None
    seen_hashes.add(declared_hash)
    if hashlib.sha256(path.read_bytes()).hexdigest() != declared_hash:
        issues.append(_issue("system-module-bundle-hash-mismatch", "模块交付清单 SHA-256 不匹配", path))
        return None
    bundle, read_issues = _read_object(path, str(path))
    issues.extend(read_issues)
    if read_issues or _validate_module_shape(bundle, str(path), stage, issues):
        return None
    return _run_module_bundle(
        entry, bundle, system, root, canonical, stage, allow_passwords, module_validator,
        path, issues, host_attestation_verifier,
    )
def _validate_module_shape(value: dict[str, object], source: str, stage: str, issues: list[Issue]) -> bool:
    before = len(issues)
    issues.extend(_exact_fields(value, MODULE_FIELDS, "system-module-bundle-schema", source))
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 2 or value.get("stage") != stage:
        issues.append(_issue("system-module-not-complete", f"模块交付包必须是 {stage} 阶段 schema_version 2", source))
    if not authority_binding_valid(value.get("authority_binding"), "module"):
        issues.append(_issue(
            "system-module-authority-binding",
            "模块交付包必须精确绑定 authority locator/sha 及维护者/独立门禁所需 role/action/policy",
            source,
        ))
    if not _unique_strings(value.get("requirement_ids"), minimum=1):
        issues.append(_issue("system-module-requirements-invalid", "模块需求 ID 必须是非空唯一字符串数组", source))
    if not _unique_strings(value.get("open_findings"), minimum=0) or value.get("open_findings"):
        issues.append(_issue("system-module-open-finding", "模块交付包不得包含开放 finding", source))
    for field in (
        "module", "code_version", "build_id", "requirement_baseline_version",
        "requirement_baseline_sha256", "maintainer_title",
        "maintainer_provider", "maintainer_model", "maintainer_reasoning_effort", "maintainer_agent_id",
        "maintainer_spawn_receipt", "maintainer_spawn_receipt_sha256",
        "implementation_run_id",
    ):
        if not isinstance(value.get(field), str) or not value[field].strip():
            issues.append(_issue("system-module-identity-invalid", f"{field} 必须是非空字符串", source))
    artifacts = value.get("artifacts")
    if (not isinstance(artifacts, dict) or not ARTIFACT_FIELDS <= set(artifacts)
            or not set(artifacts) <= ARTIFACT_FIELDS | OPTIONAL_ARTIFACT_FIELDS):
        issues.append(_issue("system-module-artifacts-schema", "模块 artifacts 字段不完整或含未知字段", source))
    return len(issues) != before
def _run_module_bundle(
    entry: dict[str, object], bundle: dict[str, object], system: dict[str, object], root: Path,
    canonical: dict[str, tuple[tuple[str, ...], str]], stage: str, allow_passwords: bool,
    module_validator: Callable[..., list[object]],
    source: Path, issues: list[Issue], host_attestation_verifier: HostAttestationVerifier | None,
) -> ModuleResult | None:
    module = str(bundle["module"]).casefold()
    if str(entry["module"]).casefold() != module or module not in canonical:
        issues.append(_issue("system-module-key-mismatch", "条目模块必须存在于 canonical 所有权并匹配模块清单", source))
        return None
    expected_title = canonical[module][1]
    if bundle["maintainer_title"] != expected_title:
        issues.append(_issue("system-module-maintainer-mismatch", "模块维护 Agent 标题与 canonical 所有权不一致", source))
    if bundle["maintainer_provider"] != "codex-native-agent" or bundle["maintainer_model"] != "gpt-6-astra":
        issues.append(_issue("system-module-maintainer-model-mismatch", "模块维护 Agent 必须由封闭 receipt 声明并绑定为原生 gpt-6-astra；严格模式追加宿主证明", source))
    if bundle["maintainer_reasoning_effort"] != "medium":
        issues.append(_issue("system-module-maintainer-effort-mismatch", "模块维护 Agent 必须使用 reasoning_effort=medium", source))
    if bundle["code_version"] != system["code_version"] or bundle["build_id"] != system["build_id"]:
        issues.append(_issue("system-module-build-mismatch", "模块 code/build 身份与系统候选不一致", source))
    paths = _bound_module_artifacts(bundle, system, root, source, issues)
    if paths is None:
        return None
    verifier_kw = {} if host_attestation_verifier is None else {"_test_only_host_attestation_verifier": host_attestation_verifier}
    try:
        module_issues = module_validator(
            agents_path=paths["agents"], trace_path=paths["trace"], context_path=paths["context"],
            command_manifest_path=paths["command_manifest"], multi_agent_evidence_path=paths["multi_agent_evidence"],
            swimlane_evidence_path=paths["swimlane_evidence"], frontend_evidence_path=paths["frontend_evidence"],
            delivery_contract_path=paths["delivery_contract"],
            requirement_questions_path=paths["requirement_questions"],
            requirement_questions_sha256=bundle["artifacts"]["requirement_questions_sha256"],
            requirement_baseline_version=bundle["requirement_baseline_version"],
            requirement_baseline_sha256=bundle["requirement_baseline_sha256"],
            project_root=root, stage=stage, allow_passwords=allow_passwords,
            **verifier_kw,
        )
    except Exception as error:  # external/custom validators must fail closed
        issues.append(_issue("system-module-validator-crash", f"模块 {module} 验证器异常：{error}", source))
        return None
    if any(getattr(item, "severity", "error") == "error" for item in module_issues):
        issues.append(_issue("system-module-bundle-invalid", f"模块 {module} 的独立交付门禁未通过", source))
        return None
    try:
        return _module_result(
            bundle, paths["context"], paths["multi_agent_evidence"], module, root, stage,
            issues, host_attestation_verifier,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as error:
        issues.append(_issue("system-module-runtime-unreadable", f"模块运行证据不可解析：{error}", source))
        return None
def _bound_module_artifacts(
    bundle: dict[str, object], system: dict[str, object], root: Path,
    source: Path, issues: list[Issue],
) -> dict[str, Path | None] | None:
    module_authority, system_authority = bundle["authority_binding"], system["authority_binding"]
    if not isinstance(module_authority, dict) or not isinstance(system_authority, dict) or any(
        module_authority.get(field) != system_authority.get(field) for field in ("locator", "sha256")
    ):
        issues.append(_issue(
            "system-module-authority-binding", "系统和每个模块交付包必须绑定同一 authority locator/sha", source,
        ))
    paths = _artifact_paths(bundle["artifacts"], root, issues)
    if paths is None:
        return None
    if paths["agents"] != _project_file(root, system["agents_path"], "agents")[0]:
        issues.append(_issue("system-module-agents-mismatch", "所有模块必须绑定系统清单同一根 AGENTS", source))
    elif not agents_declares_authority_binding(paths["agents"].read_text(encoding="utf-8"), module_authority):
        issues.append(_issue(
            "system-module-agents-authority-binding", "模块交付包 authority locator/sha 必须逐字段绑定同一根 AGENTS", source,
        ))
    return paths
def _artifact_paths(value: object, root: Path, issues: list[Issue]) -> dict[str, Path | None] | None:
    if not isinstance(value, dict):
        return None
    paths: dict[str, Path | None] = {}
    for key in ARTIFACT_FIELDS | OPTIONAL_ARTIFACT_FIELDS:
        raw = value.get(key)
        if key in ARTIFACT_HASH_FIELDS:
            if not isinstance(raw, str) or re.fullmatch(r"[0-9a-f]{64}", raw) is None:
                issues.append(_issue(
                    "system-module-artifact-hash-invalid",
                    f"{key} 必须是 64 位小写 SHA-256",
                    "module-delivery-bundle",
                ))
                return None
            continue
        if key in {"delivery_contract", "frontend_evidence", "swimlane_evidence"} and raw is None:
            paths[key] = None
            continue
        path, issue = _project_file(root, raw, key)
        if issue:
            issues.append(issue)
            return None
        paths[key] = path
    questions = paths.get("requirement_questions")
    declared = value.get("requirement_questions_sha256")
    if questions is None or hashlib.sha256(questions.read_bytes()).hexdigest() != declared:
        issues.append(_issue(
            "system-module-requirement-questions-hash-mismatch",
            "模块 requirement questions SHA-256 与工件不一致",
            questions or "module-delivery-bundle",
        ))
        return None
    return paths
def _module_result(
    bundle: dict[str, object], context_path: Path, evidence_path: Path, module: str,
    root: Path, stage: str, issues: list[Issue],
    host_attestation_verifier: HostAttestationVerifier | None,
) -> ModuleResult:
    context, duplicates = _parse_metadata(context_path.read_text(encoding="utf-8"))
    evidence = strict_json_loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise ValueError("multi-agent evidence must be a JSON object")
    changed = _parse_module_file_map(context.get("Module changed files", "")).get(module, set())
    normalized = frozenset(item for raw in changed if (item := _normalized_project_path(raw)) is not None)
    context_requirements = frozenset(
        item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()
    )
    bundle_requirements = frozenset(bundle["requirement_ids"])
    if duplicates or evidence.get("implementation_agent_title") != bundle["maintainer_title"]:
        issues.append(_issue("system-module-runtime-mismatch", "模块 context/evidence 与维护 Agent 清单不一致", context_path))
    if evidence.get("implementation_run_id") != bundle["implementation_run_id"]:
        issues.append(_issue("system-module-runtime-mismatch", "实现 run ID 与模块清单不一致", evidence_path))
    issues.extend(_system_maintainer_binding_issues(
        bundle, evidence, context, root, evidence_path, host_attestation_verifier,
    ))
    if context_requirements != bundle_requirements:
        issues.append(_issue("system-module-requirements-mismatch", "模块需求必须与真实 context 精确一致", context_path))
    identity = (str(bundle["code_version"]), str(bundle["build_id"]))
    if identity != (context.get("Code version"), context.get("Build ID")) or identity != (
        evidence.get("code_version"), evidence.get("build_id"),
    ):
        issues.append(_issue(
            "system-module-artifact-identity-mismatch",
            "模块 bundle、context 与 multi-agent evidence 必须绑定同一 code/build",
            context_path,
        ))
    gate_issues, reviewer_agent_ids, reviewer_run_ids = validate_module_gate_actors(
        evidence, module, root, host_attestation_verifier, stage=stage,
    )
    issues.extend(_issue(f"system-{item.code}", item.message, evidence_path) for item in gate_issues)
    return ModuleResult(
        module, context_requirements, normalized, str(bundle["maintainer_agent_id"]),
        str(bundle["implementation_run_id"]), reviewer_agent_ids, reviewer_run_ids,
    )
def _system_maintainer_binding_issues(
    bundle: dict[str, object], evidence: dict[str, object], context: dict[str, str],
    root: Path, source: Path,
    host_attestation_verifier: HostAttestationVerifier | None,
) -> list[Issue]:
    binding = {
        "implementation_agent_provider": "maintainer_provider",
        "implementation_agent_model": "maintainer_model",
        "implementation_agent_reasoning_effort": "maintainer_reasoning_effort",
        "implementation_agent_id": "maintainer_agent_id",
        "implementation_spawn_receipt": "maintainer_spawn_receipt",
        "implementation_spawn_receipt_sha256": "maintainer_spawn_receipt_sha256",
    }
    issues = [
        _issue(
            "system-module-maintainer-receipt-mismatch",
            "模块 bundle 与 multi-agent evidence 必须绑定同一维护 Agent 原生 GPT-6 receipt",
            source,
        )
    ] if any(evidence.get(left) != bundle[right] for left, right in binding.items()) else []
    maintainer_issues = (validate_implementation_agent(evidence, context, root)
                         if host_attestation_verifier is None else
                         _test_only_validate_implementation_agent(
                             evidence, context, root,
                             _test_only_host_attestation_verifier=host_attestation_verifier,
                         ))
    issues.extend(
        _issue(f"system-{item.code}", item.message, source)
        for item in maintainer_issues
    )
    return issues


def _project_file(root: Path, raw: object, label: str) -> tuple[Path | None, Issue | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, _issue("system-bundle-path-invalid", f"{label} 路径必须是非空字符串", label)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, _issue("system-bundle-path-invalid", f"{label} 必须是项目内相对路径", raw)
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            return None, _issue("system-bundle-path-symlink", f"{label} 路径不得经过符号链接", raw)
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, _issue("system-bundle-path-escape", f"{label} 路径逃逸项目根目录", raw)
    if not resolved.is_file():
        return None, _issue("system-bundle-path-missing", f"{label} 文件不存在", raw)
    return resolved, None


def _unique_strings(value: object, *, minimum: int) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(
        isinstance(item, str) and item.strip() for item in value
    ) and len(value) == len(set(value))


def _exact_fields(value: dict[str, object], fields: set[str], code: str, source: str) -> list[Issue]:
    if set(value) == fields:
        return []
    return [_issue(code, "字段集合不完整或包含未知字段", source)]


def _issue(code: str, message: str, source: object) -> Issue:
    return Issue("error", code, message, str(source))


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.code, item.message, item.source): item for item in issues}.values())


def main() -> int:
    return system_delivery_main(validate_system_delivery_bundle)


if __name__ == "__main__":
    raise SystemExit(main())
