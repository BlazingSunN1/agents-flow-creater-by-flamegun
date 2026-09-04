#!/usr/bin/env python3
"""Validate declared task write targets against project or maintenance boundaries.

This is a fail-closed preflight for proposed paths. It does not intercept writes
that bypass the command and therefore is not an operating-system sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from agents_dispatcher_policy_validation import module_ownership_mapping

DEFAULT_DERIVED_ROOTS = (
    Path.home() / ".codex" / "skills",
    Path.home() / ".codex" / "plugins",
    Path.home() / ".agents" / "skills",
    Path.home() / ".agents" / "plugins",
)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _canonical(path: Path, anchor: Path | None = None) -> Path:
    candidate = path if path.is_absolute() or anchor is None else anchor / path
    return candidate.resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _protected_roots(args: argparse.Namespace) -> tuple[Path, ...]:
    roots = list(DEFAULT_DERIVED_ROOTS)
    source_parent = Path.home() / "plugins"
    if source_parent.is_dir():
        roots.extend(child for child in source_parent.iterdir() if _is_source_root(child))
    roots.extend(Path(value) for value in args.protected_root)
    return tuple(dict.fromkeys(_canonical(root) for root in roots))


def _derived_roots(args: argparse.Namespace) -> tuple[Path, ...]:
    roots = list(DEFAULT_DERIVED_ROOTS)
    roots.extend(Path(value) for value in args.derived_root)
    return tuple(dict.fromkeys(_canonical(root) for root in roots))


def _is_source_root(root: Path) -> bool:
    markers = (root / "SKILL.md", root / ".codex-plugin" / "plugin.json")
    return any(marker.is_file() and not marker.is_symlink() for marker in markers)


def _has_source_marker(root: Path) -> bool:
    markers = (root / "SKILL.md", root / ".codex-plugin" / "plugin.json")
    return any(marker.is_file() or marker.is_symlink() for marker in markers)


def _source_root_for_target(target: Path, project: Path) -> Path | None:
    if target.name.casefold() == "skill.md":
        return target.parent
    if (target.name.casefold() == "plugin.json"
            and target.parent.name.casefold() == ".codex-plugin"):
        return target.parent.parent
    cursor = target if target.is_dir() else target.parent
    while cursor != project and _is_within(cursor, project):
        if _has_source_marker(cursor):
            return cursor
        cursor = cursor.parent
    return None


def _directory_target_risks(
    target: Path,
) -> tuple[Path | None, Path | None, Path | None]:
    if not target.is_dir():
        return None, None, None
    source_root: Path | None = None
    symlink_path: Path | None = None
    scan_error: Path | None = None

    def remember_scan_error(error: OSError) -> None:
        nonlocal scan_error
        if scan_error is None:
            scan_error = Path(error.filename) if error.filename else target

    for raw_root, dirnames, filenames in os.walk(
        target, followlinks=False, onerror=remember_scan_error,
    ):
        root = Path(raw_root)
        names = {name.casefold() for name in filenames}
        if source_root is None and "skill.md" in names:
            source_root = root
        if (source_root is None and root.name.casefold() == ".codex-plugin"
                and "plugin.json" in names):
            source_root = root.parent
        for name in filenames:
            child = root / name
            if symlink_path is None and child.is_symlink():
                symlink_path = child
        for name in tuple(dirnames):
            child = root / name
            if child.is_symlink():
                dirnames.remove(name)
                if symlink_path is None:
                    symlink_path = child
                if source_root is None and name.casefold() == ".codex-plugin":
                    source_root = root
        if source_root is not None and symlink_path is not None:
            break
    return source_root, symlink_path, scan_error


def _project_target_findings(
    target: Path, project: Path, protected: tuple[Path, ...],
    source_root: Path | None, descendant_source_root: Path | None,
    descendant_symlink: Path | None, descendant_scan_error: Path | None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not _is_within(target, project):
        findings.append(Finding(
            "outside-project-root", f"target resolves outside project root: {target}",
        ))
    if source_root is not None:
        findings.append(Finding(
            "project-target-is-skill-source",
            "project-agent cannot write Skill/plugin source target; use an explicitly "
            f"authorized skill-maintainer task for exact root: {source_root}",
        ))
    if source_root is None and descendant_source_root is not None:
        findings.append(Finding(
            "project-target-contains-skill-source",
            "project-agent directory target contains nested Skill/plugin source; use an "
            f"explicitly authorized skill-maintainer task for exact root: {descendant_source_root}",
        ))
    if descendant_symlink is not None:
        findings.append(Finding(
            "project-directory-target-contains-symlink",
            f"project-agent directory target contains a symlink: {descendant_symlink}",
        ))
    if descendant_scan_error is not None:
        findings.append(Finding(
            "project-directory-target-scan-failed",
            "project-agent directory target could not be scanned safely: "
            f"{descendant_scan_error}",
        ))
    if any(_is_within(target, root) for root in protected):
        findings.append(Finding(
            "protected-root", f"project-agent target is protected: {target}",
        ))
    return findings


def _project_findings(
    args: argparse.Namespace, targets: tuple[Path, ...], protected: tuple[Path, ...]
) -> list[Finding]:
    if args.project_root is None:
        return [Finding("missing-project-root", "project-agent requires --project-root")]
    project = _canonical(Path(args.project_root))
    findings: list[Finding] = []
    home = _canonical(Path.home())
    filesystem_root = Path(project.anchor)
    if (not project.is_dir() or project == filesystem_root
            or project == home or _is_within(home, project)):
        findings.append(Finding(
            "unsafe-project-root",
            f"project root must be an existing non-broad project directory: {project}",
        ))
    if _has_source_marker(project):
        findings.append(Finding(
            "project-root-is-skill-source",
            f"project-agent cannot treat a Skill/plugin source as a project root: {project}",
        ))
    if any(_is_within(project, root) for root in protected):
        findings.append(Finding(
            "project-root-is-protected",
            f"project-agent cannot use protected root as project root: {project}",
        ))
    ownership = _project_ownership(args, project, findings)
    for raw_target in targets:
        target = _canonical(raw_target, project)
        source_root = _source_root_for_target(target, project)
        directory_risks = (
            _directory_target_risks(target)
            if _is_within(target, project) else (None, None, None)
        )
        findings.extend(_project_target_findings(
            target, project, protected, source_root, *directory_risks,
        ))
        if ownership is not None:
            try:
                relative_target = target.relative_to(project)
            except ValueError:
                continue
            if not _target_is_owned(relative_target, ownership):
                findings.append(Finding(
                    "module-ownership-mismatch",
                    f"target is outside module {args.module_key} owned paths: {target}",
                ))
    return findings


def _project_ownership(
    args: argparse.Namespace, project: Path, findings: list[Finding],
) -> tuple[str, ...] | None:
    if args.ownership_file != "AGENTS.md":
        findings.append(Finding(
            "ownership-file-not-canonical",
            "project-agent requires --ownership-file AGENTS.md",
        ))
        return None
    ownership_file = project / "AGENTS.md"
    if ownership_file.is_symlink() or not ownership_file.is_file():
        findings.append(Finding(
            "missing-canonical-ownership",
            f"canonical ownership file is missing or unsafe: {ownership_file}",
        ))
        return None
    try:
        mapping = module_ownership_mapping(ownership_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        mapping = {}
    module = args.module_key.casefold()
    if module not in mapping:
        findings.append(Finding(
            "module-owner-not-registered",
            f"module key is not registered in canonical AGENTS.md ownership: {args.module_key}",
        ))
        return None
    return mapping[module][0]


def _target_is_owned(target: Path, owned_paths: tuple[str, ...]) -> bool:
    return any(
        target.parts[:len(Path(path).parts)] == Path(path).parts
        for path in owned_paths
    )


def _maintainer_findings(
    args: argparse.Namespace, targets: tuple[Path, ...], derived: tuple[Path, ...]
) -> list[Finding]:
    findings: list[Finding] = []
    if args.maintenance_root is None:
        return [Finding(
            "missing-maintenance-root", "skill-maintainer requires --maintenance-root"
        )]
    maintenance = _canonical(Path(args.maintenance_root))
    if not _is_source_root(maintenance):
        findings.append(Finding(
            "invalid-maintenance-source-root",
            "maintenance root must contain a regular SKILL.md or .codex-plugin/plugin.json",
        ))
    if any(_is_within(maintenance, root) for root in derived):
        findings.append(Finding(
            "maintenance-root-is-derived",
            f"cache or direct-install root cannot be maintained as source: {maintenance}",
        ))
    if not args.explicit_user_authorization:
        findings.append(Finding(
            "missing-explicit-user-authorization",
            "skill-maintainer requires explicit authorization from the current user request",
        ))
    if args.authorization_source != "current-user-request":
        findings.append(Finding(
            "invalid-authorization-source",
            "skill-maintainer requires --authorization-source current-user-request",
        ))
    for raw_target in targets:
        target = _canonical(raw_target, maintenance)
        if not _is_within(target, maintenance):
            findings.append(Finding(
                "outside-maintenance-root",
                f"target resolves outside the exact maintenance root: {target}",
            ))
            continue
        _source_root, descendant_symlink, scan_error = _directory_target_risks(target)
        if descendant_symlink is not None:
            findings.append(Finding(
                "maintenance-directory-target-contains-symlink",
                f"skill-maintainer directory target contains a symlink: {descendant_symlink}",
            ))
        if scan_error is not None:
            findings.append(Finding(
                "maintenance-directory-target-scan-failed",
                "skill-maintainer directory target could not be scanned safely: "
                f"{scan_error}",
            ))
    return findings


def validate(args: argparse.Namespace) -> tuple[list[Finding], list[str]]:
    targets = tuple(Path(value) for value in args.target)
    if not targets:
        return [Finding("missing-target", "at least one --target is required")], []
    protected = _protected_roots(args)
    if args.role == "project-agent":
        findings = _project_findings(args, targets, protected)
    else:
        findings = _maintainer_findings(args, targets, _derived_roots(args))
    warnings = []
    if args.runtime_boundary == "audit-only":
        warnings.append(
            "audit-only validates declared targets but does not provide OS write isolation"
        )
    return findings, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role", required=True, choices=("project-agent", "skill-maintainer")
    )
    parser.add_argument("--project-root")
    parser.add_argument("--module-key", required=False)
    parser.add_argument("--ownership-file", default="AGENTS.md")
    parser.add_argument("--maintenance-root")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--protected-root", action="append", default=[])
    parser.add_argument("--derived-root", action="append", default=[])
    parser.add_argument("--explicit-user-authorization", action="store_true")
    parser.add_argument("--authorization-source")
    parser.add_argument(
        "--runtime-boundary",
        choices=("audit-only", "workspace-write-sandbox", "isolated-worktree", "container"),
        default="audit-only",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _emit(findings: list[Finding], warnings: list[str], as_json: bool) -> None:
    if as_json:
        payload = {
            "ok": not findings,
            "errors": [finding.__dict__ for finding in findings],
            "warnings": warnings,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    for finding in findings:
        print(f"ERROR [{finding.code}] {finding.message}", file=sys.stderr)
    for warning in warnings:
        print(f"WARNING {warning}", file=sys.stderr)
    if not findings:
        print("task write scope valid")


def main() -> int:
    args = build_parser().parse_args()
    if args.role == "project-agent" and not args.module_key:
        build_parser().error("project-agent requires --module-key")
    findings, warnings = validate(args)
    _emit(findings, warnings, args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
