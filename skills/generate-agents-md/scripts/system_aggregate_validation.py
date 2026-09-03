from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModuleResultLike(Protocol):
    module: str
    requirement_ids: frozenset[str]
    changed_files: frozenset[str]
    maintainer_agent_id: str
    implementation_run_id: str
    reviewer_agent_ids: frozenset[str]
    reviewer_run_ids: frozenset[str]


@dataclass(frozen=True)
class AggregateIssue:
    code: str
    message: str


def validate_system_aggregate_sets(
    manifest: dict[str, object], affected: set[str], changed: set[str],
    results: list[ModuleResultLike],
) -> list[AggregateIssue]:
    issues = _validate_declared_sets(manifest, affected, changed, results)
    issues.extend(_validate_native_actor_uniqueness(manifest, results))
    return issues


def _validate_declared_sets(
    manifest: dict[str, object], affected: set[str], changed: set[str],
    results: list[ModuleResultLike],
) -> list[AggregateIssue]:
    issues: list[AggregateIssue] = []
    result_modules = [item.module for item in results]
    declared_modules = {str(item).casefold() for item in manifest["affected_modules"]}
    if len(result_modules) != len(set(result_modules)) or declared_modules != affected or set(result_modules) != affected:
        issues.append(_issue("system-affected-modules-mismatch", "声明、变更文件推导和模块交付包集合必须完全一致"))
    actual_requirements = set().union(*(item.requirement_ids for item in results)) if results else set()
    if set(manifest["requirement_ids"]) != actual_requirements:
        issues.append(_issue("system-requirements-mismatch", "系统需求集合必须等于逐模块需求集合并集"))
    actual_changed = set().union(*(item.changed_files for item in results)) if results else set()
    if changed != actual_changed:
        issues.append(_issue("system-changed-files-mismatch", "系统变更文件必须被逐模块 context 完整且仅一次覆盖"))
    if sum(len(item.changed_files) for item in results) != len(actual_changed):
        issues.append(_issue("system-changed-file-duplicate", "同一变更文件不得出现在多个模块交付包"))
    return issues


def _validate_native_actor_uniqueness(
    manifest: dict[str, object], results: list[ModuleResultLike],
) -> list[AggregateIssue]:
    issues: list[AggregateIssue] = []
    maintainer_runs = [item.implementation_run_id for item in results]
    maintainer_agents = [item.maintainer_agent_id for item in results]
    reviewer_runs = [run_id for item in results for run_id in item.reviewer_run_ids]
    reviewer_agents = [agent_id for item in results for agent_id in item.reviewer_agent_ids]
    if len(maintainer_runs) != len(set(maintainer_runs)):
        issues.append(_issue("system-implementation-run-duplicate", "每个模块必须由独立实现 Agent run 维护"))
    if len(maintainer_agents) != len(set(maintainer_agents)):
        issues.append(_issue("system-maintainer-agent-duplicate", "每个大功能模块必须由不同的封闭 receipt 绑定维护 Agent 长期维护；严格模式追加宿主证明"))
    actor_agents = [str(manifest["dispatcher_agent_id"]), str(manifest["aggregation_writer_agent_id"]),
                    *maintainer_agents, *reviewer_agents]
    actor_runs = [str(manifest["dispatcher_run_id"]), str(manifest["aggregation_writer_run_id"]),
                  *maintainer_runs, *reviewer_runs]
    writer_pair = (str(manifest["aggregation_writer_agent_id"]), str(manifest["aggregation_writer_run_id"]))
    forbidden_agents = {str(manifest["dispatcher_agent_id"]), *maintainer_agents, *reviewer_agents}
    forbidden_runs = {str(manifest["dispatcher_run_id"]), *maintainer_runs, *reviewer_runs}
    if writer_pair[0] in forbidden_agents or writer_pair[1] in forbidden_runs:
        issues.append(_issue("system-aggregation-writer-not-independent", "系统聚合写者 agent_id/run_id 必须独立于 Dispatcher、模块维护者和独立验收者"))
    if len(actor_agents) != len(set(actor_agents)) or len(actor_runs) != len(set(actor_runs)):
        issues.append(_issue("system-native-agent-identity-collision", "Dispatcher、每个模块维护者、独立验收者和系统聚合者的封闭 receipt agent_id/run_id 必须全局唯一；严格模式追加宿主证明"))
    return issues


def _issue(code: str, message: str) -> AggregateIssue:
    return AggregateIssue(code, message)
