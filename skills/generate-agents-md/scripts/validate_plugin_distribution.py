from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
IGNORED_PARTS = {".git", "__pycache__"}
IGNORED_NAMES = {".DS_Store"}


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


def _manifest(plugin_root: Path) -> dict[str, object]:
    path = plugin_root / ".codex-plugin" / "plugin.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"manifest must be an object: {path}")
    for field in ("name", "version"):
        if not isinstance(payload.get(field), str) or not str(payload[field]).strip():
            raise ValueError(f"manifest requires nonempty string {field}: {path}")
    return payload


def _hashed_files(root: Path, paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        if path.is_symlink():
            continue
        relative = path.relative_to(root)
        if IGNORED_PARTS.intersection(relative.parts) or path.name in IGNORED_NAMES:
            continue
        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _package_files(plugin_root: Path) -> dict[str, str]:
    files: list[Path] = []
    for root in (plugin_root / ".codex-plugin", plugin_root / "skills"):
        if root.is_dir() and not root.is_symlink():
            files.extend(path for path in root.rglob("*") if path.is_file())
    files.extend(
        path for path in (plugin_root / "README.md", plugin_root / ".gitignore") if path.is_file()
    )
    return _hashed_files(plugin_root, files)


def _skill_files(skill_root: Path) -> dict[str, str]:
    if skill_root.is_symlink():
        return {}
    return _hashed_files(
        skill_root, [path for path in skill_root.rglob("*") if path.is_file()],
    )


def _symlink_issues(root: Path, code: str) -> list[Issue]:
    if root.is_symlink():
        return [Issue(code, str(root), "symbolic links are not allowed in distributed content")]
    if not root.exists():
        return []
    return [
        Issue(code, str(path), "symbolic links are not allowed in distributed content")
        for path in root.rglob("*") if path.is_symlink()
    ]


def _package_symlink_issues(plugin_root: Path) -> list[Issue]:
    issues: list[Issue] = []
    if plugin_root.is_symlink():
        issues.append(Issue(
            "package-symlink", str(plugin_root),
            "symbolic links are not allowed in distributed content",
        ))
    for root in (plugin_root / ".codex-plugin", plugin_root / "skills"):
        issues.extend(_symlink_issues(root, "package-symlink"))
    for path in (plugin_root / "README.md", plugin_root / ".gitignore"):
        if path.is_symlink():
            issues.append(Issue(
                "package-symlink", str(path), "symbolic links are not allowed in distributed content",
            ))
    return issues


def _tree_issues(expected: dict[str, str], actual: dict[str, str], code: str, root: Path) -> list[Issue]:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(path for path in set(expected) & set(actual) if expected[path] != actual[path])
    if not (missing or extra or changed):
        return []
    summary = f"missing={missing[:5]} extra={extra[:5]} changed={changed[:5]}"
    return [Issue(code, str(root), summary)]


def _direct_skill_issues(
    source_plugin: Path, direct_skills_root: Path, require_direct_skills: bool,
) -> list[Issue]:
    issues: list[Issue] = []
    source_skills = source_plugin / "skills"
    if not source_skills.is_dir():
        return [Issue("missing-source-skills", str(source_skills), "source skills directory is missing")]
    for source in sorted(path for path in source_skills.iterdir() if (path / "SKILL.md").is_file()):
        direct = direct_skills_root / source.name
        if not direct.is_dir():
            if require_direct_skills:
                issues.append(Issue(
                    "missing-direct-skill", str(direct), "required direct Skill copy is missing",
                ))
            continue
        issues.extend(_symlink_issues(direct, "direct-skill-symlink"))
        issues.extend(_tree_issues(
            _skill_files(source), _skill_files(direct), "direct-skill-mismatch", direct,
        ))
    return issues


def validate_distribution(
    source_plugin: Path, installed_plugin: Path, direct_skills_root: Path,
    require_direct_skills: bool = False,
) -> list[Issue]:
    if not installed_plugin.is_dir():
        return [Issue("missing-installed-plugin", str(installed_plugin), "installed plugin cache is missing")]
    try:
        source_manifest = _manifest(source_plugin)
        installed_manifest = _manifest(installed_plugin)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [Issue("invalid-plugin-manifest", str(installed_plugin), str(error))]
    issues = [*_package_symlink_issues(source_plugin), *_package_symlink_issues(installed_plugin)]
    for field in ("name", "version"):
        if source_manifest.get(field) != installed_manifest.get(field):
            issues.append(Issue(
                "installed-manifest-mismatch", str(installed_plugin),
                f"{field}: source={source_manifest.get(field)!r} installed={installed_manifest.get(field)!r}",
            ))
    issues.extend(_tree_issues(
        _package_files(source_plugin), _package_files(installed_plugin),
        "installed-content-mismatch", installed_plugin,
    ))
    issues.extend(_direct_skill_issues(source_plugin, direct_skills_root, require_direct_skills))
    return issues


def _default_installed(source_plugin: Path) -> Path:
    manifest = _manifest(source_plugin)
    name, version = manifest.get("name"), manifest.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError("source manifest requires string name and version")
    return Path.home() / ".codex" / "plugins" / "cache" / "personal" / name / version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="比较插件源码、当前安装缓存和同名直接安装 Skill")
    parser.add_argument("--source-plugin-root", default=str(PLUGIN_ROOT))
    parser.add_argument("--installed-plugin-root")
    parser.add_argument("--direct-skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument(
        "--require-direct-skills", action="store_true",
        help="要求源码中的每个 Skill 都存在同名直接安装副本",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = Path(args.source_plugin_root).expanduser().absolute()
    direct = Path(args.direct_skills_root).expanduser().absolute()
    try:
        installed = (
            Path(args.installed_plugin_root).expanduser().absolute()
            if args.installed_plugin_root else _default_installed(source)
        )
        issues = validate_distribution(
            source, installed, direct, require_direct_skills=args.require_direct_skills,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues = [Issue(
            "invalid-plugin-manifest", str(source / ".codex-plugin" / "plugin.json"), str(error),
        )]
    if args.json:
        print(json.dumps({"valid": not issues, "issues": [asdict(item) for item in issues]}, indent=2))
    else:
        for issue in issues:
            print(f"ERROR {issue.code} {issue.path} {issue.message}")
        print(f"valid={str(not issues).lower()} issues={len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
