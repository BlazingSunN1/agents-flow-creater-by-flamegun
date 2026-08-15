from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from strict_json import loads as strict_json_loads
from template_schema_validation import swimlane_issues as _swimlane_template_issues
from browser_url_validation import is_http_browser_url
from browser_page_validation import PAGE_IDENTITY_FIELDS, page_identity_issues
from swimlane_html_validation import system_drilldown_issues

from validate_context_manifest import _parse_metadata as parse_context_metadata
from validate_context_manifest import _parse_module_file_map
from validate_traceability import _parse_metadata as parse_trace_metadata


SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
TOP_LEVEL_FIELDS = {
    "schema_version", "baseline_version", "baseline_sha256", "code_version",
    "build_id", "run_id", "diagrams", "browser", "verdict",
}
DIAGRAM_FIELDS = {"module", "path", "sha256", "code_evidence"}
BROWSER_FIELDS = {"tool", "run_id", "page_url", "transcript_path", "transcript_sha256"} | PAGE_IDENTITY_FIELDS
TRANSCRIPT_FIELDS = {
    "tool", "run_id", "page_url", "actions", "modules_opened", "assertions", "console_errors", "verdict",
} | PAGE_IDENTITY_FIELDS
ACTION_FIELDS = {"sequence", "action", "target", "result", "visible", "enabled"}
ASSERTION_FIELDS = {
    "single_module_open", "lane_headers_visible", "connectors_visible", "back_to_overview",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_swimlane_evidence(
    path: Path,
    *,
    trace_path: Path,
    context_path: Path,
    project_root: Path,
    template: bool = False,
) -> list[Issue]:
    data, issues = _read_json(path, "invalid-swimlane-evidence")
    if data is None:
        return issues
    _validate_structure(data, issues)
    if template:
        issues.extend(Issue("error", code, message) for code, message in _swimlane_template_issues(
            data, DIAGRAM_FIELDS, BROWSER_FIELDS,
        ))
        return _deduplicate(issues)
    if PLACEHOLDER_RE.search(path.read_text(encoding="utf-8")):
        issues.append(Issue("error", "placeholder", "泳道证据包含未解析占位符"))
    trace = _read_metadata(trace_path, parse_trace_metadata, "trace", issues)
    context = _read_metadata(context_path, lambda text: parse_context_metadata(text)[0], "context", issues)
    if trace is None or context is None:
        return _deduplicate(issues)
    _validate_binding(data, trace, context, issues)
    modules = {item.strip() for item in context.get("Modules", "").split(",") if item.strip()}
    root = project_root.resolve()
    _validate_diagrams(data.get("diagrams"), modules, context, root, issues)
    raw_diagrams = data.get("diagrams")
    diagrams = raw_diagrams if isinstance(raw_diagrams, list) else []
    system = next((entry for entry in diagrams if isinstance(entry, dict) and entry.get("module") == "system"), {})
    _validate_browser(data.get("browser"), modules, system, root, issues)
    if data.get("verdict") != "pass":
        issues.append(Issue("error", "swimlane-verdict-not-pass", "泳道证据总 verdict 必须是 pass"))
    return _deduplicate(issues)


def _read_json(path: Path, code: str) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [Issue("error", code, str(error))]
    if not isinstance(data, dict):
        return None, [Issue("error", code, "JSON 根节点必须是对象")]
    return data, []


def _validate_structure(data: dict[str, object], issues: list[Issue]) -> None:
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issues.append(Issue("error", "invalid-schema-version", "schema_version 必须是 1"))
    for field in (
        "baseline_version", "baseline_sha256", "code_version", "build_id",
        "run_id", "diagrams", "browser", "verdict",
    ):
        if field not in data:
            issues.append(Issue("error", "missing-field", f"缺少泳道证据字段：{field}"))
    if set(data) != TOP_LEVEL_FIELDS:
        issues.append(Issue("error", "invalid-swimlane-fields", "泳道证据含缺失或未知字段"))
    identities = ("baseline_version", "baseline_sha256", "code_version", "build_id", "run_id", "verdict")
    if any(type(data.get(field)) is not str or not data.get(field, "").strip() for field in identities):
        issues.append(Issue("error", "invalid-swimlane-identity-types", "泳道版本、构建、run 和 verdict 必须是非空字符串"))


def _read_metadata(path: Path, parser, label: str, issues: list[Issue]) -> dict[str, str] | None:
    try:
        return parser(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        issues.append(Issue("error", f"unreadable-{label}", str(error)))
        return None


def _validate_binding(
    data: dict[str, object],
    trace: dict[str, str],
    context: dict[str, str],
    issues: list[Issue],
) -> None:
    mappings = (
        ("baseline_version", "Baseline version"),
        ("baseline_sha256", "Baseline SHA-256"),
        ("code_version", "Code version"),
        ("build_id", "Build ID"),
        ("run_id", "Implementation run ID"),
    )
    for field, trace_field in mappings:
        if str(data.get(field, "")).casefold() != trace.get(trace_field, "").casefold():
            issues.append(Issue("error", "stale-swimlane-binding", f"{field} 与追踪矩阵不一致"))
    if str(data.get("run_id", "")) != context.get("Run ID", ""):
        issues.append(Issue("error", "swimlane-context-run-mismatch", "泳道 run_id 与工作集不一致"))


def _validate_diagrams(
    raw_diagrams: object,
    modules: set[str],
    context: dict[str, str],
    root: Path,
    issues: list[Issue],
) -> None:
    if not isinstance(raw_diagrams, list):
        issues.append(Issue("error", "invalid-swimlane-diagrams", "diagrams 必须是数组"))
        return
    diagram_map: dict[str, dict[str, object]] = {}
    identities: dict[tuple[int, int], str] = {}
    changed = {item.strip() for item in context.get("Changed files", "").split(",") if item.strip()}
    module_files = _parse_module_file_map(context.get("Module changed files", ""))
    covered_changed: set[str] = set()
    for entry in raw_diagrams:
        if not isinstance(entry, dict):
            issues.append(Issue("error", "invalid-swimlane-diagram", "泳道条目必须是对象"))
            continue
        if set(entry) != DIAGRAM_FIELDS:
            issues.append(Issue("error", "invalid-swimlane-diagram-fields", "泳道条目含缺失或未知字段"))
        raw_module = entry.get("module")
        module = raw_module.strip() if type(raw_module) is str else ""
        if not module or module in diagram_map:
            issues.append(Issue("error", "duplicate-or-missing-swimlane-module", f"泳道模块缺失或重复：{module}"))
        diagram_map[module] = entry
        diagram, evidence_paths = _validate_diagram_entry(
            entry, module, changed if module == "system" else module_files.get(module, set()),
            modules if module == "system" else set(), root, issues,
        )
        covered_changed |= evidence_paths & changed
        if diagram is not None:
            identity = (diagram.stat().st_dev, diagram.stat().st_ino)
            if identity in identities:
                issues.append(Issue("error", "reused-swimlane-diagram", f"{module} 与 {identities[identity]} 复用同一泳道文件"))
            identities[identity] = module
    required = modules | {"system"}
    for missing in required - set(diagram_map):
        issues.append(Issue("error", "missing-swimlane-module", f"缺少系统或模块泳道：{missing}"))
    for extra in set(diagram_map) - required:
        issues.append(Issue("error", "unexpected-swimlane-module", f"泳道模块不在当前工作集：{extra}"))
    for uncovered in changed - covered_changed:
        issues.append(Issue("error", "uncovered-swimlane-changed-file", f"变更文件未映射到系统或模块泳道：{uncovered}"))


def _validate_diagram_entry(
    entry: dict[str, object], module: str, expected_evidence: set[str],
    expected_modules: set[str], root: Path, issues: list[Issue],
) -> tuple[Path | None, set[str]]:
    diagram = _validate_hashed_file(
        entry.get("path"), entry.get("sha256"), root, "swimlane-diagram", issues,
    )
    code_evidence = entry.get("code_evidence")
    valid_evidence = (
        isinstance(code_evidence, list) and code_evidence
        and all(type(item) is str and bool(item.strip()) for item in code_evidence)
    )
    evidence_paths = set(code_evidence) if valid_evidence else set()
    if not evidence_paths:
        issues.append(Issue("error", "missing-swimlane-code-evidence", f"{module} 缺少代码依据"))
    elif evidence_paths != expected_evidence:
        issues.append(Issue("error", "swimlane-code-evidence-mismatch", f"{module} 未精确绑定所属变更文件"))
    for evidence_path in evidence_paths:
        _resolve_file(evidence_path, root, "swimlane-code-evidence", issues)
    if diagram is None:
        return None, evidence_paths
    text = diagram.read_text(encoding="utf-8", errors="replace")
    if 'class="lane-head"' not in text or not re.search(r'class="(?:module-)?flow"', text):
        issues.append(Issue("error", "invalid-swimlane-html", f"{module} 缺少泳道头或连线"))
    if module == "system":
        issues.extend(Issue("error", code, message) for code, message in system_drilldown_issues(
            text, expected_modules, diagram, root,
        ))
    return diagram, evidence_paths


def _validate_browser(
    raw_browser: object, modules: set[str], system: dict[str, object], root: Path, issues: list[Issue],
) -> None:
    if not isinstance(raw_browser, dict):
        issues.append(Issue("error", "invalid-swimlane-browser", "browser 必须是对象"))
        return
    if set(raw_browser) != BROWSER_FIELDS:
        issues.append(Issue("error", "invalid-swimlane-browser-fields", "泳道浏览器证据含缺失或未知字段"))
    if raw_browser.get("tool") != "browser:control-in-app-browser":
        issues.append(Issue("error", "wrong-swimlane-browser-tool", "泳道必须使用应用内浏览器"))
    if not is_http_browser_url(raw_browser.get("page_url")):
        issues.append(Issue("error", "invalid-swimlane-page-url", "泳道 page_url 必须是无内嵌凭据的 HTTP(S) URL"))
    raw_run_id = raw_browser.get("run_id")
    run_id = raw_run_id.strip() if type(raw_run_id) is str else ""
    if not run_id:
        issues.append(Issue("error", "missing-swimlane-browser-run", "泳道浏览器 run_id 不能为空"))
    transcript = _validate_hashed_file(
        raw_browser.get("transcript_path"), raw_browser.get("transcript_sha256"),
        root, "swimlane-browser-transcript", issues,
    )
    if transcript is None:
        return
    data, transcript_issues = _read_json(transcript, "invalid-swimlane-browser-transcript")
    issues.extend(transcript_issues)
    if data is None:
        return
    _validate_swimlane_transcript(data, raw_browser, run_id, modules, system, root, issues)


def _validate_swimlane_transcript(
    data: dict[str, object], raw_browser: dict[str, object], run_id: str, modules: set[str],
    system: dict[str, object], root: Path, issues: list[Issue],
) -> None:
    if set(data) != TRANSCRIPT_FIELDS:
        issues.append(Issue("error", "invalid-swimlane-transcript-fields", "泳道浏览器转录含缺失或未知字段"))
    issues.extend(Issue("error", code, message) for code, message in page_identity_issues(
        raw_browser, data, root, code="swimlane-page-artifact-mismatch",
        expected_path=system.get("path") if type(system.get("path")) is str else None,
        expected_sha256=system.get("sha256") if type(system.get("sha256")) is str else None,
        require_loopback=True,
    ))
    if (data.get("tool") != raw_browser.get("tool") or data.get("run_id") != run_id
            or data.get("page_url") != raw_browser.get("page_url")):
        issues.append(Issue("error", "swimlane-browser-transcript-mismatch", "浏览器转录与证据头不一致"))
    actions = data.get("actions")
    action_names = {item.get("action") for item in actions if isinstance(item, dict)} if isinstance(actions, list) else set()
    if not {"navigate", "click", "assert"} <= action_names:
        issues.append(Issue("error", "incomplete-swimlane-browser-actions", "泳道转录必须包含 navigate/click/assert"))
    if not isinstance(actions, list) or any(not isinstance(item, dict) or item.get("result") != "pass" for item in actions):
        issues.append(Issue("error", "failed-swimlane-browser-action", "泳道转录存在失败或非结构化动作"))
    elif any(set(item) != ACTION_FIELDS for item in actions):
        issues.append(Issue("error", "invalid-swimlane-action-fields", "泳道动作含缺失或未知字段"))
    elif not _ordered_actions(actions, modules):
        issues.append(Issue("error", "invalid-swimlane-action-order", "泳道动作必须按 navigate/click/assert 排序并逐模块绑定 target"))
    opened = set(data.get("modules_opened", [])) if isinstance(data.get("modules_opened"), list) else set()
    if opened != modules:
        issues.append(Issue("error", "incomplete-swimlane-module-clicks", "浏览器未逐个进入当前模块"))
    assertions = data.get("assertions")
    required_assertions = ("single_module_open", "lane_headers_visible", "connectors_visible", "back_to_overview")
    if not isinstance(assertions, dict) or any(assertions.get(key) is not True for key in required_assertions):
        issues.append(Issue("error", "failed-swimlane-browser-assertion", "泳道头、连线、单模块展开或返回总览断言未通过"))
    elif set(assertions) != ASSERTION_FIELDS:
        issues.append(Issue("error", "invalid-swimlane-assertion-fields", "泳道断言含缺失或未知字段"))
    if data.get("console_errors") != [] or data.get("verdict") != "pass":
        issues.append(Issue("error", "swimlane-browser-not-clean", "泳道浏览器存在错误或 verdict 未通过"))


def _ordered_actions(actions: list[dict[str, object]], modules: set[str]) -> bool:
    ranks = {"navigate": 0, "click": 1, "assert": 2}
    targets = {"navigate": {"system"}, "click": modules, "assert": modules}
    previous, clicked = -1, set()
    for index, item in enumerate(actions, start=1):
        action, target = item.get("action"), item.get("target")
        if (type(item.get("sequence")) is not int or item.get("sequence") != index
                or type(action) is not str or action not in ranks
                or type(target) is not str or target not in targets[action]
                or item.get("visible") is not True or item.get("enabled") is not True
                or ranks[action] < previous):
            return False
        previous = ranks[action]
        if action == "click":
            clicked.add(target)
    return clicked == modules and {"navigate", "assert"} <= {item["action"] for item in actions}


def _validate_hashed_file(
    raw_path: object, raw_hash: object, root: Path, code: str, issues: list[Issue]
) -> Path | None:
    if type(raw_path) is not str or type(raw_hash) is not str:
        issues.append(Issue("error", f"unsafe-{code}-path", "证据路径和哈希必须是字符串"))
        return None
    resolved = _resolve_file(raw_path, root, code, issues)
    expected = raw_hash.casefold()
    if resolved is not None and (not SHA256_RE.fullmatch(expected) or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected):
        issues.append(Issue("error", f"stale-{code}", f"证据哈希失效：{raw_path}"))
    return resolved


def _resolve_file(raw_path: str, root: Path, code: str, issues: list[Issue]) -> Path | None:
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径必须位于项目内：{raw_path}"))
        return None
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            issues.append(Issue("error", f"unsafe-{code}-path", f"路径不得经过符号链接：{raw_path}"))
            return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", f"unsafe-{code}-path", f"路径越出项目根：{raw_path}"))
        return None
    if not resolved.is_file():
        issues.append(Issue("error", f"missing-{code}", f"文件不存在：{raw_path}"))
        return None
    return resolved


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证系统/模块泳道、代码依据和浏览器点击闭环")
    parser.add_argument("path", type=Path)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_swimlane_evidence(
        arguments.path, trace_path=arguments.trace, context_path=arguments.context,
        project_root=arguments.project_root, template=arguments.template,
    )
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
