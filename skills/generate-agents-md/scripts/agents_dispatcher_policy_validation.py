from __future__ import annotations

import re

from agents_policy_common import (
    DISPATCHER_OWNERSHIP_HEADING_RE,
    PLACEHOLDER_RE,
    Issue,
    extract_heading_section,
    section_has_line,
)
from agents_self_signoff_policy_validation import (
    allows_implementation_self_signoff as _allows_implementation_self_signoff,
)
from write_authority_policy_validation import hierarchy_write_override


TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
RUNTIME_ID_RE = re.compile(
    r"(?:\b(?:thread|session|run)(?:[ _-]?id)?\s*[:=_-]\s*[A-Za-z0-9][A-Za-z0-9_-]{7,}\b)"
    r"|(?:\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b)",
    re.IGNORECASE,
)
MARKDOWN_CODE_SPAN_RE = re.compile(r"`([^`\r\n]+)`")
OWNED_PATH_RE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/?")
OWNED_PATH_CELL_RE = re.compile(r"\s*`[^`\r\n]+`\s*(?:,\s*`[^`\r\n]+`\s*)*")


def validate_dispatcher_ownership_policy(text: str, *, mode: str) -> list[Issue]:
    section = extract_heading_section(text, DISPATCHER_OWNERSHIP_HEADING_RE)
    if section is None:
        return [Issue(
            "error",
            "missing-dispatcher-ownership-section",
            "缺少 Dispatcher 与稳定模块维护 Agent 所有权章节",
        )]

    issues = _validate_mapping(section, mode=mode)
    issues.extend(
        Issue("error", code, message)
        for matched, code, message in _policy_checks(section)
        if not matched
    )
    issues.extend(_dispatcher_contradictions(text))
    return issues


def _policy_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        _module_closure_checks(section)
        + _dispatcher_role_checks(section)
        + _handoff_lifecycle_checks(section)
    )


def _module_closure_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return _module_identity_checks(section) + _module_acceptance_checks(section)


def _module_identity_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        (
            section_has_line(section, (
                r"major functional module|大功能模块|主要功能模块",
                r"stable business capability|稳定.*业务能力",
                r"independently testable entry|独立.*测试.*入口",
                r"output contract|输出契约",
                r"non-overlapping ownership boundary|不重叠.*边界",
                r"helpers|辅助|临时.*切片",
                r"do not create|不.*创建|无需.*创建",
            )),
            "missing-major-module-definition",
            "缺少大功能模块的稳定能力、可测入口输出和非重叠边界定义，或未限制辅助文件导致 Agent 膨胀",
        ),
        (
            section_has_line(section, (
                r"every major functional module|每个.*大功能模块|每个.*主要功能模块",
                r"one independent long-term maintenance Agent|独立.*长期维护 Agent",
                r"requirement|需求",
                r"design|flow|设计|流程",
                r"implementation|实现",
                r"targeted tests?|定向测试",
                r"independent black-box acceptance|独立.*黑盒.*验收",
                r"evidence|log|swimlane|证据|日志|泳道",
                r"before.*complet|完成前|闭环",
            )),
            "missing-major-module-closed-loop",
            "缺少每个大功能模块由独立长期维护 Agent 负责的需求到验收与维护闭环",
        ),
    )


def _module_acceptance_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        (
            section_has_line(section, (
                r"module maintenance Agent|模块维护 Agent",
                r"sole writer|唯一写者",
                r"must not self-certify|不得自证|禁止自验",
                r"review|acceptance|审查|验收",
                r"different independent read-only Agent|不同.*独立.*只读 Agent",
                r"same code/build identity|相同.*代码.*构建",
            )),
            "missing-module-independent-acceptance",
            "缺少模块维护 Agent 可单写实现但不得自证、由不同只读 Agent 绑定同一构建验收的隔离规则",
        ),
        (
            section_has_line(section, (
                r"cross-module|system completion|跨模块|系统完成",
                r"every affected module|each module|每个.*受影响模块",
                r"requirement IDs?|需求 ID",
                r"code/build|代码.*构建",
                r"targeted tests?|定向测试",
                r"independent acceptance|独立验收",
                r"run/latest|run.*latest|运行.*最新",
                r"swimlane evidence|泳道证据",
                r"no open finding|无.*开放.*问题|没有.*未关闭",
            )),
            "missing-system-module-closure-gate",
            "缺少系统完成前逐一关闭所有受影响模块及其当前证据的聚合门禁",
        ),
    )


def _dispatcher_role_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        (
            _has_only_user_entry(section) and section_has_line(section, (
                r"user.*(?:entry|入口)|用户.*(?:entry|入口)",
                r"decompos|拆解",
                r"rout|路由|派工",
                r"orchestrat|编排",
                r"new module|新模块",
            )),
            "missing-dispatcher-entry-role",
            "Dispatcher 必须是用户入口并只负责拆解、路由、编排和新模块 Agent 创建",
        ),
        (
            section_has_line(section, (
                r"Dispatcher",
                r"must not|excludes|不得|禁止|排除",
                r"business code|业务代码",
                r"shared.*records?|共享.*记录",
            )),
            "missing-dispatcher-no-write-boundary",
            "缺少 Dispatcher 禁止修改业务代码和共享记录的边界",
        ),
        (
            section_has_line(section, (
                r"exactly one|恰好一个|唯一",
                r"implementation Agent|实现 Agent",
                r"writer|写者",
                r"other|其余|其他",
                r"read-only|只读",
            )),
            "missing-task-single-writer-boundary",
            "缺少每项任务唯一实现 Agent 及其他 Agent 只读规则",
        ),
    )


def _has_only_user_entry(section: str) -> bool:
    patterns = (
        r"(?:only|sole).{0,30}(?:user(?:'s)?\s+)?entry point",
        r"user(?:'s)?\s+(?:only|sole)\s+entry point",
        r"用户.{0,12}唯一.{0,12}入口|唯一.{0,12}用户.{0,12}入口",
    )
    return any(re.search(pattern, section, re.IGNORECASE) for pattern in patterns)


def _handoff_lifecycle_checks(section: str) -> tuple[tuple[bool, str, str], ...]:
    return (
        (
            _has_context_packet(section),
            "missing-dispatcher-context-packet",
            "缺少 Dispatcher 向模块 Agent 传递最小充分上下文的完整字段",
        ),
        (
            section_has_line(section, (r"need not|无需|不必", r"repeat|重复", r"request|请求"))
            and section_has_line(section, (
                r"must not|excludes|不得|禁止|排除",
                r"full chat|完整聊天",
                r"unrelated|无关",
                r"reasoning|推理",
            )),
            "missing-context-minimization-boundary",
            "缺少用户免重复与禁止传递完整聊天、无关历史和其他 Agent 推理的规则",
        ),
        (
            section_has_line(section, (
                r"Dispatcher",
                r"full-flow|end-to-end|全流程",
                r"orchestrat|编排|组织",
            )) and section_has_line(section, (
                r"Dispatcher", r"read-only|只读", r"self-certif|自证",
            )) and section_has_line(section, (r"independent|独立", r"read-only|只读", r"gate|门禁")),
            "missing-independent-validation-orchestration",
            "缺少 Dispatcher 编排独立只读全流程验证且不得自证的规则",
        ),
        (
            _has_new_module_protocol(section),
            "missing-new-module-agent-protocol",
            "缺少稳定新模块先建立唯一边界和长期维护 Agent 再实现的协议",
        ),
        (
            section_has_line(section, (
                r"stable.*title|稳定.*标题",
                r"thread|session",
                r"runtime|运行时",
                r"must not|不得|禁止",
                r"AGENTS\.md|this file|本文件",
            )),
            "missing-runtime-id-separation",
            "缺少稳定 Agent 标题与易变 thread/session ID 的持久化隔离规则",
        ),
    )


def _has_context_packet(section: str) -> bool:
    flattened = _context_packet_text(section)
    groups = (
        r"user goal|用户目标",
        r"approved requirements?|批准.*需求",
        r"constraints?|约束",
        r"affected modules?|影响模块",
        r"boundar(?:y|ies)|边界",
        r"input/output contracts?|输入.?输出.*契约",
        r"dependencies?|依赖",
        r"risks?|风险",
        r"verification|验证",
        r"acceptance|验收",
        r"paths?|路径",
        r"evidence|证据",
    )
    return all(re.search(pattern, flattened, re.IGNORECASE) for pattern in groups)


def _context_packet_text(section: str) -> str:
    lines = section.splitlines()
    marker = re.compile(r"context packet|handoff packet|上下文.*(?:包|交接)|交接包", re.IGNORECASE)
    for index, line in enumerate(lines):
        if not marker.search(line):
            continue
        selected: list[str] = []
        for candidate in lines[index:]:
            if selected and (candidate.startswith("- ") or candidate.startswith("### ")):
                break
            selected.append(candidate.strip())
        return " ".join(selected)
    return ""


def _has_new_module_protocol(section: str) -> bool:
    flattened = " ".join(line.strip() for line in section.splitlines())
    groups = (
        r"new module|新模块",
        r"unique module key|唯一.*模块键|不复用.*模块",
        r"name|名称",
        r"boundar(?:y|ies)|边界",
        r"long-term maintenance Agent|长期维护 Agent",
        r"session|会话",
        r"register|登记",
        r"before implementation|实现前|不得开始实现",
        r"non-overlap|不重叠",
        r"ownership|所有权",
    )
    return all(re.search(pattern, flattened, re.IGNORECASE) for pattern in groups)


def _validate_mapping(section: str, *, mode: str) -> list[Issue]:
    table = _first_markdown_table(section)
    if table is None:
        return [Issue("error", "missing-module-agent-map", "缺少模块、边界和稳定维护 Agent 标题映射表")]
    headers, rows = table
    indexes = _mapping_indexes(headers)
    if indexes is None:
        return [Issue("error", "invalid-module-agent-map", "模块所有权映射表必须唯一包含模块、范围、拥有路径/边界和维护 Agent 标题列")]
    if not rows:
        return [Issue("error", "empty-module-agent-map", "模块所有权映射表至少需要一个模块行")]
    issues: list[Issue] = []
    seen_modules: set[str] = set()
    seen_titles: set[str] = set()
    seen_boundaries: set[str] = set()
    seen_paths: set[str] = set()
    for row in rows:
        if len(row) != len(headers) or any(not row[index].strip() for index in indexes.values()):
            issues.append(Issue("error", "invalid-module-agent-row", "模块映射行必须完整填写模块、范围、边界和稳定维护 Agent 标题"))
            continue
        module = row[indexes["module"]].strip().casefold()
        title = row[indexes["title"]].strip()
        raw_boundary = row[indexes["ownership"]].strip()
        boundary = _boundary_identity(raw_boundary)
        if module in seen_modules or title.casefold() in seen_titles:
            issues.append(Issue("error", "duplicate-module-agent-owner", "模块键和稳定维护 Agent 标题必须一一唯一"))
        seen_modules.add(module)
        seen_titles.add(title.casefold())
        if boundary in seen_boundaries:
            issues.append(Issue("error", "duplicate-module-agent-boundary", "模块拥有路径/边界不得静默重复"))
        seen_boundaries.add(boundary)
        owned_paths, valid_paths = _parse_owned_paths(raw_boundary)
        is_public_placeholder = mode == "public-template" and PLACEHOLDER_RE.search(raw_boundary)
        if not is_public_placeholder and (not valid_paths or not owned_paths):
            issues.append(Issue(
                "error", "invalid-module-agent-boundary-path",
                "模块机器所有权必须至少包含一个反引号包裹的项目相对路径；多个路径用逗号分隔且不得混用裸文本",
            ))
        if any(_paths_overlap(path, previous) for path in owned_paths for previous in seen_paths):
            issues.append(Issue("error", "overlapping-module-agent-boundary", "模块拥有路径不得存在父子或等价重叠"))
        seen_paths.update(owned_paths)
        if RUNTIME_ID_RE.search(title):
            issues.append(Issue("error", "runtime-id-in-stable-agent-title", "稳定维护 Agent 标题不得包含 thread/session/run ID"))
    if mode == "public-template":
        joined = " ".join(" ".join(row) for row in rows)
        for placeholder in ("MODULE_KEY", "MODULE_SCOPE", "MODULE_OWNED_BOUNDARY", "MODULE_AGENT_TITLE"):
            if f"{{{{{placeholder}}}}}" not in joined:
                issues.append(Issue("error", "missing-module-agent-placeholder", f"公共模板缺少 {{{{{placeholder}}}}} 占位符"))
    elif any(PLACEHOLDER_RE.search(cell) for row in rows for cell in row):
        issues.append(Issue("error", "unresolved-module-agent-map", "项目模式的模块所有权映射不得保留占位符"))
    return issues


def module_ownership_mapping(text: str) -> dict[str, tuple[tuple[str, ...], str]]:
    section = extract_heading_section(text, DISPATCHER_OWNERSHIP_HEADING_RE)
    if section is None:
        return {}
    table = _first_markdown_table(section)
    if table is None:
        return {}
    headers, rows = table
    indexes = _mapping_indexes(headers)
    if indexes is None:
        return {}
    result: dict[str, tuple[tuple[str, ...], str]] = {}
    for row in rows:
        if len(row) != len(headers):
            return {}
        module = row[indexes["module"]].strip().casefold()
        title = row[indexes["title"]].strip()
        paths, valid_paths = _parse_owned_paths(row[indexes["ownership"]])
        if not module or not title or not valid_paths or not paths or module in result:
            return {}
        result[module] = (paths, title)
    return result


def _mapping_indexes(headers: list[str]) -> dict[str, int] | None:
    normalized = [re.sub(r"\s+", " ", value.strip()).casefold() for value in headers]
    required = {
        "module": ("module", "模块"),
        "scope": ("scope", "职责", "范围"),
        "ownership": ("owned path", "owned project-relative path", "ownership", "boundary", "拥有路径", "所有权", "边界"),
        "title": ("agent title", "maintenance agent", "维护 agent", "agent 标题"),
    }
    indexes: dict[str, int] = {}
    for key, aliases in required.items():
        matches = [index for index, header in enumerate(normalized) if any(alias in header for alias in aliases)]
        if len(matches) != 1:
            return None
        indexes[key] = matches[0]
    return indexes


def _boundary_identity(value: str) -> str:
    without_code_markup = MARKDOWN_CODE_SPAN_RE.sub(r"\1", value)
    return re.sub(r"\s+", " ", without_code_markup.strip()).casefold()


def _parse_owned_paths(value: str) -> tuple[tuple[str, ...], bool]:
    if not OWNED_PATH_CELL_RE.fullmatch(value):
        return (), False
    paths: list[str] = []
    for raw in MARKDOWN_CODE_SPAN_RE.findall(value):
        candidate = raw.strip()
        if "\\" in candidate or "//" in candidate or not OWNED_PATH_RE.fullmatch(candidate):
            return (), False
        without_trailing = candidate[:-1] if candidate.endswith("/") else candidate
        parts = without_trailing.split("/")
        if not without_trailing or any(part in {"", ".", ".."} for part in parts):
            return (), False
        canonical = "/".join(parts)
        if candidate not in {canonical, canonical + "/"}:
            return (), False
        paths.append(canonical)
    unique = tuple(dict.fromkeys(paths))
    return unique, bool(unique)


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _first_markdown_table(section: str) -> tuple[list[str], list[list[str]]] | None:
    lines = section.splitlines()
    for index in range(len(lines) - 1):
        headers = _table_cells(lines[index])
        separators = _table_cells(lines[index + 1])
        if not headers or len(headers) != len(separators):
            continue
        if not all(TABLE_SEPARATOR_RE.fullmatch(cell.strip()) for cell in separators):
            continue
        rows: list[list[str]] = []
        for line in lines[index + 2:]:
            cells = _table_cells(line)
            if not cells:
                break
            rows.append(cells)
        return headers, rows
    return None


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _dispatcher_contradictions(section: str) -> list[Issue]:
    flattened = " ".join(line.strip() for line in section.splitlines())
    patterns = (
        r"Dispatcher.{0,60}(?:has|holds|possesses).{0,30}(?:write|edit|modify).{0,30}(?:authority|access|permission).{0,60}(?:business code|shared.*records?|业务代码|共享.*记录)",
        r"Dispatcher.{0,80}(?:may|can|可以|允许).{0,50}(?:edit|modify|write|修改|写入).{0,60}(?:business code|shared.*records?|业务代码|共享.*记录)",
        r"(?:multiple|more than one|多个|多名).{0,50}(?:implementation Agents?|实现 Agent).{0,50}(?:write|写入|修改)",
        r"(?:other Agents?|其他 Agent|其余 Agent).{0,50}(?:may|can|可以|允许).{0,30}(?:also\s+)?(?:write|edit|写入|修改).{0,60}(?:code|records?|代码|记录)",
        r"(?:thread|session).{0,20}ID.{0,80}(?:store|persist|write|记录|写入).{0,50}AGENTS\.md",
        r"(?:new module|新模块).{0,80}(?:may|can|可以|允许).{0,30}(?:implement|实现).{0,50}(?:before|先于|之前).{0,50}(?:owner|ownership|session|所有权|会话)",
        r"(?:module maintenance Agent|模块维护 Agent).{0,80}(?:may|can|allowed|permitted|可以|允许).{0,30}(?:self-certif|self-accept|自证|自验).{0,60}(?:implementation|acceptance|review|实现|验收|审查)",
        r"(?:system|cross-module|系统|跨模块).{0,30}(?:completion|完成).{0,80}(?:may|can|allowed|permitted|可以|允许).{0,40}(?:while|before|即使|先于).{0,60}(?:affected module|受影响模块).{0,30}(?:open|unclosed|未关闭|开放)",
        r"(?:module|模块).{0,40}(?:closure|闭环).{0,60}(?:optional|advisory|skippable|obsolete|可选|可跳过|过时)",
        r"(?:every affected module|所有受影响模块|每个受影响模块).{0,80}(?:optional|advisory|skippable|not required|可选|可跳过|非必需)",
        r"(?:module maintenance Agent|模块维护 Agent).{0,80}(?:entitled|authorized|permitted).{0,50}(?:approve|accept|review|批准|验收|审查).{0,40}(?:its own|自身|自己的).{0,40}(?:implementation|review|实现|审查)",
        r"(?:preceding|previous|above|foregoing|前述|上述|上一条).{0,30}(?:rule|requirement|policy|规则|要求|策略).{0,40}(?:discretionary|optional|advisory|need not be followed|not mandatory|可选|酌情|无需遵守)",
        r"(?:module )?maintainer.{0,40}(?:empowered|entitled|authorized|permitted|allowed|有权|获准).{0,35}(?:sign[ -]?off|approve|accept|验收|批准).{0,35}(?:its own|their own|自身|自己的).{0,35}(?:delivery|implementation|交付|实现)",
    )
    semantic_groups = (
        (r"Dispatcher", r"may|can|allowed|permitted|authorized|granted|free to|可以|允许|授权", r"edit|modify|alter|write|written|修改|写入|变更", r"business code|shared.*records?|业务代码|共享.*记录"),
        (r"other Agents?|其他 Agent|其余 Agent", r"may|can|allowed|permitted|authorized|granted|可以|允许|授权", r"write|edit|modify|access|写入|修改", r"code|records?|代码|记录"),
        (r"another|second|additional|alternate|另一个|第二个|额外", r"user(?:'s)?\s+entry point|用户.*入口"),
        (r"another|second|additional|alternate|另一个|第二个|额外", r"Agents?|代理", r"may|can|allowed|permitted|可以|允许", r"accept|receive|handle|接受|接收|处理", r"user.*requests?|用户.*(?:请求|需求)"),
    )
    segments = _policy_segments(section)
    has_semantic_contradiction = any(
        _has_all(segment, groups) and not _negates_authority(segment)
        for segment in segments
        for groups in semantic_groups
    )
    if (any(re.search(pattern, flattened, re.IGNORECASE) for pattern in patterns)
            or has_semantic_contradiction or _reverses_new_module_order(segments)
            or _weakens_module_closure(segments) or hierarchy_write_override(segments)
            or _allows_implementation_self_signoff(segments)):
        return [Issue("error", "contradictory-dispatcher-policy", "Dispatcher、单写者或运行时 ID 规则包含反向授权")]
    return []


def _policy_segments(section: str) -> tuple[str, ...]:
    return tuple(segment.strip() for segment in re.split(r"(?<=[.!?。！？;；])\s*|\n+", section) if segment.strip())

def _has_all(text: str, patterns: tuple[str, ...]) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _weakens_module_closure(segments: tuple[str, ...]) -> bool:
    subject = re.compile(
        r"(?:module.{0,30}closure|模块.{0,20}闭环|requirement[- ]to[- ]acceptance|"
        r"需求.{0,20}验收|maintenance loop|维护闭环|this (?:entire )?requirement|"
        r"该(?:完整)?要求|described above)", re.IGNORECASE,
    )
    weakening = re.compile(
        r"(?:optional|advisory|skippable|may be skipped|can be skipped|may ignore|"
        r"can ignore|free to disregard|may disregard|can disregard|waive|bypass|"
        r"opt out|need not comply|nonbinding|non-binding|"
        r"dispense with|exempt from|set aside|"
        r"可选|建议性|可跳过|可以跳过|可以忽略|可以放弃|可以绕过|无需遵守|不具约束力)", re.IGNORECASE,
    )
    negated = re.compile(
        r"(?:not|never|must not|cannot|can't|不得|不可|禁止).{0,16}"
        r"(?:optional|advisory|skippable|skip|ignore|可选|建议性|跳过|忽略)",
        re.IGNORECASE,
    )
    return any(subject.search(item) and weakening.search(item) and not negated.search(item) for item in segments)
def _negates_authority(text: str) -> bool:
    return bool(re.search(r"must not|may not|cannot|not (?:allowed|permitted|authorized|granted)|never|不得|禁止|不允许", text, re.IGNORECASE))

def _reverses_new_module_order(segments: tuple[str, ...]) -> bool:
    required = (r"new module|新模块", r"may|can|allowed|permitted|authorized|granted|可以|允许|授权")
    temporal_reversal = (
        r"(?:implementation|implement|实现).{0,60}(?:before|先于|之前).{0,60}(?:owner|ownership|session|所有权|会话)",
        r"(?:before|先于|之前).{0,60}(?:owner|ownership|session|所有权|会话).{0,60}(?:implementation|implement|实现)",
    )
    return any(_has_all(segment, required) and not _negates_authority(segment)
               and any(re.search(pattern, segment, re.IGNORECASE) for pattern in temporal_reversal)
               for segment in segments)
