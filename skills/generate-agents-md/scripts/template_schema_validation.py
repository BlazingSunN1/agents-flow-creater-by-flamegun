from __future__ import annotations

import re


def frontend_issues(
    data: dict[str, object], browser_fields: set[str], e2e_fields: set[str], placeholder: re.Pattern[str],
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    browser = data.get("browser")
    if not isinstance(browser, dict) or set(browser) != browser_fields:
        issues.append(("invalid-browser-fields", "模板 browser 必须包含精确字段"))
    else:
        excluded = {"viewport", "click_path", "assertions", "state_transitions", "console_errors", "required_request_failures", "screenshots"}
        if any(type(browser.get(field)) is not str or not browser.get(field, "").strip() for field in browser_fields - excluded):
            issues.append(("invalid-browser-field-types", "模板 browser 身份和路径字段必须是字符串"))
        if browser.get("tool") != "browser:control-in-app-browser":
            issues.append(("wrong-browser-tool", "模板必须使用应用内浏览器"))
        issues.extend(_browser_list_issues(browser))
    e2e = data.get("e2e")
    if not isinstance(e2e, dict) or set(e2e) != e2e_fields:
        issues.append(("invalid-e2e-fields", "模板 e2e 必须包含精确字段"))
    elif any(
        type(e2e.get(field)) is bool
        or not (type(e2e.get(field)) is int or (type(e2e.get(field)) is str and placeholder.fullmatch(e2e[field])))
        for field in ("exit_code", "passed", "failed")
    ):
        issues.append(("invalid-e2e-counts", "模板 E2E 计数必须是整数或单一占位符"))
    elif any(
        type(e2e.get(field)) is not str or not e2e.get(field, "").strip()
        for field in e2e_fields - {"exit_code", "passed", "failed"}
    ):
        issues.append(("invalid-e2e-field-types", "模板 E2E 身份、时间、框架和路径必须是非空字符串"))
    mobile = data.get("mobile")
    mobile_placeholder = type(mobile) is str and bool(placeholder.fullmatch(mobile.strip()))
    mobile_na = type(mobile) is str and mobile.strip().casefold().startswith("n/a:")
    if not mobile_placeholder and not mobile_na:
        if not isinstance(mobile, dict) or set(mobile) != browser_fields:
            issues.append(("invalid-mobile-template", "模板 mobile 必须是单一占位符、N/A 原因或完整 browser 对象"))
        else:
            excluded = {"viewport", "click_path", "assertions", "state_transitions", "console_errors", "required_request_failures", "screenshots"}
            if any(type(mobile.get(field)) is not str or not mobile.get(field, "").strip() for field in browser_fields - excluded):
                issues.append(("invalid-mobile-template", "模板 mobile 身份和路径字段必须是字符串"))
            if mobile.get("tool") != "browser:control-in-app-browser":
                issues.append(("invalid-mobile-template", "模板 mobile 必须使用应用内浏览器"))
            issues.extend(("invalid-mobile-template", message) for _, message in _browser_list_issues(mobile))
    return issues


def _browser_list_issues(browser: dict[str, object]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    viewport = browser.get("viewport")
    if not isinstance(viewport, list) or len(viewport) != 2 or any(type(item) is not int or item <= 0 for item in viewport):
        issues.append(("invalid-viewport", "模板 viewport 必须是两个正整数"))
    for field in ("click_path", "assertions"):
        value = browser.get(field)
        if not isinstance(value, list) or not value or any(type(item) is not str or not item for item in value):
            issues.append((f"invalid-{field.replace('_', '-')}", f"模板 {field} 必须是非空字符串数组"))
    screenshots = browser.get("screenshots")
    invalid = not isinstance(screenshots, list) or not screenshots or any(
        not isinstance(item, dict) or set(item) != {"path", "sha256"}
        or any(type(item.get(field)) is not str or not item.get(field, "").strip() for field in ("path", "sha256"))
        for item in screenshots or []
    )
    if invalid:
        issues.append(("invalid-screenshots", "模板 screenshots 必须是精确的路径/哈希对象数组"))
    transitions = browser.get("state_transitions")
    fields = {
        "click_target", "assertion_target", "before_state_path", "before_state_sha256",
        "after_state_path", "after_state_sha256",
    }
    if not isinstance(transitions, list) or not transitions or any(
        not isinstance(item, dict) or set(item) != fields
        or any(type(item.get(field)) is not str or not item.get(field, "").strip() for field in fields)
        for item in transitions or []
    ):
        issues.append(("invalid-state-transitions", "模板 state_transitions 必须是精确的点击、断言和状态哈希对象数组"))
    if browser.get("console_errors") != [] or browser.get("required_request_failures") != []:
        issues.append(("browser-template-errors", "模板浏览器错误数组必须为空"))
    return issues


def swimlane_issues(
    data: dict[str, object], diagram_fields: set[str], browser_fields: set[str],
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    diagrams = data.get("diagrams")
    if not isinstance(diagrams, list) or not diagrams:
        issues.append(("invalid-swimlane-diagrams", "模板 diagrams 必须是非空数组"))
    else:
        for entry in diagrams:
            if not isinstance(entry, dict) or set(entry) != diagram_fields:
                issues.append(("invalid-swimlane-diagram-fields", "模板泳道条目必须包含精确字段"))
                continue
            if any(type(entry.get(field)) is not str or not entry.get(field, "").strip() for field in ("module", "path", "sha256")):
                issues.append(("invalid-swimlane-diagram-types", "模板泳道身份、路径和哈希必须是字符串"))
            evidence = entry.get("code_evidence")
            if not isinstance(evidence, list) or not evidence or any(type(item) is not str or not item.strip() for item in evidence):
                issues.append(("missing-swimlane-code-evidence", "模板 code_evidence 必须是非空字符串数组"))
    browser = data.get("browser")
    if not isinstance(browser, dict) or set(browser) != browser_fields:
        issues.append(("invalid-swimlane-browser-fields", "模板 browser 必须包含精确字段"))
    elif any(type(browser.get(field)) is not str or not browser.get(field, "").strip() for field in browser_fields):
        issues.append(("invalid-swimlane-browser-types", "模板 browser 字段必须是非空字符串"))
    elif browser.get("tool") != "browser:control-in-app-browser":
        issues.append(("wrong-swimlane-browser-tool", "模板泳道必须使用应用内浏览器"))
    return issues


def multi_agent_issues(
    data: dict[str, object], gate_fields: set[str],
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if data.get("open_disagreements") != []:
        issues.append(("open-agent-disagreement", "模板 open_disagreements 必须为空"))
    if data.get("implementation_agent_reasoning_effort") != "medium":
        issues.append(("invalid-implementation-agent-effort", "模板实现 Agent 必须固定 reasoning_effort=medium"))
    gates = data.get("gates")
    if not isinstance(gates, list):
        return [("invalid-gates", "模板 gates 必须是数组")]
    boundaries = {
        "may_modify_code", "may_modify_shared_records", "received_full_chat",
        "received_other_agent_reasoning", "accepted_implementation_self_report",
    }
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != gate_fields:
            issues.append(("invalid-gate-fields", "模板独立 Agent 门禁必须包含精确字段"))
            continue
        if any(gate.get(field) is not False for field in boundaries):
            issues.append(("unsafe-agent-boundary", "模板独立 Agent 边界必须为 false"))
        if any(type(gate.get(field)) is not str or not gate.get(field, "").strip() for field in gate_fields - boundaries):
            issues.append(("invalid-gate-types", "模板独立 Agent 身份、路径和结论必须是字符串"))
        if gate.get("provider") != "codex-native-agent" or gate.get("agent_model") != "gpt-6-astra":
            issues.append(("invalid-gate-agent", "模板独立 Agent 必须固定为 Codex 原生 gpt-6-astra"))
        if gate.get("agent_reasoning_effort") != "high":
            issues.append(("invalid-gate-agent-effort", "模板独立 Agent 必须固定 reasoning_effort=high"))
    return issues
