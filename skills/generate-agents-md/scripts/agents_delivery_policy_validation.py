from __future__ import annotations

import re

from agents_policy_common import (
    FRONTEND_VERIFICATION_HEADING_RE,
    Issue,
    MODULAR_LOG_HEADING_RE,
    SWIMLANE_HEADING_RE,
    TRACEABILITY_HEADING_RE,
    document_path_pattern as _document_path_pattern,
    extract_heading_section as _extract_heading_section,
    section_has_line as _section_has_line,
)


def _validate_traceability_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, TRACEABILITY_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-traceability-section", "缺少“需求追踪与交付门禁”根级规则章节")]
    path_pattern = _document_path_pattern(mode)
    checks = (
        *_traceability_baseline_checks(section, path_pattern),
        *_traceability_risk_checks(section, path_pattern),
        *_traceability_implementation_checks(section, path_pattern),
        *_traceability_completion_checks(section, path_pattern),
    )
    return [Issue("error", code, message) for matched, code, message in checks if not matched]


def _traceability_baseline_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(
    section,
    (
    r"traceability|追踪",
    r"matrix|矩阵",
    path_pattern,
    r"REQ-\*",
    r"FLOW-\*",
    r"FEAT-\*",
    r"UI-\*",
    r"UT-\*",
    r"AT-\*",
    r"MOD-\*",
    r"BB-\*",
    ),
    ),
    "missing-traceability-matrix",
    "缺少追踪矩阵路径或 REQ/FLOW/FEAT/UI/UT/AT/MOD/BB 稳定编号链",
    ),
    (
    _section_has_line(section, (r"before implementation|实现前", r"objective|目标", r"scope|范围", r"non-goals?|非目标", r"constraints?|约束", r"acceptance|验收")),
    "missing-requirement-baseline",
    "缺少实现前固化目标、范围、非目标、约束和验收标准的需求基线",
    ),
    (
    _section_has_line(section, (r"baseline artifact|基线文件|基线产物", r"version|版本", r"SHA-256|哈希"))
    and _section_has_line(section, (r"black-box|黑盒", r"code version|代码版本", r"build ID|构建", r"environment|环境", r"time|时间")),
    "missing-version-bound-evidence",
    "缺少需求基线哈希及黑盒代码/构建/环境/时间绑定",
    ),
    (
    _section_has_line(section, (r"ambigu|歧义", r"return|退回", r"block|阻断", r"invent|发明|自行")),
    "missing-ambiguity-return-gate",
    "缺少歧义退回需求基线并阻断自行扩展需求的门禁",
    ),
    )


def _traceability_risk_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"standard|标准", r"high-risk|高风险", r"solution design|方案", r"swimlane|泳道", r"feature|功能", r"black-box|黑盒")),
    "missing-delivery-sequence",
    "缺少标准和高风险任务从方案到独立黑盒验收的有序流程",
    ),
    (
    _section_has_line(section, (r"small|小型", r"standard|标准", r"high-risk|高风险", r"reason|原因"))
    and _section_has_line(section, (r"small|小型", r"skip|跳过", r"inapplicable|不适用", r"never skips?|不能跳过", r"traceability|追踪", r"test|测试", r"swimlane|泳道")),
    "missing-risk-tier-policy",
    "缺少风险分级及小型任务仅跳过不适用重型门禁的规则",
    ),
    (
    _section_has_line(section, (r"change surfaces|变更面", r"behavior-change", r"user-visible", r"ui", r"api", r"standard|标准"))
    and _section_has_line(section, (r"public-api", r"auth", r"security", r"migration", r"persistence", r"async", r"cross-module", r"data-schema", r"high-risk|高风险"))
    and _section_has_line(section, (r"unknown|未知", r"high-risk|高风险", r"until disproved|证明")),
    "missing-objective-risk-escalation",
    "缺少由变更面触发且未知默认高风险的客观升级规则",
    ),
    (
    _section_has_line(section, (r"independent UI/UX Agent|独立 UI/UX Agent", r"approved|批准", r"prototype|原型", r"must report|报告", r"instead of|不得|不能", r"requirements?|需求")),
    "missing-independent-ui-ux-gate",
    "缺少独立 UI/UX Agent 的输入、产出和禁止扩需求边界",
    ),
    )




def _traceability_implementation_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"test points?|测试点", r"unit test|单元", r"before implementation|实现前", r"separate|independent|另一个|独立", r"acceptance Agent|验收 Agent", r"complete|完整")),
    "missing-independent-acceptance-case-gate",
    "缺少实现前测试点、单元用例和独立 Agent 完整验收用例",
    ),
    (
    _section_has_line(section, (r"new|新增|changed behavior|改变行为", r"identifier|编号", r"design|方案", r"swimlane|泳道", r"test|测试", r"before code|代码.*前")),
    "missing-traced-change-control",
    "缺少新增或改变行为先更新追踪产物再继续编码的变更控制",
    ),
    (
    _section_has_line(section, (r"code standards?|代码规范", r"continuously|持续", r"before and during|实现前.*实现中", r"`[^`]+`")),
    "missing-continuous-code-standards",
    "缺少在实现前和实现中持续执行真实代码规范命令的规则",
    ),
    (
    _section_has_line(section, (r"independent black-box Agent|独立黑盒 Agent", r"acceptance cases?|验收用例", r"release-like|类发布", r"without|不得|不能", r"modify code|修改代码|self-report|自报")),
    "missing-independent-black-box-gate",
    "缺少独立黑盒 Agent 的用例、环境和禁止修改代码或接受自报边界",
    ),
    )


def _traceability_completion_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"distinct|不同|独立", r"implementation.*run ID|实现.*run ID", r"UI/UX", r"acceptance-case|验收用例", r"black-box|黑盒"))
    and _section_has_line(section, (r"input manifest|输入清单", r"output evidence|输出证据", r"must not|不得|不能", r"equal|相同|复用")),
    "missing-independent-run-evidence",
    "缺少独立 Agent 运行编号、最小输入清单及防自证/复用规则",
    ),
    (
    _section_has_line(section, (r"implementation_defect", r"requirement_ambiguity", r"acceptance_case_defect", r"environment_blocker", r"approved_requirement_change"))
    and _section_has_line(section, (r"never|不得|不能", r"requirements?|需求", r"implementation defect|实现缺陷", r"pass|通过")),
    "missing-failure-routing",
    "缺少失败分类、固定回流路径及禁止为实现缺陷改需求的规则",
    ),
    (
    _section_has_line(section, (r"fail-closed|失败关闭", r"semantic trace validator|语义追踪", r"`[^`]+`", r"before implementation handoff|实现交接前", r"completed|完成"))
    and _section_has_line(section, (r"missing|cannot run|缺失|无法运行", r"blocked|阻断", r"manual judgment|人工判断|人工")),
    "missing-semantic-trace-validator",
    "缺少实现交接与完成前运行的失败关闭语义追踪命令",
    ),
    (
    _section_has_line(section, (
        r"delivery-bundle validator|交付包验证", r"`[^`]+`", r"AGENTS\.md",
        r"traceability matrix|追踪矩阵", r"context manifest|工作集", r"plan/progress|计划.进度",
        r"automated-review|自动审查", r"module run|模块.*run", r"latest\.md",
        r"baseline|基线", r"code version|代码版本", r"run ID",
    )),
    "missing-delivery-bundle-validator",
    "缺少跨 AGENTS、追踪、工作集、计划进度、审查和模块日志的交付包一致性验证命令",
    ),
    (
    _section_has_line(section, (r"independent Agent|独立 Agent", r"cannot|无法", r"blocked|阻断", r"must not|不得|不能", r"self-cert|自证"))
    and _section_has_line(section, (r"not mark|do not mark|不得.*标记|不能.*标记", r"completed|完成", r"trace|追踪", r"tests?|测试", r"independent acceptance|独立验收", r"bug|错误")),
    "missing-independent-completion-gate",
    "缺少独立 Agent 不可用时阻断及追踪、测试、独立验收、无 Bug 完成门禁",
    ),
    )






def _validate_swimlane_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, SWIMLANE_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-swimlane-section", "缺少“泳道图同步”根级规则章节")]
    path_pattern = _document_path_pattern(mode)
    checks = (
        *_swimlane_trigger_checks(section),
        (
            _section_has_line(section, (r"if|when|如果|当", r"system overview|系统总览", r"first|before|先")),
            "missing-swimlane-overview-rule",
            "缺少系统级流程变化时先更新完整系统总览的规则",
        ),
        (
            _section_has_line(section, (r"module.*swimlane|module.*diagram|模块.*泳道图|模块.*图", path_pattern))
            and _section_has_line(section, (r"system overview|系统总览", path_pattern)),
            "missing-swimlane-path",
            "缺少系统总览和模块泳道图的两个明确路径",
        ),
        (
            _section_has_line(section, (r"browser|浏览器", r"click|点击", r"lane header|泳道头", r"connector|连线", r"return|返回")),
            "missing-swimlane-browser-check",
            "缺少在浏览器中实际点击验证交互式泳道图闭环的规则",
        ),
        (
            _has_local_http_preview_policy(section),
            "missing-local-http-browser-preview",
            "本地交互页面缺少回环 HTTP 预览且禁止 file:// 自动化证据的规则",
        ),
        (
            _section_has_line(section, (r"record|记录", r"diagram path|图路径", r"code evidence|代码证据", r"verification|验证")),
            "missing-swimlane-progress-evidence",
            "缺少在完成进度中记录泳道图路径和验证证据的规则",
        ),
        (
            _section_has_line(section, (r"not complete|must not|do not mark|不得|不能", r"completed|完成", r"synchroni|verified|同步|验证")),
            "missing-swimlane-completion-gate",
            "缺少“泳道图未同步验证不得标记代码修改完成”的门禁",
        ),
        (
            _section_has_line(section, (r"implementation code|实现代码", r"entry point|入口", r"call chain|调用链", r"test|测试")),
            "missing-swimlane-code-evidence",
            "缺少从实现代码、入口、调用链和测试提取泳道图的规则",
        ),
    )
    missing = [Issue("error", code, message) for matched, code, message in checks if not matched]
    return [*_swimlane_contradictions(section), *missing]


def _swimlane_trigger_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        (
            _section_has_line(
                section,
                (r"stage|milestone|阶段|里程碑", r"complete|完成", r"generate|update|synchron|生成|更新|同步", r"swimlane|泳道图"),
            ),
            "missing-swimlane-sync-rule",
            "缺少“阶段或任务里程碑完成时同步对应泳道图”的强制规则",
        ),
        (
            _section_has_line(
                section,
                (r"only when|immediately only|仅当|只在", r"flow|entry point|handoff|流程|入口|交接", r"update|更新"),
            ),
            "missing-swimlane-flow-change-trigger",
            "缺少里程碑之间仅在流程变化时立即更新泳道图的规则",
        ),
    )


def _swimlane_contradictions(section: str) -> list[Issue]:
    issues: list[Issue] = []
    if _required_swimlane_update_negated(section):
        issues.append(Issue(
            "error", "contradictory-swimlane-update-policy",
            "泳道章节不得禁止阶段完成或流程变化时的必要同步",
        ))
    forced_internal = (
        r"after\s+every\s+(?:code\s+)?(?:edit|change|refactor)|(?:every|each)\s+(?:(?:flow-neutral|internal|code)\s+)*(?:edit|change|refactor)|always|whenever|每次|每逢|所有|任何",
        r"flow-neutral|internal edit|internal change|flow[- ]neutral|流程无关|不影响流程|内部修改|内部调整",
        r"update|redraw|同步|更新|重画",
    )
    if _section_has_line(section, forced_internal):
        issues.append(Issue(
            "error", "contradictory-swimlane-frequency-policy",
            "泳道章节不得强制流程无关内部修改逐次重画",
        ))
    if _swimlane_trigger_weakened(section):
        issues.append(Issue(
            "error", "weakened-swimlane-trigger-policy",
            "阶段完成或流程变化时的泳道同步不得降级为可选动作",
        ))
    return issues


def _required_swimlane_update_negated(section: str) -> bool:
    trigger = r"stage|milestone|flow\s+change|阶段|里程碑|流程变化"
    negation = r"do\s+not|must\s+not|need\s+not|not\s+(?:required|mandatory|compulsory)|no\s+need|unnecessary|never|skip|不得|不能|禁止|不要|无需|不必|跳过|并非强制|不是必须"
    action = r"update|updated|updating|synchroni[sz](?:e|ed|ing|ation)|redraw|redrawing|更新|同步|重画"
    for line in section.splitlines():
        for clause in re.split(r"[.;。；]", line):
            completion_gate = r"(?:not\s+complete|must\s+not\s+be\s+marked\s+completed|不得.{0,20}完成).{0,100}(?:until|直到|前).{0,60}(?:synchroni[sz]ed|同步|verified|验证)"
            if re.search(completion_gate, clause, re.IGNORECASE):
                continue
            if all(re.search(pattern, clause, re.IGNORECASE) for pattern in (trigger, negation, action)):
                return True
    return False


def _swimlane_trigger_weakened(section: str) -> bool:
    trigger = r"stage|milestone|flow|entry point|handoff|阶段|里程碑|流程|入口|交接"
    weak = r"\bmay\b|\bcan\b|\bshould\b|optional|recommended|可选|可以|建议"
    action = r"update|updating|synchroni[sz](?:e|ing|ation)|redraw|redrawing|更新|同步|重画"
    return _section_has_line(section, (trigger, weak, action))


def _validate_frontend_verification_policy(text: str) -> list[Issue]:
    section = _extract_heading_section(text, FRONTEND_VERIFICATION_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-frontend-verification-section", "缺少“前端交互验证”根级规则章节")]
    checks = (
        (
            _section_has_line(section, (r"every|after every|每次", r"frontend code|前端代码", r"browser:control-in-app-browser")),
            "missing-in-app-browser-rule",
            "缺少每次前端代码修改后使用 browser:control-in-app-browser 的规则",
        ),
        (
            _section_has_line(section, (r"playwright|cypress", r"e2e|end-to-end|端到端", r"`[^`]+`")),
            "missing-frontend-e2e-rule",
            "缺少 Playwright/Cypress 端到端验证规则",
        ),
        (
            _section_has_line(section, (r"desktop|pc|桌面", r"viewport|视口")),
            "missing-desktop-frontend-viewport",
            "缺少默认桌面 PC 浏览器视口验证规则",
        ),
        (
            _section_has_line(
                section,
                (
                    r"only when|if|仅当|只有|明确.*时",
                    r"mobile|移动端",
                    r"requirement|baseline|supported environment|scope|需求|基线|支持环境|范围",
                    r"otherwise|not required|must not block|否则|不要求|不得.*阻断|不能.*阻断",
                ),
            ),
            "missing-conditional-mobile-viewport",
            "缺少仅在需求或支持范围明确涉及移动端时才启用且否则不得阻断的规则",
        ),
        (
            _section_has_line(section, (r"human|manual-like|人工", r"click|点击", r"entry|入口", r"result|结果|闭环")),
            "missing-human-click-closure",
            "缺少从入口到结果的人工式点击闭环",
        ),
        (
            _has_local_http_preview_policy(section),
            "missing-local-http-browser-preview",
            "本地前端页面缺少 HTTP(S) 服务入口且禁止 file:// 自动化证据的规则",
        ),
        (
            _section_has_line(section, (r"bug|error|错误", r"not complete|must not|do not mark|不得|不能", r"completed|完成|通过")),
            "missing-frontend-zero-bug-gate",
            "缺少发现 Bug 或错误时不得标记前端修改通过的门禁",
        ),
    )
    return [Issue("error", code, message) for matched, code, message in checks if not matched]


def _has_local_http_preview_policy(section: str) -> bool:
    return _section_has_line(section, (
        r"local|本地", r"server|preview|loopback|服务|预览|回环",
        r"http://|https://|HTTP", r"file://", r"never|not valid|禁止|不得",
    ))


def _validate_modular_execution_log_policy(text: str, *, mode: str) -> list[Issue]:
    section = _extract_heading_section(text, MODULAR_LOG_HEADING_RE)
    if section is None:
        return [Issue("error", "missing-modular-execution-log-section", "缺少“模块化执行日志”根级规则章节")]
    path_pattern = _document_path_pattern(mode)
    checks = (*_execution_log_storage_checks(section, path_pattern),
              *_execution_log_read_checks(section, path_pattern))
    return [Issue("error", code, message) for matched, code, message in checks if not matched]


def _execution_log_storage_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"compact|小型|简短", r"index|索引", path_pattern)),
    "missing-execution-log-index",
    "模块化执行日志缺少明确的小型索引路径",
    ),
    (
    _section_has_line(section, (r"immutable|不可变", r"module|模块", r"run_id", path_pattern)),
    "missing-module-execution-log-route",
    "缺少按模块和 run_id 存放不可变单次日志的路径",
    ),
    (
    _section_has_line(section, (r"run_id", r"code_version|code version|代码版本", r"distinct|separate|never treat|分开|不得混")),
    "missing-execution-version-separation",
    "模块化执行日志必须分开记录 run_id 和 code_version",
    ),
    (
    _section_has_line(section, (r"latest\.md", r"update|更新", r"summary|摘要")),
    "missing-module-latest-summary",
    "模块化执行日志缺少模块 latest.md 压缩摘要",
    ),
    (
    _section_has_line(section, (r"module|模块", r"status|状态", r"risk|风险", r"traceability|追踪", r"changed files|变更文件", r"result|结果", r"verification|验证", r"independent review|独立评审", r"swimlane|泳道图")),
    "missing-execution-log-fields",
    "单次执行日志缺少模块、状态、风险、追踪编号、变更文件、结果、验证、独立评审或泳道图字段",
    ),
    )


def _execution_log_read_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"read|读", r"index|索引", r"only|只", r"latest\.md", r"run_id")),
    "missing-selective-log-read-policy",
    "缺少先读索引、再只读受影响模块的选择性读取协议",
    ),
    (
    _section_has_line(section, (r"older runs?|old records?|history|历史|旧记录", r"regression|回归", r"conflict|冲突", r"decision|决策")),
    "missing-history-read-guard",
    "缺少仅在回归、冲突或历史决策调查时读取旧日志的限制",
    ),
    (
    _section_has_line(section, (r"cross-module|跨模块", r"system|系统", path_pattern)),
    "missing-system-execution-log-route",
    "缺少跨模块执行的系统级日志路由",
    ),
    (
    _section_has_line(section, (r"completed|完成", r"latest\.md", r"index|索引", r"do not mark|不得|不能")),
    "missing-execution-log-completion-gate",
    "缺少日志、latest.md 和索引未同步时不得标记 completed 的门禁",
    ),
    (
    _section_has_line(section, (r"reference|引用", r"path|路径", r"test output|测试输出", r"screenshot|截图", r"diff", r"instead of|do not paste|不粘贴")),
    "missing-large-artifact-reference-rule",
    "缺少大段测试输出、截图和 diff 只引用路径而不粘贴的 Token 节省规则",
    ),
    )


def _validate_external_multi_model_policy(text: str) -> list[Issue]:
    checks = (
        (
            _section_has_line(text, (
                r"explicitly enable|明确启用", r"spawn_external_agent", r"Kimi",
                r"complete design|complete revision|完整设计|完整修订",
            )),
            "missing-external-kimi-author-policy",
            "缺少显式启用、隔离 spawn_external_agent 和 Kimi 完整设计/修订边界",
        ),
        (
            _section_has_line(text, (
                r"DeepSeek", r"black-box|黑盒", r"review|审查", r"Codex GPT|GPT",
                r"independent|独立", r"same candidate|同一候选|same version|同一版本",
            )),
            "missing-external-review-role-policy",
            "缺少 DeepSeek 黑盒/审查与 GPT 独立同候选复核职责",
        ),
        (
            _section_has_line(text, (
                r"six rounds|6 rounds|六轮|6 轮", r"incomplete|未完成",
                r"hash|SHA-256|哈希", r"bundle|聚合|门禁",
            )),
            "missing-external-loop-binding-policy",
            "缺少六轮上限、未通过状态及同候选哈希聚合门禁",
        ),
        (
            _section_has_line(text, (
                r"not replace|never replace|不得替代|不替代", r"native|原生",
                r"black-box|黑盒", r"runtime|运行时|execution|执行",
            )),
            "missing-external-adviser-isolation-policy",
            "缺少外部顾问不替代原生 Agent 和真实黑盒执行的边界",
        ),
    )
    issues = [Issue("error", code, message) for matched, code, message in checks if not matched]
    contradiction_patterns = (
        r"(?:external multi-model|spawn_external_agent|外部多模型).{0,100}(?:informational only|obsolete|deprecated|仅供参考|已废弃)",
        r"Kimi.{0,80}(?:need not|must not|optional|无需|不必).{0,80}(?:author|design|revision|设计|修订)",
        r"DeepSeek.{0,80}(?:need not|must not|optional|无需|不必).{0,80}(?:black-box|review|黑盒|审查)",
        r"(?:Codex )?GPT.{0,80}(?:need not|must not|optional|无需|不必).{0,80}(?:independent|adjudicat|verify|独立|裁决|复核)",
        r"(?:hash|SHA-256|哈希).{0,80}(?:bundle|门禁).{0,50}(?:informational only|optional|obsolete|仅供参考|可选|已废弃)",
    )
    flattened = " ".join(line.strip() for line in text.splitlines())
    if any(re.search(pattern, flattened, re.IGNORECASE) for pattern in contradiction_patterns):
        issues.append(Issue("error", "contradictory-external-multi-model-policy", "外部多模型职责、同候选门禁和六轮停止不得被否定或降级"))
    return issues
