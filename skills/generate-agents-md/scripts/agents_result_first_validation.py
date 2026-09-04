from __future__ import annotations

import re

from agents_policy_common import section_has_line


def has_result_first_hardening_sequence(section: str) -> bool:
    """Return whether delivery produces, freezes, then preserves a usable result."""
    flattened = re.sub(r"\s+", " ", section).strip()
    canonical_order = re.search(
        r"result_candidate\s*->\s*affected_checks_passed\s*->\s*"
        r"baseline_frozen\s*->\s*hardening\s*->\s*closure_candidate",
        flattened,
        re.IGNORECASE,
    ) is not None
    negated_first_result = re.search(
        r"(?:do not|never|must not|不得|禁止)\s+(?:\S+\s+){0,12}"
        r"(?:drive|run|execute|跑通|执行).{0,100}(?:real entry|真实入口|observable|可观测)",
        flattened,
        re.IGNORECASE,
    ) is not None
    return (
        canonical_order
        and not negated_first_result
        and section_has_line(section, (r"first|before.*harden|先|首个", r"smallest.*business flow|minimum business flow|最小业务流程|最小业务链", r"real entry|真实入口", r"observable.*result|可观测.*结果"))
        and section_has_line(section, (r"freeze|冻结", r"code(?: version)?/build|代码版本", r"acceptance command|验收命令", r"result|结果", r"SHA-256|hash|哈希"))
        and section_has_line(section, (r"only after|afterward|之后才|冻结后才|之后", r"mapped|映射|nonessential|非必要", r"gate|门禁|hardening|打磨|优化"))
        and section_has_line(section, (r"regress|回归", r"restore|repair|恢复|修复", r"rerun|replay|重跑|重放", r"frozen acceptance|冻结.*验收"))
        and section_has_line(section, (r"governance|治理", r"not.*deliver|not delivery|不能.*交付|不得.*替代"))
    )
