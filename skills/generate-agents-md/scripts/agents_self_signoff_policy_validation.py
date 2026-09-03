from __future__ import annotations

import re


SELF_SIGNOFF_ACTION_PATTERN = (
    r"(?:\b(?:sign(?:s|ed|ing)?[ -]?off|approv(?:e|es|ed|ing)|accept(?:s|ed|ing)?|certif(?:y|ies|ied|ying)|"
    r"clos(?:e|es|ed|ing)|complet(?:e|es|ed|ing)|finali[sz](?:e|es|ed|ing)|review(?:s|ed|ing)?|"
    r"rubber[ -]?stamp|black[ -]?box(?:\s+tests?)?|acceptance\s+tests?|acceptance\s+testing|"
    r"adjudicat(?:e|es|ed|ing|or|ors|ion|ions)|execut(?:e|es|ed|ing)|run(?:s|ning)?|done)\b|"
    r"\b(?:publish(?:es|ed|ing)?|releas(?:e|es|ed|ing)|issu(?:e|es|ed|ing)\s+"
    r"(?:(?:a|its own|the final acceptance)\s+)?verdict|final\s+approval)\b|"
    r"\bdeclare.{0,60}\b(?:complet(?:e|ed)|done)\b|"
    r"\bmark(?:s|ed|ing)?.{0,60}\bcomplet(?:e|ed)\b|验收|批准|通过|签署|关闭|闭合|完成|审查|"
    r"裁决|黑盒测试|"
    r"\b(?:(?:giv(?:e|es|ing)|gave|given)\s+(?:the\s+)?final\s+approval|final\s+approver|"
    r"final\s+signatory|receiv(?:e|es|ed|ing)\s+(?:the\s+)?final\s+approval|"
    r"own(?:s|ed|ing)?\s+(?:final\s+)?(?:acceptance|release\s+approval|closure)|"
    r"(?:final\s+)?(?:approval|release|closure|acceptance)\s+(?:authority|rights?)|authority)\b|"
    r"审批权|批准权|验收权|发布权|关闭权|发布|宣告.{0,40}完成|标记.{0,40}完成)"
)
ACTION_RE = re.compile(SELF_SIGNOFF_ACTION_PATTERN, re.IGNORECASE)
ACTOR_RE = re.compile(
    r"(?P<maintainer>\b(?:(?:a|an|the)\s+)?(?:module\s+(?:maintainers?|owners?|maintenance\s+Agents?)|"
    r"maintenance\s+Agent|maintainer|implementation owner|implementing Agent|(?<!gate )implementation Agent|"
    r"implementers?|authorized writers?|lease[ -]?holders?)\b|模块维护 Agent|维护 Agent|模块负责人|"
    r"实现负责人|实现 Agent|授权写者|租约持有人|维护者)|"
    r"(?P<dispatcher>(?<![A-Za-z0-9_])(?:the\s+)?Dispatcher(?![A-Za-z0-9_]))|"
    r"(?P<reviewer>\b(?:a|an|the)\s+reviewer\b|审查者)",
    re.IGNORECASE,
)
POLARITY_RE = re.compile(
    r"(?P<positive>\b(?:is\s+)?not\s+(?:prohibited|forbidden)(?:\s+(?:from|to))?\b|"
    r"并非(?:不得|不可|不能|不应|无权|禁止|不允许))|"
    r"(?P<negative>\b(?:is\s+)?not\s+(?:free|entitled|able|allowed|permitted|authorized|granted)(?:\s+to)?\b|"
    r"\b(?:must|may|can|shall|will|does|is)\s+not\b|\bcannot\b|\bcan't\b|"
    r"\b(?:is\s+)?(?:prohibited|forbidden)(?:\s+(?:from|to))?\b|"
    r"\b(?:has\s+)?no\s+authority(?:\s+to)?\b|never|不得|不可|不能|不应|无权|禁止|不允许)|"
    r"(?P<reset>\b(?:but|yet|however)\b|\b(?:may|can|must|shall|will)\b|"
    r"\b(?:is\s+)?(?:free|entitled|able|allowed|permitted|authorized)(?:\s+to)?\b|"
    r"但是|然而|同时|但|而|应|能|有权|获准|可以|允许|(?<!不)可)",
    re.IGNORECASE,
)
OWN_WORK_RE = re.compile(
    r"(?:its own|their own|own delivery|it authored|authored (?:change|implementation)|"
    r"module(?:'s|’s) delivery|自身|自己(?:的)?|其编写|模块的交付)",
    re.IGNORECASE,
)
MODULE_DELIVERY_RE = re.compile(
    r"(?:module(?:'s|’s)? (?:delivery|implementation|acceptance)|模块(?:的)?(?:交付|实现|验收))",
    re.IGNORECASE,
)
REVIEW_CONDITION_RE = re.compile(
    r"(?:not|never)\s+without\s+(?:(?:a|an)\s+)?(?:separate|independent|outside)\s+"
    r"(?:reviewer|review|acceptance)(?=$|[.,;:])|"
    r"(?:only\s+after|subject\s+to|conditioned\s+on|requires?|after)\s+(?:(?:a|an)\s+)?(?:"
    r"(?:successful|completed|passed)\s+independent\s+(?:black-box\s+)?(?:review|acceptance)|"
    r"independent\s+(?:black-box\s+)?(?:review|acceptance)\s+(?:has\s+)?(?:passed|completed|succeeded)|"
    r"completed\s+independent\s+review\s+with\s+a\s+passing\s+verdict)"
    r"(?:\s+by\s+(?:(?:a|an)\s+)?(?:another|different|independent|outside)\s+(?:read-only\s+Agent|reviewer))?"
    r"(?=$|[.,;:])|"
    r"(?:不得|不可|不能|禁止)\s*(?:在)?\s*无(?:需)?(?:独立|外部|单独)审查(?:时|的情况下)|"
    r"(?:必须|须|需要)\s*(?:先)?(?:经过并通过\s*(?:独立|外部|单独)审查|"
    r"经\s*(?:独立|外部|单独)(?:审查通过|验收成功))后?(?:才能|方可)?|"
    r"仅在\s*(?:独立|外部|单独)(?:审查通过|验收成功)后(?:才能|方可)?",
    re.IGNORECASE,
)
CONTROL_OBJECT_RE = re.compile(
    r"(?P<intrinsic>\b(?:prevent(?:s|ed|ing)?|forbid(?:s|ding)?|forbade|forbidden|"
    r"block(?:s|ed|ing)?|disallow(?:s|ed|ing)?|stop(?:s|ped|ping)?)\s+"
    r"(?:(?:a|an|the|neither)\s+)?)$|"
    r"(?P<authority>\b(?:allow(?:s|ed|ing)?|permit(?:s|ted|ting)?|authoriz(?:e|es|ed|ing)|"
    r"ask(?:s|ed|ing)?|instruct(?:s|ed|ing)?)\s+(?:(?:a|an|the|neither)\s+)?)$|"
    r"(?P<cn_intrinsic>禁止|不允许|阻止)\s*$|(?P<cn_authority>允许|授权|要求|指示)\s*$",
    re.IGNORECASE,
)
CONTROL_NEGATION_RE = re.compile(
    r"(?:\b(?:must|may|can|shall|will|does|is)\s+not|\bcannot|\bcan't|\bnever|"
    r"\b(?:is\s+)?not\s+(?:allowed|permitted|authorized)(?:\s+to)?|不得|不可|不能|不应|无权|(?:并)?不)\s*$",
    re.IGNORECASE,
)
CONTROL_FAILURE_RE = re.compile(r"(?:\bfails?\s+to|未能)\s*$", re.IGNORECASE)
ACTOR_RELATION_RE = re.compile(
    r"(?P<passive>\bby|由)|(?P<ownership>\bbelong(?:s|ed|ing)?\s+to|归)|"
    r"(?P<source>\bfrom|从)|(?P<authority>\bunder\s+(?:the\s+)?authority\s+of)",
    re.IGNORECASE,
)
RELATION_NEGATION_RE = re.compile(r"(?:\b(?:does|did|is|was)\s+not|\bnever|不)\s*$", re.IGNORECASE)
DIRECT_ACTION_NEGATION_RE = re.compile(r"(?:\b(?:has|holds|possesses|owns)\s+)?no\s*$|无(?:最终)?\s*$", re.IGNORECASE)
GLOBAL_FINAL_AUTHORITY_RE = re.compile(
    r"(?:(?:final\s+)?(?:approval|release|closure|acceptance)\s+(?:authority|rights?)|"
    r"final\s+(?:approver|signatory)|(?:最终)?(?:审批|批准|验收|发布|关闭)权)", re.IGNORECASE,
)
RESULT_RECORD_RE = re.compile(
    r"(?:\b(?:may|can)\s+(?:record|register|log)\b|可以(?:记录|登记)|可(?:记录|登记))",
    re.IGNORECASE,
)
INDEPENDENTLY_PASSED_RE = re.compile(
    r"(?:\bindependently[ -]+passed\b|\bpassed\s+independently\b|(?:已经|已)?独立通过)", re.IGNORECASE,
)
GATE_RESULT_RE = re.compile(
    r"(?:\b(?:review|black[ -]?box|adjudication|acceptance)[ -]+(?:result|verdict)\b|"
    r"\b(?:result|verdict)\s+of\s+(?:the\s+)?(?:acceptance\s+)?review\b|"
    r"(?:审查|黑盒|裁决|验收)(?:测试)?(?:结果|结论))",
    re.IGNORECASE,
)
def allows_implementation_self_signoff(segments: tuple[str, ...]) -> bool:
    expanded = _inherit_continuation_actor(segments)
    return any(
        _passive_scope_allows_prohibited_action(segment)
        or any(_scope_allows_prohibited_action(actor, scope, inherited_negation)
               for actor, scope, inherited_negation in _actor_scopes(segment))
        for segment in expanded
    )


def _inherit_continuation_actor(segments: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    previous_maintainer = False
    for segment in segments:
        has_actor = bool(ACTOR_RE.search(segment))
        continuation = bool(re.match(
            r"\s*(?:(?:it|they|its|their|该角色|其)\s*)?"
            r"(?:then|and|while|may|can|allowed|permitted|authorized|然后|并|同时|可|可以|允许)",
            segment, re.IGNORECASE,
        ))
        if not has_actor and previous_maintainer and continuation:
            segment = "The module maintainer " + segment
        expanded.append(segment)
        previous_maintainer = any(match.lastgroup == "maintainer" for match in ACTOR_RE.finditer(segment))
    return tuple(expanded)


def _actor_scopes(segment: str) -> tuple[tuple[str, str, bool], ...]:
    matches = tuple(ACTOR_RE.finditer(segment))
    return tuple(
        (
            match.lastgroup or "",
            segment[match.start():matches[index + 1].start() if index + 1 < len(matches) else len(segment)],
            _controller_negates(segment[matches[index - 1].end() if index else 0:match.start()])
            or _coordinated_actor_negates(segment, matches, index),
        )
        for index, match in enumerate(matches)
    )


def _scope_allows_prohibited_action(actor: str, scope: str, inherited_negation: bool = False) -> bool:
    if actor == "maintainer":
        return _maintainer_scope_allows_self_signoff(scope, inherited_negation)
    if actor == "dispatcher":
        return _dispatcher_scope_allows_closure(scope, inherited_negation)
    return False


def _maintainer_scope_allows_self_signoff(scope: str, inherited_negation: bool) -> bool:
    if not OWN_WORK_RE.search(scope) and not GLOBAL_FINAL_AUTHORITY_RE.search(scope):
        return False
    actions = _action_matches(scope)
    return any(not inherited_negation and not _action_is_negated(scope, action.start()) for action in actions)


def _safe_independent_result_spans(scope: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for record in RESULT_RECORD_RE.finditer(scope):
        clause_end_match = re.search(r"[.;。；]", scope[record.end():])
        clause_end = record.end() + clause_end_match.start() if clause_end_match else len(scope)
        result = GATE_RESULT_RE.search(scope, record.end(), clause_end)
        passed = INDEPENDENTLY_PASSED_RE.search(scope, record.end(), clause_end)
        if result and passed:
            spans.append((record.start(), max(result.end(), passed.end())))
    return tuple(spans)


def _dispatcher_scope_allows_closure(scope: str, inherited_negation: bool) -> bool:
    if not MODULE_DELIVERY_RE.search(scope):
        return False
    return any(not inherited_negation and not _action_is_negated(scope, action.start())
               for action in _action_matches(scope))


def _controller_negates(prefix: str) -> bool:
    controller = CONTROL_OBJECT_RE.search(prefix)
    if not controller:
        return False
    before = prefix[:controller.start()]
    directly_negated = bool(CONTROL_NEGATION_RE.search(before))
    if controller.lastgroup in {"intrinsic", "cn_intrinsic"}:
        return not directly_negated and not CONTROL_FAILURE_RE.search(before)
    return "neither" in controller.group(0).casefold() or directly_negated


def _coordinated_actor_negates(segment: str, actors: tuple[re.Match[str], ...], index: int) -> bool:
    before = segment[actors[index - 1].end() if index else 0:actors[index].start()]
    if re.search(r"\bneither(?:\s+the)?\s*$", before, re.IGNORECASE):
        return True
    return bool(index and re.search(r"\bnor(?:\s+the)?\s*$", before, re.IGNORECASE)
                and re.search(r"\bneither\b", segment[:actors[index - 1].start()], re.IGNORECASE))


def _passive_scope_allows_prohibited_action(segment: str) -> bool:
    actors = tuple(ACTOR_RE.finditer(segment))
    for index, actor in enumerate(actors):
        object_pattern = OWN_WORK_RE if actor.lastgroup == "maintainer" else MODULE_DELIVERY_RE
        if actor.lastgroup not in {"maintainer", "dispatcher"}:
            continue
        objects = tuple(object_pattern.finditer(segment, 0, actor.start()))
        if not objects:
            continue
        between = segment[objects[-1].end():actor.start()]
        relation = ACTOR_RELATION_RE.search(between)
        chinese_authority = between.rstrip().endswith("在") and re.match(r"\s*授权下", segment[actor.end():])
        if not chinese_authority and (not relation or relation.end() != len(between.rstrip())):
            continue
        end = actors[index + 1].start() if index + 1 < len(actors) else len(segment)
        start = actors[index - 1].end() if index else 0
        predicate = segment[start:end]
        actions = _action_matches(predicate)
        relation_negated = bool(
            relation and relation.lastgroup == "ownership"
            and RELATION_NEGATION_RE.search(between, 0, relation.start())
        )
        if any(not relation_negated and not _action_is_negated(predicate, action.start()) for action in actions):
            return True
    return False


def _action_matches(scope: str) -> tuple[re.Match[str], ...]:
    matches: list[re.Match[str]] = []
    conditions = tuple(REVIEW_CONDITION_RE.finditer(scope))
    safe_records = _safe_independent_result_spans(scope)
    for match in ACTION_RE.finditer(scope):
        if any(start <= match.start() and match.end() <= end for start, end in safe_records):
            continue
        if any(condition.start() <= match.start() and match.end() <= condition.end() for condition in conditions):
            continue
        if match.group(0).casefold() in {"review", "审查"}:
            prefix = scope[max(0, match.start() - 16):match.start()]
            if re.search(r"(?:independent|separate|outside)\s+$|(?:独立|外部|单独)$", prefix, re.IGNORECASE):
                continue
        matches.append(match)
    return tuple(matches)


def _action_is_negated(scope: str, action_start: int) -> bool:
    if DIRECT_ACTION_NEGATION_RE.search(scope, 0, action_start):
        return True
    polarities = tuple(POLARITY_RE.finditer(scope, 0, action_start))
    return bool(polarities and polarities[-1].lastgroup == "negative")


def _conditioned_action_indexes(scope: str, actions: tuple[re.Match[str], ...]) -> set[int]:
    conditioned: set[int] = set()
    for condition in REVIEW_CONDITION_RE.finditer(scope):
        if not actions:
            break
        index = min(range(len(actions)), key=lambda item: _action_condition_distance(actions[item], condition))
        conditioned.add(index)
        before = [item for item, action in enumerate(actions) if action.end() <= condition.start()]
        after = [item for item, action in enumerate(actions) if condition.end() <= action.start()]
        if before and after and _action_key(actions[before[-1]]) == _action_key(actions[after[0]]):
            conditioned.update((before[-1], after[0]))
    return conditioned


def _action_key(action: re.Match[str]) -> str:
    value = action.group(0).casefold()
    for key in ("approv", "accept", "certif", "clos", "complet", "finali", "review"):
        if key in value:
            return key
    return value


def _action_condition_distance(action: re.Match[str], condition: re.Match[str]) -> tuple[int, int]:
    if action.end() <= condition.start():
        return condition.start() - action.end(), 0
    if condition.end() <= action.start():
        return action.start() - condition.end(), 1
    return 0, 0
