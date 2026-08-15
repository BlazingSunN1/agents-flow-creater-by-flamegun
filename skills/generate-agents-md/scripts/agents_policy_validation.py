from __future__ import annotations

import re
from urllib.parse import urlsplit

from agents_policy_common import (
    AUTOMATED_REVIEW_HEADING_RE,
    CONTEXT_BUDGET_HEADING_RE,
    DEVELOPMENT_PLAN_HEADING_RE,
    Issue,
    MACHINE_POLICY_HEADING_RE,
    PASSWORD_AUTHORIZATION_HEADING_RE,
    PLACEHOLDER_RE,
    REQUIRED_MACHINE_POLICY,
    URI_CREDENTIAL_DETAIL_RE,
    document_path_pattern as _document_path_pattern,
    extract_heading_section as _extract_heading_section,
    section_has_contradiction as _section_has_contradiction,
    section_has_line as _section_has_line,
)
from agents_delivery_policy_validation import (
    _validate_external_multi_model_policy,
    _validate_frontend_verification_policy,
    _validate_modular_execution_log_policy,
    _validate_swimlane_policy,
    _validate_traceability_policy,
)


def _validate_root_policies(text: str, mode: str) -> list[Issue]:
    issues: list[Issue] = []
    issues.extend(_validate_global_policy_contradictions(text))
    issues.extend(_validate_machine_policy(text))
    issues.extend(_validate_development_plan_policy(text, mode=mode))
    issues.extend(_validate_traceability_policy(text, mode=mode))
    issues.extend(_validate_automated_review_policy(text, mode=mode))
    issues.extend(_validate_context_budget_policy(text, mode=mode))
    issues.extend(_validate_swimlane_policy(text, mode=mode))
    issues.extend(_validate_modular_execution_log_policy(text, mode=mode))
    issues.extend(_validate_frontend_verification_policy(text))
    issues.extend(_validate_execution_evidence_policy(text, mode=mode))
    issues.extend(_validate_external_multi_model_policy(text))
    return issues


def _validate_global_policy_contradictions(text: str) -> list[Issue]:
    patterns = (
        r"(?:advisory\s+only|仅供参考).{0,120}(?:ignore|skip|忽略|跳过).{0,80}(?:validator|gate|check|验证器|门禁|检查)",
        r"(?:ignore|skip|忽略|跳过).{0,40}(?:all|every|全部|所有).{0,40}(?:validator|gate|check|验证器|门禁|检查)",
        r"(?:browser|e2e|前端|浏览器).{0,100}(?:checks?|verification|验证|检查).{0,50}(?:optional|可选).{0,100}(?:complete|completed|完成).{0,60}(?:without|无需|不需要)",
        r"(?:all|every|全部|所有).{0,40}(?:validators?|gates?|checks?|验证器|门禁|检查).{0,80}(?:discretionary|optional|need\s+not|not\s+required|可选|无需|不必)",
        r"(?:completion|complete|完成).{0,60}(?:allowed|permitted|可以|允许).{0,60}(?:no|without|未|无).{0,30}(?:validation|validator|verification|验证|检查)",
    )
    flattened = " ".join(line.strip() for line in text.splitlines())
    if any(re.search(pattern, flattened, re.IGNORECASE) for pattern in patterns):
        return [Issue("error", "contradictory-global-policy", "项目规则不得把机器门禁整体降级、忽略或设为可选")]
    return []


def _validate_execution_evidence_policy(text: str, *, mode: str) -> list[Issue]:
    path_pattern = _document_path_pattern(mode)
    checks = (
        (
            _section_has_line(text, (r"command registry|命令清单", path_pattern, r"before running|运行.*前", r"validat|校验"))
            and _section_has_line(text, (r"constant-success|恒定成功|fabricated|伪造", r"shell-wrapped|Shell", r"block|阻断")),
            "missing-real-command-registry",
            "缺少真实命令清单及执行前失败关闭校验规则",
        ),
        (
            _section_has_line(text, (r"sole code|single writer|唯一.*写者|唯一写者", r"implementation Agent|实现 Agent"))
            and _section_has_line(text, (r"independent Agents?|独立 Agent", r"read-only|只读", r"full chat|完整聊天", r"reasoning|推理", r"self-report|自报")),
            "missing-single-writer-agent-boundary",
            "缺少实现 Agent 单写者及独立 Agent 只读隔离边界",
        ),
        (
            _section_has_line(text, (r"small|小型", r"acceptance-case|验收用例", r"black-box|黑盒"))
            and _section_has_line(text, (r"standard|标准", r"change-review|变更审查"))
            and _section_has_line(text, (r"high-risk|高风险", r"requirement-consistency|需求一致", r"domain-specialist|领域专项")),
            "missing-risk-triggered-agent-roles",
            "缺少按风险触发的独立多 Agent 角色规则",
        ),
        (
            _section_has_line(text, (r"multi-Agent evidence|多 Agent.*证据", path_pattern, r"validat|校验"))
            and _section_has_line(text, (r"unique run ID|唯一.*run ID", r"hashed|哈希", r"disagreement|分歧", r"majority vote|多数票", r"blocked|阻断")),
            "missing-multi-agent-evidence-gate",
            "缺少多 Agent 证据绑定、分歧阻断和禁止多数票规则",
        ),
        (
            _section_has_line(text, (r"shared plan|共享.*计划", r"progress|进度", r"trace|追踪", r"context|工作集", r"file lock|文件锁", r"SHA-256", r"atomic|原子"))
            and _section_has_line(text, (r"stale write|过期写入", r"fail|失败", r"concurrent Agents?|并发 Agent", r"overwrite|覆盖")),
            "missing-atomic-record-update",
            "缺少共享记录的锁、期望哈希和原子更新规则",
        ),
        (
            _section_has_line(text, (r"structured browser|结构化.*浏览器", r"Playwright|Cypress", r"evidence|证据", path_pattern, r"validat|校验"))
            and _section_has_line(text, (r"stale hashes?|过期哈希", r"console errors?|控制台错误", r"failed requests?|请求失败", r"block|阻断")),
            "missing-frontend-evidence-gate",
            "缺少结构化前端证据路径及失败关闭校验规则",
        ),
    )
    return [Issue("error", code, message) for matched, code, message in checks if not matched]


def _validate_machine_policy(text: str) -> list[Issue]:
    section = _extract_heading_section(text, MACHINE_POLICY_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-machine-policy", "缺少根级 Machine-Enforced Policy 章节")]
    issues: list[Issue] = []
    values: dict[str, str] = {}
    in_yaml = False
    for line_number, line in enumerate(section.splitlines(), start=1):
        stripped = line.strip()
        if stripped == "```yaml":
            in_yaml = True
            continue
        if stripped == "```" and in_yaml:
            in_yaml = False
            continue
        if not in_yaml or not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*)\s*:\s*([A-Za-z0-9_-]+)", stripped)
        if not match:
            issues.append(Issue("error", "invalid-machine-policy-entry", "机器策略条目格式无效", line_number))
            continue
        key, value = match.groups()
        if key in values:
            issues.append(Issue("error", "duplicate-machine-policy-key", f"机器策略键重复：{key}", line_number))
        else:
            values[key] = value
    for key in sorted(set(values) - set(REQUIRED_MACHINE_POLICY)):
        issues.append(
            Issue("error", "unknown-machine-policy-key", f"机器策略包含未声明键：{key}")
        )
    for key, expected in REQUIRED_MACHINE_POLICY.items():
        actual = values.get(key)
        if actual != expected:
            issues.append(
                Issue(
                    "error",
                    "invalid-machine-policy",
                    f"机器策略 {key} 必须是 {expected}，当前为 {actual or 'missing'}",
                )
            )
    if not _section_has_line(section, (r"authoritative|权威", r"must not|不得|不能", r"weaken|contradict|削弱|冲突")):
        issues.append(Issue("error", "missing-machine-policy-authority", "机器策略块必须声明其他规则不得削弱或冲突"))
    return issues


def _validate_development_plan_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, DEVELOPMENT_PLAN_HEADING_RE)
    if section is None:
        return [
            Issue(
                "error",
                "missing-development-plan-section",
                "缺少“开发计划与完成进度”根级规则章节",
            )
        ]
    path_pattern = _document_path_pattern(mode)
    checks = (
        (
            _section_has_line(section, (r"development plan|开发计划", path_pattern)),
            "missing-development-plan-path",
            "开发计划章节缺少明确的计划文件路径",
        ),
        (
            _section_has_line(section, (r"completion|progress|完成|进度", path_pattern)),
            "missing-progress-record-path",
            "开发计划章节缺少明确的完成进度记录路径",
        ),
        (
            _section_has_line(section, (r"before|之前|前", r"objective|scope|steps|目标|范围|步骤")),
            "missing-plan-update-timing",
            "缺少实质开发前更新计划的规则",
        ),
        (
            _section_has_line(section, (r"after|之后|后", r"verif|验证", r"result|结果")),
            "missing-progress-update-timing",
            "缺少验证后记录结果与证据的规则",
        ),
        (
            all(value in section.casefold() for value in ("pending", "in_progress", "completed", "blocked")),
            "missing-progress-statuses",
            "完成进度章节缺少 pending/in_progress/completed/blocked 状态",
        ),
        (
            _section_has_line(section, (r"never|must not|do not|不得|不能", r"unverified|未验证", r"completed|完成")),
            "missing-progress-completion-gate",
            "缺少未验证工作不得标记 completed 的门禁",
        ),
        (
            _section_has_line(section, (r"Baseline version", r"Baseline SHA-256", r"Objective", r"Scope", r"Ordered steps", r"Verification criteria", r"Known risks"))
            and _section_has_line(section, (r"Run ID", r"Code version", r"Completion date", r"Delivered result", r"Validation performed", r"Remaining work", r"Status")),
            "missing-plan-progress-binding-rule",
            "缺少计划绑定需求基线及进度绑定 run/代码版本与完成字段的规则",
        ),
    )
    return [Issue("error", code, message) for matched, code, message in checks if not matched]


def _validate_automated_review_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, AUTOMATED_REVIEW_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-automated-review-section", "缺少自动代码审查根级规则章节")]
    path_pattern = _document_path_pattern(mode)
    issues = _automated_review_contradictions(section)
    checks = (
        (
            _section_has_line(section, (r"after every|每次", r"code module|代码模块", r"automatically|自动", r"`[^`]+`")),
            "missing-automated-review-command",
            "缺少每次代码模块修改后自动运行的审查命令",
        ),
        (
            _section_has_line(section, (r"missing|cannot run|缺失|无法运行", r"blocked|阻断", r"skip|跳过")),
            "missing-automated-review-fail-closed",
            "缺少自动审查命令不可用时失败关闭的规则",
        ),
        (
            _section_has_line(section, (r"actual changed files|真实变更文件", r"callers?|调用方", r"callees?|被调用方", r"interfaces?|接口", r"tests?|测试", r"trace|追踪", r"swimlane|泳道")),
            "missing-automated-review-impact-scope",
            "自动审查缺少真实变更及调用链、接口、测试、追踪和泳道影响面",
        ),
        (
            _section_has_line(section, (r"severity|严重", r"file|文件", r"line|行", r"trigger|触发", r"impact|影响", r"repro|verification|复现|验证")),
            "missing-actionable-review-findings",
            "自动审查发现缺少严重度、文件行号、触发、影响和复现证据",
        ),
        (
            _section_has_line(section, (r"regression test|回归测试", r"root-cause|根因", r"rerun|重跑", r"tests?|测试", r"code standards?|代码规范", r"trace|追踪", r"swimlane|泳道", r"review|审查")),
            "missing-automated-review-repair-loop",
            "缺少失败测试、最小根因修复及自动重跑审查闭环",
        ),
        (
            _section_has_line(section, (r"scope|范围", r"code version|代码版本", r"commands?|命令", r"findings?|发现", r"verdict|结论", path_pattern)),
            "missing-automated-review-evidence",
            "自动审查缺少项目内证据路径和必填字段",
        ),
        (
            _section_has_line(section, (r"do not|must not|不得|不能", r"black-box|黑盒", r"completed|完成", r"finding|问题|发现", r"blocked|阻断")),
            "missing-automated-review-completion-gate",
            "缺少未解决发现或审查阻断时禁止黑盒验收与完成的门禁",
        ),
    )
    return [*issues, *(Issue("error", code, message) for matched, code, message in checks if not matched)]


def _automated_review_contradictions(section: str) -> list[Issue]:
    if not _section_has_contradiction(
        section,
        action=r"(?:automatically\s+run|run\s+automatically|自动运行|自动执行)",
    ):
        return []
    return [Issue(
        "error",
        "contradictory-automated-review-policy",
        "自动代码审查章节包含禁止自动运行审查的反向规则",
    )]


def _validate_context_budget_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, CONTEXT_BUDGET_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-context-budget-section", "缺少上下文与 Token 预算根级规则章节")]
    path_pattern, issues = _document_path_pattern(mode), _context_budget_contradictions(section)
    checks = (
        (
            _section_has_line(section, (r"workset|工作集", r"manifest|清单", path_pattern, r"baseline|基线", r"code version|代码版本", r"requirement|需求", r"module|模块", r"files?|文件", r"commands?|命令", r"evidence|证据")),
            "missing-context-workset",
            "缺少带版本、影响面、命令和证据路径的当前工作集清单",
        ),
        (
            _section_has_line(section, (r"read in this order|读取顺序|按.*读取", r"index|索引", r"latest\.md", r"current run|当前.*run", r"requirement|需求", r"code|代码", r"tests?|测试", r"configuration|配置", r"diagram|图"))
            and _section_has_line(section, (r"do not|禁止|不得", r"whole repository|全仓", r"historical|历史", r"complete logs?|完整日志", r"default|默认")),
            "missing-selective-context-loading",
            "缺少按顺序选择性加载并禁止默认全仓/全历史/完整日志的规则",
        ),
        (
            _section_has_line(section, (r"expand|扩展", r"high-risk|高风险", r"cross-module|跨模块", r"public contract|公共契约", r"unknown impact|影响未知", r"test|测试", r"review|审查", r"reason|原因")),
            "missing-context-expansion-trigger",
            "缺少高风险、跨模块、未知影响或测试审查发现时扩展工作集的规则",
        ),
        (
            _section_has_line(section, (r"reuse|复用", r"code version|代码版本", r"command|命令", r"configuration hash|配置哈希", r"environment ID|环境", r"input hashes?|输入哈希", r"stale|过期|失效", r"rerun|重跑")),
            "missing-evidence-fingerprint",
            "缺少验证证据完整指纹、缓存失效和重跑规则",
        ),
        (
            _section_has_line(section, (r"fail-closed|失败关闭", r"manifest validator|清单验证", r"`[^`]+`", r"reus|复用", r"blocked|阻断")),
            "missing-context-manifest-validator",
            "缺少证据复用前失败关闭的工作集清单验证命令",
        ),
        (
            _section_has_line(section, (r"raw command output|原始.*输出", r"project paths?|项目.*路径", r"exit status|退出状态", r"result counts?|结果计数", r"fingerprint|指纹", r"evidence path|证据路径", r"do not paste|不.*粘贴")),
            "missing-compact-evidence-summary",
            "缺少原始输出落盘及上下文只保留紧凑摘要的规则",
        ),
        (
            _section_has_line(section, (r"independent Agent|独立 Agent", r"role-specific|职责|角色", r"input manifest|输入清单", r"full chat|完整聊天", r"repository documentation|全仓.*文档", r"reasoning|推理")),
            "missing-role-specific-agent-context",
            "缺少独立 Agent 最小角色输入及禁止传递完整上下文的规则",
        ),
        (
            _section_has_line(section, (r"do not rerun|避免重复|不.*重复", r"identical command|相同命令", r"fingerprint|指纹"))
            and _section_has_line(section, (r"never|不得|不能", r"Token|context|上下文", r"skip|跳过", r"correctness|正确性", r"security|安全", r"traceability|追踪", r"review|审查", r"acceptance|验收")),
            "missing-token-safety-boundary",
            "缺少避免无效重复且不得因 Token 限制跳过质量门禁的边界",
        ),
    )
    return [*issues, *(Issue("error", code, message) for matched, code, message in checks if not matched)]


def _context_budget_contradictions(section: str) -> list[Issue]:
    if not _section_has_contradiction(
        section,
        action=r"(?:maintain\s+(?:the\s+)?current\s+workset|维护当前工作集)",
    ):
        return []
    return [Issue(
        "error",
        "contradictory-context-workset-policy",
        "上下文章节包含禁止维护当前工作集的反向规则",
    )]


def _validate_password_authorization(text: str) -> list[Issue]:
    section = _extract_heading_section(text, PASSWORD_AUTHORIZATION_HEADING_RE)
    if section is None:
        return [
            Issue(
                "error",
                "missing-password-authorization",
                "获准记录密码时必须包含 Password Authorization 章节",
            )
        ]
    fields: dict[str, str] = {}
    duplicates: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^-\s+([^:：]+)[:：]\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.group(1).strip().casefold(), match.group(2).strip()
        if key in fields:
            duplicates.append(key)
        else:
            fields[key] = value
    if duplicates:
        return [Issue(
            "error", "duplicate-password-authorization-field",
            f"密码授权字段不得重复：{', '.join(sorted(set(duplicates)))}",
        )]
    aliases = {
        "scope": ("scope", "作用域"),
        "purpose": ("purpose", "用途"),
        "update method": ("update method", "更新方式"),
        "access boundary": ("access boundary", "访问边界"),
    }
    boundary_issue = _password_boundary_issue(fields, aliases)
    if boundary_issue:
        return [boundary_issue]
    return _password_endpoint_issues(text, fields)


def _password_boundary_issue(
    fields: dict[str, str], aliases: dict[str, tuple[str, str]],
) -> Issue | None:
    missing = [label for label, names in aliases.items() if not any(
        fields.get(name.casefold(), "").strip() for name in names
    )]
    if missing:
        return Issue(
            "error", "invalid-password-authorization",
            f"密码授权缺少非空边界字段：{', '.join(missing)}",
        )
    invalid_value = re.compile(
        r"^(?:tbd|todo|later|unknown|everyone|anyone|all|待定|以后|所有人|任意)$",
        re.IGNORECASE,
    )
    values = [
        next(fields[name.casefold()] for name in names if fields.get(name.casefold(), "").strip())
        for names in aliases.values()
    ]
    if any(PLACEHOLDER_RE.search(value) or invalid_value.fullmatch(value.strip()) for value in values):
        return Issue(
            "error", "invalid-password-authorization",
            "密码授权字段不得使用占位符、待定值或无限制访问边界",
        )
    return None


def _password_endpoint_issues(text: str, fields: dict[str, str]) -> list[Issue]:
    uri_endpoints = {
        endpoint
        for match in URI_CREDENTIAL_DETAIL_RE.finditer(text)
        if (endpoint := _normalized_password_endpoint(match.group("uri"))) is not None
    }
    if uri_endpoints:
        endpoints = fields.get("authorized endpoints", fields.get("授权端点", ""))
        authorized = {
            endpoint
            for item in endpoints.split(",")
            if (endpoint := _normalized_password_endpoint(item)) is not None
        }
        if not authorized or not uri_endpoints <= authorized:
            return [Issue("error", "unauthorized-password-endpoint", "每个 URI 内嵌密码端点必须逐项列入 Authorized endpoints")]
    return []


def _normalized_password_endpoint(raw_value: str) -> str | None:
    value = raw_value.strip().strip("`'\".,;")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not host:
        return None
    authority = host.casefold()
    if ":" in authority and not authority.startswith("["):
        authority = f"[{authority}]"
    if port is not None:
        authority = f"{authority}:{port}"
    return f"{parsed.scheme.casefold()}://{authority}{parsed.path or '/'}"
