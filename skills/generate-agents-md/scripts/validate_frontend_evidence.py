from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import zlib
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path
from validate_project_commands import validate_project_commands
from validate_traceability import _parse_metadata as parse_trace_metadata
from frontend_report_validation import _native_report_counts
from strict_json import loads as strict_json_loads
from template_schema_validation import frontend_issues as _frontend_template_issues
from browser_url_validation import is_http_browser_url
from browser_page_validation import PAGE_IDENTITY_FIELDS
from frontend_entry_validation import frontend_entry, frontend_page_issues
from browser_dom_validation import DOM_FIELDS, dom_action_issues, state_snapshot_state
from image_evidence_validation import screenshot_covers_viewport
from frontend_state_validation import ordered_actions as _ordered_actions, valid_state_transitions as _valid_state_transitions
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
MOBILE_SURFACES = {"mobile", "touch", "responsive"}
ISO_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
TOP_LEVEL_FIELDS = {
    "schema_version", "baseline_version", "baseline_sha256", "code_version",
    "build_id", "run_id", "browser", "e2e", "mobile", "verdict",
}
BROWSER_FIELDS = {
    "tool", "run_id", "verifier_agent_run_id", "started_at", "ended_at",
    "page_url", "transcript_path", "transcript_sha256", "verdict", "viewport", "click_path",
    "assertions", "state_transitions", "console_errors", "required_request_failures", "screenshots",
} | PAGE_IDENTITY_FIELDS | DOM_FIELDS
E2E_FIELDS = {
    "framework", "command_id", "execution_run_id", "started_at", "ended_at",
    "command_argv_sha256", "exit_code", "passed", "failed", "report_path", "report_sha256",
}
TRANSCRIPT_FIELDS = {
    "tool", "run_id", "verifier_agent_run_id", "page_url", "started_at", "ended_at", "viewport",
    "screenshots", "actions", "console_errors", "required_request_failures",
    "state_transitions",
} | PAGE_IDENTITY_FIELDS | DOM_FIELDS
ACTION_FIELDS = {"sequence", "action", "target", "result", "visible", "enabled"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def validate_frontend_evidence(
    path: Path,
    *,
    trace_path: Path,
    command_manifest: Path,
    project_root: Path,
    template: bool = False,
) -> list[Issue]:
    data, issues = _read_json(path)
    if data is None:
        return issues
    _validate_structure(data, issues)
    if template:
        issues.extend(Issue("error", code, message) for code, message in _frontend_template_issues(
            data, BROWSER_FIELDS, E2E_FIELDS, PLACEHOLDER_RE,
        ))
        return _deduplicate(issues)
    if PLACEHOLDER_RE.search(path.read_text(encoding="utf-8")):
        issues.append(Issue("error", "placeholder", "前端证据包含未解析占位符"))
    issues.extend(
        Issue(item.severity, f"commands-{item.code}", item.message)
        for item in validate_project_commands(command_manifest, project_root=project_root)
    )
    e2e_command = _validate_e2e_command(command_manifest, issues)
    entry = frontend_entry(command_manifest)
    if entry is None:
        try:
            command_data = strict_json_loads(command_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            command_data = None
        if isinstance(command_data, dict) and command_data.get("frontend_applicable") is True:
            issues.append(Issue("error", "browser-page-authority-mismatch", "命令清单缺少可信前端预览入口"))
    trace = _read_trace_metadata(trace_path, issues)
    if trace is None:
        return _deduplicate(issues)
    _validate_binding(data, trace, issues)
    root = project_root.resolve()
    _validate_browser(data.get("browser"), root, issues, label="browser", expected_entry=entry)
    _validate_e2e(data.get("e2e"), root, e2e_command, issues)
    surfaces = {item.strip().casefold() for item in trace.get("Change surfaces", "").split(",")}
    if surfaces & MOBILE_SURFACES:
        _validate_browser(data.get("mobile"), root, issues, label="mobile", expected_entry=entry)
        _validate_mobile_distinct(data.get("browser"), data.get("mobile"), issues)
    if data.get("verdict") != "pass":
        issues.append(Issue("error", "frontend-verdict-not-pass", "前端证据总 verdict 必须是 pass"))
    return _deduplicate(issues)


def _validate_e2e_command(path: Path, issues: list[Issue]) -> dict[str, object] | None:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    commands = data.get("commands", []) if isinstance(data, dict) else []
    entry = next((item for item in commands if isinstance(item, dict) and item.get("id") == "frontend_e2e"), None)
    argv = entry.get("argv", []) if entry else []
    valid_runner = _runner_framework_for_argv(argv) is not None
    if not valid_runner:
        issues.append(Issue("error", "e2e-command-framework-mismatch", "frontend_e2e argv 必须实际调用 Playwright 或 Cypress"))
    return entry


def _is_real_e2e_runner(tokens: list[str]) -> bool:
    return _runner_framework(tokens) is not None


def _runner_framework_for_argv(argv: object) -> str | None:
    if not isinstance(argv, list) or not argv:
        return None
    executable = str(argv[0])
    basename = Path(executable).name.casefold()
    if basename in {"playwright", "playwright.cmd", "cypress", "cypress.cmd"} and ("/" in executable or "\\" in executable):
        return None
    return _runner_framework([Path(str(item)).name.casefold() for item in argv])


def _runner_framework(tokens: list[str]) -> str | None:
    runners = {"playwright", "playwright.cmd", "cypress", "cypress.cmd"}
    actions = {"test", "run"}
    runner: str | None = None
    if len(tokens) >= 2 and tokens[0] in runners:
        runner = tokens[0] if tokens[1] in actions else None
    elif len(tokens) >= 4 and tokens[0].startswith("python") and tokens[1:2] == ["-m"]:
        runner = tokens[2] if tokens[2] in runners and tokens[3] in actions else None
    elif len(tokens) >= 3 and tokens[0] in {"npx", "pnpx", "bunx", "yarn"}:
        runner = tokens[1] if tokens[1] in runners and tokens[2] in actions else None
    elif len(tokens) >= 4 and tokens[0] in {"npm", "pnpm"} and tokens[1] == "exec":
        runner = tokens[2] if tokens[2] in runners and tokens[3] in actions else None
    if runner is None:
        return None
    return "Playwright" if runner.startswith("playwright") else "Cypress"


def _read_json(path: Path) -> tuple[dict[str, object] | None, list[Issue]]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [Issue("error", "invalid-frontend-evidence", str(error))]
    if not isinstance(data, dict):
        return None, [Issue("error", "invalid-frontend-evidence", "证据根节点必须是对象")]
    return data, []


def _validate_structure(data: dict[str, object], issues: list[Issue]) -> None:
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issues.append(Issue("error", "invalid-schema-version", "schema_version 必须是 1"))
    for field in ("baseline_version", "baseline_sha256", "code_version", "build_id", "run_id", "browser", "e2e", "mobile", "verdict"):
        if field not in data:
            issues.append(Issue("error", "missing-field", f"缺少前端证据字段：{field}"))
    if set(data) != TOP_LEVEL_FIELDS:
        issues.append(Issue("error", "invalid-frontend-fields", "前端证据含缺失或未知字段"))
    identities = ("baseline_version", "baseline_sha256", "code_version", "build_id", "run_id", "verdict")
    if any(type(data.get(field)) is not str or not data.get(field, "").strip() for field in identities):
        issues.append(Issue("error", "invalid-frontend-identity-types", "前端版本、构建、run 和 verdict 必须是非空字符串"))




def _read_trace_metadata(path: Path, issues: list[Issue]) -> dict[str, str] | None:
    try:
        return parse_trace_metadata(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        issues.append(Issue("error", "unreadable-trace", str(error)))
        return None


def _validate_binding(data: dict[str, object], trace: dict[str, str], issues: list[Issue]) -> None:
    mappings = (
        ("baseline_version", "Baseline version"),
        ("baseline_sha256", "Baseline SHA-256"),
        ("code_version", "Code version"),
        ("build_id", "Build ID"),
        ("run_id", "Implementation run ID"),
    )
    for evidence_field, trace_field in mappings:
        if str(data.get(evidence_field, "")).casefold() != trace.get(trace_field, "").casefold():
            issues.append(Issue("error", "stale-frontend-binding", f"{evidence_field} 与追踪矩阵不一致"))


def _validate_browser(
    value: object, root: Path, issues: list[Issue], *, label: str,
    expected_entry: tuple[str, str, str] | None,
) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("error", f"missing-{label}-evidence", f"缺少 {label} 浏览器证据对象"))
        return
    if set(value) != BROWSER_FIELDS:
        issues.append(Issue("error", f"invalid-{label}-fields", f"{label} 浏览器证据含缺失或未知字段"))
    if value.get("tool") != "browser:control-in-app-browser":
        issues.append(Issue("error", "wrong-browser-tool", "必须使用 browser:control-in-app-browser"))
    if not is_http_browser_url(value.get("page_url")):
        issues.append(Issue("error", f"invalid-{label}-page-url", f"{label} page_url 必须是无内嵌凭据的 HTTP(S) URL"))
    _validate_browser_transcript(value, root, issues, label=label, expected_entry=expected_entry)
    if value.get("verdict") != "pass":
        issues.append(Issue("error", f"{label}-verdict-not-pass", f"{label} verdict 必须是 pass"))
    viewport = value.get("viewport")
    if not isinstance(viewport, list) or len(viewport) != 2 or any(type(item) is not int or item <= 0 for item in viewport):
        issues.append(Issue("error", "invalid-viewport", f"{label} viewport 必须是两个正整数"))
    for field in ("click_path", "assertions"):
        items = value.get(field)
        minimum = 2 if field == "click_path" else 1
        if not isinstance(items, list) or len(items) < minimum or any(not isinstance(item, str) or not item for item in items):
            issues.append(Issue("error", f"invalid-{field.replace('_', '-')}", f"{label} {field} 证据不足"))
    for field in ("console_errors", "required_request_failures"):
        if value.get(field) != []:
            issues.append(Issue("error", f"nonempty-{field.replace('_', '-')}", f"{label} 存在 {field}"))
    screenshots = value.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots:
        issues.append(Issue("error", "missing-screenshots", f"{label} 缺少截图证据"))
    else:
        for item in screenshots:
            screenshot = _validate_hashed_artifact(item, root, issues, f"{label}-screenshot")
            if screenshot is not None and not screenshot_covers_viewport(screenshot.read_bytes(), viewport):
                issues.append(Issue("error", "screenshot-viewport-mismatch", f"{label} 截图像素必须覆盖声明视口"))


def _validate_browser_transcript(value: dict[str, object], root: Path, issues: list[Issue], *, label: str, expected_entry: tuple[str, str, str] | None) -> None:
    raw_run_id = value.get("run_id")
    run_id = raw_run_id.strip() if type(raw_run_id) is str else ""
    if not run_id:
        issues.append(Issue("error", "missing-browser-run-id", "应用内浏览器 run_id 不能为空"))
    raw_verifier = value.get("verifier_agent_run_id")
    verifier_run_id = raw_verifier.strip() if type(raw_verifier) is str else ""
    if not verifier_run_id:
        issues.append(Issue("error", "missing-browser-verifier-run-id", "前端点击必须绑定独立黑盒 Agent run ID"))
    interval = _validate_time_interval(value, label, issues)
    transcript = _validate_hashed_artifact(
        {"path": value.get("transcript_path"), "sha256": value.get("transcript_sha256")},
        root, issues, "browser-transcript",
    )
    if transcript is None:
        return
    try:
        data = strict_json_loads(transcript.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError):
        issues.append(Issue("error", "invalid-browser-transcript", "浏览器转录必须是可解析 JSON"))
        return
    if (not isinstance(data, dict) or data.get("tool") != value.get("tool")
            or data.get("run_id") != run_id or data.get("verifier_agent_run_id") != verifier_run_id
            or data.get("page_url") != value.get("page_url")
            or (interval is not None and (data.get("started_at"), data.get("ended_at")) != interval)):
        issues.append(Issue("error", "browser-transcript-mismatch", "浏览器转录与证据头不一致"))
        return
    if set(data) != TRANSCRIPT_FIELDS:
        issues.append(Issue("error", "invalid-browser-transcript-fields", "浏览器转录含缺失或未知字段"))
    issues.extend(Issue("error", code, message) for code, message in frontend_page_issues(
        value, data, root, label, expected_entry,
    ))
    issues.extend(Issue("error", code, message) for code, message in dom_action_issues(value, data, root))
    if data.get("state_transitions") != value.get("state_transitions") or not _valid_state_transitions(value):
        issues.append(Issue("error", "invalid-browser-state-transitions", "每次点击必须绑定不同的前后状态哈希和已声明断言"))
    else:
        _validate_state_transition_artifacts(value, root, issues)
    if data.get("viewport") != value.get("viewport") or data.get("screenshots") != value.get("screenshots"):
        issues.append(Issue(
            "error", "browser-transcript-artifact-mismatch", "浏览器转录必须绑定证据头的 viewport 和截图路径/哈希",
        ))
    _validate_transcript_actions(data.get("actions"), value, issues)
    if data.get("console_errors") != [] or data.get("required_request_failures") != []:
        issues.append(Issue("error", "browser-transcript-errors", "浏览器转录含控制台或必需请求错误"))


def _validate_transcript_actions(
    actions: object, evidence: dict[str, object], issues: list[Issue],
) -> None:
    action_names = {item.get("action") for item in actions if isinstance(item, dict)} if isinstance(actions, list) else set()
    if not {"navigate", "click", "assert", "screenshot"} <= action_names:
        issues.append(Issue("error", "incomplete-browser-transcript", "浏览器转录必须包含 navigate/click/assert/screenshot"))
    if not isinstance(actions, list) or any(not isinstance(item, dict) or item.get("result") != "pass" for item in actions):
        issues.append(Issue("error", "failed-browser-transcript-action", "浏览器转录存在失败动作"))
    elif any(set(item) != ACTION_FIELDS for item in actions):
        issues.append(Issue("error", "invalid-browser-action-fields", "浏览器动作含缺失或未知字段"))
    elif not _ordered_actions(actions, evidence):
        issues.append(Issue("error", "invalid-browser-action-order", "浏览器动作必须按 navigate/click/assert/screenshot 排序并绑定当前路径、断言或截图"))


def _validate_state_transition_artifacts(
    evidence: dict[str, object], root: Path, issues: list[Issue],
) -> None:
    for item in evidence["state_transitions"]:
        before = _validate_hashed_artifact(
            {"path": item["before_state_path"], "sha256": item["before_state_sha256"]},
            root, issues, "browser-before-state",
        )
        after = _validate_hashed_artifact(
            {"path": item["after_state_path"], "sha256": item["after_state_sha256"]},
            root, issues, "browser-after-state",
        )
        if before is not None and after is not None and before.read_bytes() == after.read_bytes():
            issues.append(Issue("error", "unchanged-browser-state", "点击前后状态快照内容必须实际变化"))
        before_state = state_snapshot_state(item["before_state_path"], item["assertion_target"], evidence, root)
        after_state = state_snapshot_state(item["after_state_path"], item["assertion_target"], evidence, root)
        if before_state is None or after_state is None or not after_state[1] or before_state[0] == after_state[0]:
            issues.append(Issue("error", "invalid-browser-state-snapshot",
                                "点击前后快照必须是 UTF-8 DOM，并证明声明断言目标的可见状态发生变化"))


def _validate_mobile_distinct(browser: object, mobile: object, issues: list[Issue]) -> None:
    if not isinstance(browser, dict) or not isinstance(mobile, dict):
        return
    if mobile.get("viewport") == browser.get("viewport"):
        issues.append(Issue("error", "mobile-viewport-not-distinct", "移动证据必须使用与桌面不同的移动视口"))
    mobile_hashes = _browser_artifact_hashes(mobile)
    browser_hashes = _browser_artifact_hashes(browser)
    reused_identity = mobile.get("run_id") == browser.get("run_id")
    reused_transcript = mobile.get("transcript_sha256") == browser.get("transcript_sha256")
    reused_screenshot = bool(mobile_hashes[1] & browser_hashes[1])
    if reused_identity or reused_transcript or reused_screenshot:
        issues.append(Issue(
            "error", "mobile-evidence-reused-desktop",
            "移动端必须使用独立 run ID，且转录与截图内容哈希不得复用桌面证据",
        ))


def _browser_artifact_hashes(value: dict[str, object]) -> tuple[object, set[object]]:
    screenshots = value.get("screenshots", [])
    screenshot_hashes = {
        item.get("sha256") for item in screenshots
        if isinstance(item, dict) and item.get("sha256")
    } if isinstance(screenshots, list) else set()
    return value.get("transcript_sha256"), screenshot_hashes


def _validate_e2e(
    value: object,
    root: Path,
    command_entry: dict[str, object] | None,
    issues: list[Issue],
) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("error", "missing-e2e-evidence", "缺少 E2E 证据对象"))
        return
    if set(value) != E2E_FIELDS:
        issues.append(Issue("error", "invalid-e2e-fields", "E2E 证据含缺失或未知字段"))
    if value.get("framework") not in {"Playwright", "Cypress"}:
        issues.append(Issue("error", "invalid-e2e-framework", "E2E framework 必须是 Playwright 或 Cypress"))
    if value.get("command_id") != "frontend_e2e":
        issues.append(Issue("error", "wrong-e2e-command", "E2E 必须引用 frontend_e2e 命令"))
    execution_run = value.get("execution_run_id")
    if type(execution_run) is not str or not execution_run.strip():
        issues.append(Issue("error", "missing-e2e-run-id", "E2E execution_run_id 不能为空"))
    _validate_time_interval(value, "e2e", issues)
    argv = command_entry.get("argv", []) if command_entry else []
    runner_framework = _runner_framework_for_argv(argv)
    if value.get("framework") != runner_framework:
        issues.append(Issue("error", "e2e-runner-framework-mismatch", "E2E framework 必须与 frontend_e2e 实际 runner 一致"))
    argv_fingerprint = hashlib.sha256("\0".join(str(item) for item in argv).encode("utf-8")).hexdigest()
    if value.get("command_argv_sha256") != argv_fingerprint:
        issues.append(Issue("error", "stale-e2e-command-binding", "E2E 执行证据未绑定当前 frontend_e2e argv"))
    numeric = (value.get("exit_code"), value.get("failed"), value.get("passed"))
    if (any(type(item) is not int for item in numeric) or value.get("exit_code") != 0
            or value.get("failed") != 0 or value.get("passed", 0) <= 0):
        issues.append(Issue("error", "e2e-not-passed", "E2E 必须 exit_code=0、failed=0 且 passed>0"))
    report = _validate_hashed_artifact(
        {"path": value.get("report_path"), "sha256": value.get("report_sha256")},
        root,
        issues,
        "e2e-report",
    )
    if report is not None:
        try:
            report_data = strict_json_loads(report.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError, ValueError):
            issues.append(Issue("error", "invalid-e2e-report", "E2E 报告必须是可解析 JSON"))
        else:
            counts = _native_report_counts(report_data, str(value.get("framework", "")))
            if counts != (value.get("passed"), value.get("failed")):
                issues.append(Issue("error", "e2e-report-mismatch", "E2E 报告内容与证据自报不一致"))


def _validate_time_interval(
    value: dict[str, object], label: str, issues: list[Issue]
) -> tuple[str, str] | None:
    raw_start, raw_end = str(value.get("started_at", "")), str(value.get("ended_at", ""))
    try:
        if not ISO_TIME_RE.fullmatch(raw_start) or not ISO_TIME_RE.fullmatch(raw_end):
            raise ValueError("shape")
        start = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
        if start > end:
            raise ValueError("order")
    except ValueError:
        issues.append(Issue("error", f"invalid-{label}-time", f"{label} 时间必须是可解析、带时区且开始不晚于结束的 ISO-8601"))
        return None
    return raw_start, raw_end


def _validate_hashed_artifact(value: object, root: Path, issues: list[Issue], label: str) -> Path | None:
    if not isinstance(value, dict):
        issues.append(Issue("error", "invalid-evidence-artifact", f"{label} 必须包含 path 和 sha256"))
        return None
    if set(value) != {"path", "sha256"}:
        issues.append(Issue("error", "invalid-evidence-artifact-fields", f"{label} 含缺失或未知字段"))
    if type(value.get("path")) is not str or type(value.get("sha256")) is not str:
        issues.append(Issue("error", "invalid-evidence-artifact-types", f"{label} 路径和哈希必须是字符串"))
        return None
    raw_path = value["path"]
    expected = value["sha256"].casefold()
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        issues.append(Issue("error", "unsafe-evidence-path", f"{label} 路径必须位于项目内"))
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(Issue("error", "unsafe-evidence-path", f"{label} 路径越出项目根"))
        return None
    if not resolved.is_file():
        issues.append(Issue("error", "missing-evidence-file", f"{label} 文件不存在：{raw_path}"))
        return None
    if resolved.stat().st_size == 0:
        issues.append(Issue("error", "empty-evidence-file", f"{label} 文件不能为空"))
        return None
    if not SHA256_RE.fullmatch(expected) or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected:
        issues.append(Issue("error", "stale-evidence-hash", f"{label} SHA-256 已失效"))
        return None
    if label.endswith("screenshot") and not _is_structurally_valid_image(resolved.read_bytes()):
        issues.append(Issue("error", "invalid-screenshot-format", f"{label} 不是可解析的 PNG/JPEG/WebP 图像证据"))
        return None
    return resolved


def _is_structurally_valid_image(payload: bytes) -> bool:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return _valid_png(payload)
    if payload.startswith(b"\xff\xd8"):
        return payload.endswith(b"\xff\xd9") and b"\xff\xda" in payload and any(marker in payload for marker in (b"\xff\xc0", b"\xff\xc2"))
    if payload.startswith(b"RIFF") and len(payload) >= 20:
        declared = struct.unpack("<I", payload[4:8])[0]
        return payload[8:12] == b"WEBP" and declared + 8 == len(payload) and payload[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    return False


def _valid_png(payload: bytes) -> bool:
    offset, idat, saw_ihdr, saw_iend = 8, bytearray(), False, False
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        chunk_type = payload[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(payload):
            return False
        chunk_data = payload[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length:end])[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False
        if chunk_type == b"IHDR":
            width, height = struct.unpack(">II", chunk_data[:8]) if length == 13 else (0, 0)
            saw_ihdr = width > 0 and height > 0
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            saw_iend = length == 0 and end == len(payload)
            break
        offset = end
    try:
        decoded = zlib.decompress(bytes(idat))
    except zlib.error:
        return False
    return saw_ihdr and saw_iend and bool(decoded)

def _deduplicate(issues: list[Issue]) -> list[Issue]:
    return list({(item.severity, item.code, item.message): item for item in issues}.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="验证应用内浏览器和 Playwright/Cypress 前端闭环证据")
    parser.add_argument("path", type=Path)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--command-manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    issues = validate_frontend_evidence(arguments.path, trace_path=arguments.trace, command_manifest=arguments.command_manifest, project_root=arguments.project_root, template=arguments.template)
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
