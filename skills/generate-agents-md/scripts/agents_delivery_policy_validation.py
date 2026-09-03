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
    _section_has_line(section, (r"question_id", r"impact_scope", r"risk", r"proposed_default", r"safe_fallback", r"answer_status", r"delivery_disposition", r"assumption", r"owner", r"review_due"))
    and _section_has_line(section, (r"NOT_PROVIDED|unanswered|未答", r"P2", r"never.*block|不.*阻", r"reversible|可逆", r"continue|继续"))
    and _section_has_line(section, (r"legal|法律", r"security|安全", r"destruct|不可逆|破坏", r"permission|权限", r"not.*block|不.*阻"))
    and _section_has_line(section, (r"ANSWERED", r"requirement|需求", r"objective|目标", r"baseline|基线", r"affected|受影响", r"rerun|重跑")),
    "missing-question-default-continuation-policy",
    "缺少所有未答疑问作为非阻塞 P2、安全默认继续及答案到达后纠偏重跑的机器规则",
    ),
    )

def _traceability_risk_checks(section: str, path_pattern: str) -> tuple[tuple[bool, str, str], ...]:
    return (
    (
    _section_has_line(section, (r"when|applicable|risk mapping|仅当|适用|风险映射", r"solution design|方案", r"swimlane|泳道", r"feature|功能", r"black-box|黑盒")),
    "missing-delivery-sequence",
    "缺少按适用风险从方案到独立黑盒验收的有序流程",
    ),
    (
    _section_has_line(section, (r"stable delivery|稳定交付", r"only purpose|唯一目的", r"complexity|复杂度"))
    and _section_has_line(section, (r"adding|before adding|新增", r"Agent", r"artifact|产物", r"gate|门禁", r"context|上下文", r"record|记录"))
    and _section_has_line(section, (r"verified risk|failure mode|已核实风险|失败模式", r"factual evidence|事实证据", r"acceptance|验收", r"observable signal|可观测信号", r"removal condition|停用条件"))
    and _section_has_line(section, (r"mapping is absent|without (?:a )?mapping|no mapping|缺任一映射|无映射", r"do not add|must not add|不得启用|不得新增|不得启动")),
    "missing-evidence-based-complexity-policy",
    "缺少稳定交付导向的风险-证据-验收-信号-停用复杂度映射",
    ),
    (
    _section_has_line(section, (r"minimum reliable loop|最小可靠链", r"objective|目标", r"scope|范围", r"non-goals?|非目标", r"acceptance|验收"))
    and _section_has_line(section, (r"smallest implementation|最小实现", r"affected tests?|受影响测试", r"static checks?|静态检查", r"evidence|证据")),
    "missing-minimum-reliable-loop",
    "缺少所有任务必须闭合的最小可靠交付链",
    ),
    (
    _section_has_line(section, (r"small|小型", r"standard|标准", r"high-risk|高风险", r"reason|evidence|原因|依据"))
    and _section_has_line(section, (r"small|小型", r"known impact|影响面已知", r"externally observable|外部可观测", r"contract|契约", r"flow|流程", r"targeted verification|目标验证"))
    and _section_has_line(section, (r"small|小型", r"no extra Agent|starts no extra Agent|does not create a new Agent|不启动额外 Agent|不创建新 Agent", r"prototype|原型", r"swimlane|泳道", r"full multi-artifact chain|完整多产物链"))
    and _section_has_line(section, (r"standard|标准", r"mapped|risk mapping|映射", r"changed behavior|改变行为"))
    and _section_has_line(section, (r"high-risk|高风险", r"multi-Agent|多 Agent", r"concurrent major modules|并发大模块", r"independence|compliance|独立性|合规")),
    "missing-risk-tier-policy",
    "缺少小型最小闭环、标准映射加载与高风险多 Agent 的证据分级规则",
    ),
    (
    _section_has_line(section, (r"change surfaces|变更面", r"behavior-change", r"user-visible", r"ui", r"api", r"standard|标准"))
    and _section_has_line(section, (r"public-api", r"auth", r"security", r"migration", r"persistence", r"async", r"cross-module", r"data-schema", r"high-risk|高风险"))
    and _section_has_line(section, (r"unknown|未知", r"high-risk|高风险", r"investigation|调查", r"until.*disprov|disprov|收敛|排除")),
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
            _section_has_line(
                section,
                (r"only when|只有.*才|仅当", r"system overview|系统总览", r"system|cross-module|系统|跨模块", r"boundary|handoff|entry|exit|边界|交接|入口|出口"),
            ),
            "missing-swimlane-overview-scope-rule",
            "缺少“仅在系统或跨模块边界变化时更新系统总览”的范围规则",
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
                (r"flow_impact", r"none", r"changed", r"uncertain", r"classif|判定|分类"),
            ),
            "missing-swimlane-impact-classification",
            "缺少每次代码模块变化的 none/changed/uncertain 三态泳道影响判定",
        ),
        (
            _section_has_line(
                section,
                (r"flow_impact=changed|flow_impact.*changed", r"stabili[sz]ed candidate|稳定候选", r"batch|合并|批", r"at most once|至多.*一次", r"first downstream consumer|首次.*下游"),
            ),
            "missing-swimlane-batched-update-rule",
            "缺少按模块、阶段和稳定候选合并且首次下游依赖前至多写图一次的规则",
        ),
        (
            _section_has_line(
                section,
                (r"flow_impact=none|flow_impact.*none", r"do not rewrite|不改写", r"content|内容", r"sha-?256|哈希"),
            ),
            "missing-swimlane-no-change-preservation",
            "缺少 none 影响时保留泳道内容和 SHA-256、仅记录新鲜度检查的规则",
        ),
        (
            _section_has_line(
                section,
                (r"flow_impact=uncertain|flow_impact.*uncertain", r"resolve|收敛|解析", r"none", r"changed", r"must not redraw just in case|不得为保险起见重画"),
            ),
            "missing-swimlane-uncertain-resolution",
            "缺少 uncertain 影响先最小调查并收敛、禁止保险式重画的规则",
        ),
        (
            _section_has_line(
                section,
                (r"flow_impact=changed|flow_impact.*changed", r"update|synchron|更新|同步", r"first downstream consumer|首次.*下游|stage|阶段|milestone|里程碑"),
            ),
            "missing-swimlane-sync-rule",
            "缺少确认 changed 后在首次下游依赖或阶段交接前同步泳道的强制规则",
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
            "确认 changed 后在首次下游依赖或阶段交接前的泳道同步不得降级为可选动作",
        ))
    return issues

def _required_swimlane_update_negated(section: str) -> bool:
    trigger = r"flow_impact.{0,20}changed|changed.{0,30}(?:stabili[sz]ed candidate|flow)|first downstream consumer|确认变化|流程变化|稳定候选"
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
    trigger = r"flow_impact.{0,20}changed|changed.{0,30}(?:stabili[sz]ed candidate|flow)|first downstream consumer|确认变化|流程变化|稳定候选"
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
    checks = ((
            _section_has_line(text, (
                r"Kimi", r"DeepSeek", r"disabled|暂停|禁用", r"native-gpt-review-loop",
                r"gpt-5\.6-sol", r"reasoning_effort=high", r"reasoning_effort=xhigh",
            )),
            "missing-native-sol-model-policy",
            "缺少停用外部 provider、改用原生 GPT Sol Skill 及精确模型绑定",
        ),
        (
            _section_has_line(text, (
                r"solution-author|方案", r"black-box-reviewer|黑盒", r"parent GPT|父 GPT|Codex GPT",
                r"independent|独立", r"same candidate|同一候选|same version|同一版本|same hash|同一哈希",
            )),
            "missing-native-sol-role-policy",
            "缺少原生方案、黑盒审查与父 GPT 独立同候选复核职责",
        ),
        (
            _section_has_line(text, (
                r"six candidate versions|six rounds|6 rounds|六轮|6 轮", r"incomplete|未完成",
                r"hash|SHA-256|哈希", r"blocked|阻断",
            )),
            "missing-native-sol-loop-binding-policy",
            "缺少六轮上限、失败状态及同候选哈希门禁",
        ),
        (
            _section_has_line(text, (
                r"read-only|只读", r"only.*(?:Agent|代理).*(?:write|写)|唯一写者",
                r"assigned.*(?:implementation|module maintenance) Agent|指派.*(?:实现|模块维护) Agent|current module maintenance",
                r"Dispatcher", r"must not.*(?:execute|self-certify)|不得.*(?:执行|自证)",
                r"self-report|自报",
                r"black-box execution|黑盒.*执行", r"secrets?|敏感|凭据",
            )),
            "missing-native-sol-authority-policy",
            "缺少子 Agent 只读、获派模块维护 Agent 唯一写入、Dispatcher 不写及真实执行证据边界",
        ),
    )
    issues = [Issue("error", code, message) for matched, code, message in checks if not matched]
    contradiction_patterns = (
        r"gpt-5\.6-sol.{0,80}(?:optional|fallback|substitut|可选|替换|降级)",
        r"solution-author.{0,80}(?:write workspace|modify code|写工作区|修改代码)",
        r"black-box-reviewer.{0,80}(?:write workspace|modify code|写工作区|修改代码)",
        r"(?:parent GPT|父 GPT).{0,80}(?:need not|must not|optional|无需|不必).{0,80}(?:adjudicat|verify|裁决|复核)",
        r"(?:parent GPT\s+(?:runs?|executes?)|父 GPT(?:运行|执行)).{0,50}(?:independent|black-box|acceptance|独立|黑盒|验收).{0,20}(?:gates?|门禁)?",
        r"Dispatcher.{0,80}(?:parent GPT|父 GPT).{0,80}(?:sole.*writer|唯一写者|写入)",
        r"child self-report.{0,40}(?:proves|is sufficient|counts as).{0,30}(?:model|evidence)",
        r"子 Agent 自报.{0,30}(?:可以|可|足以|能够).{0,20}(?:证明|证据)",
    )
    issues.extend(_native_sol_contradiction_issues(text, contradiction_patterns))
    return issues


def _native_sol_contradiction_issues(text: str, patterns: tuple[str, ...]) -> list[Issue]:
    flattened = " ".join(line.strip() for line in text.splitlines())
    if not any(re.search(pattern, flattened, re.IGNORECASE) for pattern in patterns):
        return []
    return [Issue("error", "contradictory-native-sol-policy", "原生 GPT Sol 模型、只读角色、父级裁决和证据边界不得被否定或降级")]
