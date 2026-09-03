from __future__ import annotations

import re

HIERARCHY_WRITER_ACTOR = r"\b(?:main|root|parent|child|subagent)\s+Agent\b|主\s*Agent|父\s*Agent|子\s*Agent"
INDEPENDENT_ROLE = (
    r"\bindependent\b[^.;。；\n]{0,80}?\b(?:Agents?|reviewer|review-author)\b|"
    r"独立[^。；\n]{0,40}?(?:Agent|审查者|评审者|方案作者)"
)
CANONICAL_READ_ONLY_ROLE = (
    r"\b(?:black[ -]?box[ -]?reviewer|acceptance[ -]?reviewer|change[ -]?review[ -]?Agent|"
    r"UI/?UX[ -]?Agent|solution-author|review-author)\b|"
    r"(?:黑盒审查者|验收审查者|变更审查\s*Agent|UI/?UX\s*Agent|方案编写\s*Agent|审查方案作者)"
)
HARD_DENY_WRITER_ACTOR = (
    rf"\bDispatcher\b|{INDEPENDENT_ROLE}|{CANONICAL_READ_ONLY_ROLE}|"
    r"\b(?:another|other)\s+module\s+maintainers?\b|其他模块维护\s*Agent|"
    r"\b(?:coordinator|adjudicator)\b|协调裁决\s*Agent|裁决者|"
    r"协调者(?=\s*(?:可|可以|允许|有权|不得|不能|不可|只读|，|,|。|；|;))"
)
CANONICAL_WRITER_ACTOR = (
    r"\bcurrent\s+canonical\s+(?:module\s+maintainer|implementation\s+(?:Agent|writer))\b|"
    r"\bcurrent\s+module\s+(?:maintainer|implementation\s+Agent)\b|"
    r"当前(?:规范|canonical)?\s*(?:模块维护|实现|实现写入)\s*(?:Agent|者)"
)
NONCANONICAL_WRITER_ACTOR = rf"(?:{HIERARCHY_WRITER_ACTOR})|(?:{HARD_DENY_WRITER_ACTOR})"
WRITER_ACTOR_RE = re.compile(
    rf"(?P<hierarchy>{HIERARCHY_WRITER_ACTOR})|(?P<hard>{HARD_DENY_WRITER_ACTOR})|"
    rf"(?P<canonical>{CANONICAL_WRITER_ACTOR})", re.IGNORECASE,
)
WRITE_GRANT = r"may|can|permission|permitted|allowed|authorized|not\s+prohibited|有权|可|允许"
ENGLISH_WRITE_ACTION = (
    r"(?:writ(?:e|es|ing|ten)|wrote|modif(?:y|ies|ied|ying)|edit(?:s|ted|ting)?|"
    r"implement(?:s|ed|ing)?|updat(?:e|es|ed|ing)|record(?:s|ed|ing)?|"
    r"register(?:s|ed|ing)?|log(?:s|ged|ging)?|append(?:s|ed|ing)?|"
    r"creat(?:e|es|ed|ing)|delet(?:e|es|ed|ing)|overwrit(?:e|es|ing|ten)|overwrote|"
    r"patch(?:es|ed|ing)?|replac(?:e|es|ed|ing)|remov(?:e|es|ed|ing)|"
    r"add(?:s|ed|ing)?|alter(?:s|ed|ing)?)"
)
WRITE_ACTION = (
    rf"\b{ENGLISH_WRITE_ACTION}\b|写入|修改|实现|更新|记录|登记|追加|创建|删除|覆盖|"
    r"打补丁|替换|移除|添加|变更"
)
WRITE_OBJECT = r"artifacts?|tests?|files?|code|records?|module|project|工件|测试|文件|代码|记录|模块|项目"
FORBIDDEN_SCOPE = (
    r"outside\s+(?:the\s+)?(?:(?:registered|exact|current)\s+)?owned\s+paths?|"
    r"(?:another|different|other|sibling)\s+module|cross[ -]?module|"
    r"(?:project[ -]?wide|shared(?:\s+project)?|global(?:\s+shared)?)\s+records?|"
    r"\bfor\s+Agent\s+(?!the\s+current\b)[A-Za-z0-9_-]+|"
    r"\b(?:another|second|additional)\s+(?:active\s+)?(?:writer|lease)\b|"
    r"所有权路径(?:之外|外)|其他模块|别的模块|本模块以外|跨模块|(?:全局|项目)共享记录|"
    r"(?:另一|第二|额外)(?:活动)?(?:写者|租约)|Agent\s*身份不匹配"
)
POLARITY_RE = re.compile(
    r"(?P<negative>\bnot\s+(?:allowed|authorized|permitted)(?:\s+to)?\b|"
    r"\b(?:must\s+not|may\s+not|cannot|can't|never)\b|\binstead\s+of\b|\bread[ -]?only\b|"
    r"不得|不能|不可|不可以|禁止|无权|不允许|只读)|"
    r"(?P<positive>\bnot\s+prohibited(?:\s+from)?\b|\b(?:may|can)\b|"
    r"\b(?:allowed|authorized|permitted)(?:\s+to)?\b|并非禁止|可|可以|允许|有权)", re.IGNORECASE,
)


def hierarchy_write_override(segments: tuple[str, ...]) -> bool:
    return any(_segment_has_override(segment) for segment in _inherit_actor_context(segments))


def _inherit_actor_context(segments: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    previous_actor: str | None = None
    continuation = re.compile(
        rf"\s*(?:(?:it|they|该角色|其)\s*)?(?:remains?\b[^,;。；]{{0,30}}|"
        rf"may|can|allowed|permitted|authorized|可|可以|允许|{WRITE_ACTION})", re.IGNORECASE,
    )
    for segment in segments:
        actors = tuple(WRITER_ACTOR_RE.finditer(segment))
        if not actors and previous_actor and continuation.match(segment):
            segment = f"{previous_actor} {segment}"
            actors = tuple(WRITER_ACTOR_RE.finditer(segment))
        expanded.append(segment)
        if actors:
            previous_actor = actors[-1].group(0)
    return tuple(expanded)


def _segment_has_override(segment: str) -> bool:
    actors = tuple(WRITER_ACTOR_RE.finditer(segment))
    actions = tuple(re.finditer(WRITE_ACTION, segment, re.IGNORECASE))
    for index, action in enumerate(actions):
        clause_start = actions[index - 1].end() if index else 0
        clause_end = actions[index + 1].start() if index + 1 < len(actions) else len(segment)
        clause = segment[clause_start:clause_end]
        target_window = segment[action.end():min(len(segment), action.end() + 100)]
        if not re.search(WRITE_OBJECT, clause + target_window, re.IGNORECASE):
            continue
        grant_prefix = segment[max(clause_start, action.start() - 100):action.start()]
        if not re.search(WRITE_GRANT, clause, re.IGNORECASE) and not re.search(
            WRITE_GRANT, grant_prefix, re.IGNORECASE,
        ):
            continue
        if _action_is_negated(grant_prefix):
            continue
        sentence_boundary = max(
            (match.end() for match in re.finditer(r"[.!?。！？]", segment[:action.start()])),
            default=0,
        )
        relevant = tuple(
            actor for actor in actors if sentence_boundary <= actor.start() < action.start()
        )
        if not relevant:
            continue
        if any(actor.lastgroup == "hard" and not _actor_is_read_only(segment, actor, relevant)
               for actor in relevant):
            return True
        controlled = tuple(actor for actor in relevant if actor.lastgroup in {"hierarchy", "canonical"})
        if controlled and not _legal_writer_implementation(segment):
            return True
    return False


def _actor_is_read_only(segment: str, actor: re.Match[str], actors: tuple[re.Match[str], ...]) -> bool:
    later = next((item for item in actors if item.start() > actor.start()), None)
    end = later.start() if later else len(segment)
    return bool(re.search(r"\bread[ -]?only\b|只读|不得|不可|禁止|无权", segment[actor.end():end], re.IGNORECASE))


def _action_is_negated(prefix: str) -> bool:
    polarities = tuple(POLARITY_RE.finditer(prefix))
    return bool(polarities and polarities[-1].lastgroup == "negative")


def _legal_writer_implementation(text: str) -> bool:
    required = (
        CANONICAL_WRITER_ACTOR,
        r"exact\s+(?:current\s+)?module\s+target|本模块(?:的)?精确目标",
        r"distinct implementation run|独立.*实现.*run",
        r"canonical ownership|canonical.*所有权",
        r"(?:exact\s+)?owned paths?|(?:精确)?所有权路径",
        r"(?:one\s+)?unique active|唯一.*active|唯一.*活动",
        r"local[ -]?coordination|本地协调|host-attested|宿主.*证明",
        r"module lease|模块.*租约",
    )
    return not re.search(FORBIDDEN_SCOPE, text, re.IGNORECASE) and all(
        re.search(pattern, text, re.IGNORECASE) for pattern in required
    )


def _grants_write(text: str) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE) for pattern in (WRITE_GRANT, WRITE_ACTION, WRITE_OBJECT))


def _negates_authority(text: str) -> bool:
    actions = tuple(re.finditer(WRITE_ACTION, text, re.IGNORECASE))
    return bool(actions and all(_action_is_negated(text[:action.start()]) for action in actions))


def _legal_hierarchy_implementation(text: str) -> bool:
    return _legal_writer_implementation(text)
