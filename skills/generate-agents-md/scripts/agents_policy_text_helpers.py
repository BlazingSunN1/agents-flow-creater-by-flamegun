from __future__ import annotations

import re


def default_context_expands_workset(clause: str) -> bool:
    broad = (
        r"whole[- ]repository|entire\s+repository|(?:entire|complete|whole|full)\s+"
        r"(?:codebase|source\s+tree)|all\s+(?:repository\s+)?"
        r"(?:files|history|logs|documentation)|latest\.md|old\s+runs?|raw\s+logs?"
        r"|全仓|全部文件|全部历史|原始日志"
    )
    load = r"load(?:ed|s|ing)?|include(?:d|s|ing)?|read(?:s|ing)?|ingest(?:ed|s|ing)?|加载|读取|包含"
    default = r"by\s+default|default(?:ly)?|默认"
    return bool(
        (re.search(rf"(?i)(?:{default}).{{0,80}}(?:{load})", clause)
         and re.search(rf"(?i)(?:{broad})", clause))
        or re.search(rf"(?i)(?:{default}).{{0,80}}(?:{load}).{{0,100}}(?:{broad})", clause)
        or re.search(rf"(?i)(?:{broad}).{{0,100}}(?:{load}).{{0,80}}(?:{default})", clause)
    )


def without_prohibited_agent_roles(clause: str) -> str:
    prohibition = (
        r"\b(?:must|should|shall|may|can)\s+(?:not|never)\b"
        r"|\b(?:do|does)\s+not\b|\bnever\b"
        r"|不得|不应(?:该)?|禁止|不允许|无需|不需要|不要"
    )
    boundary = (
        r"[.;!?。；！？]|\b(?:but|however|instead|except)\b|但|不过|然而"
        r"|\b(?:and|or)\s+(?:must|should|shall|may|can|start|launch|create|add|require)\b"
        r"|并(?:且)?(?:必须|需要|启动|创建|增加)"
    )
    role = (
        r"\b[A-Z][A-Z0-9_]+(?:\s+Agents?)?\b"
        r"|(?i:(?:independent\s+)?review\s+Agents?)|(?:独立)?审查\s*Agent"
    )
    pattern = rf"(?i:{prohibition})(?:(?!(?i:{boundary})).)*?(?:{role})"
    return re.sub(pattern, "", clause)


def policy_clauses(text: str) -> list[str]:
    return re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z])|(?<=[。！？])", text)
