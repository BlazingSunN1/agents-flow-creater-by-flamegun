from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
FULL_AFFECTED_PATHS = {
    "SKILL.md",
    "scripts/delivery_gate_planner.py", "scripts/validate_delivery_contract.py",
    "scripts/plan_delivery_gates.py", "scripts/validate_skill.py",
    "scripts/run_mutation_checks.py",
    "scripts/validate_project_commands.py", "assets/delivery-contract.template.json",
    "assets/gate-receipt.template.json", "assets/project-commands.template.json",
}
FULL_AFFECTED_PREFIXES = ("references/",)
FULL_AFFECTED_SCRIPT_PREFIXES = ("scripts/mutation_cases_",)
AFFECTED_ASSET_TESTS = {
    "assets/AGENTS.template.md": {"test_validate_agents_md", "test_validate_skill"},
    "assets/AGENTS.scoped.template.md": {"test_validate_agents_md", "test_validate_skill"},
    "assets/AGENTS.optional-sections.md": {"test_validate_agents_md", "test_validate_skill"},
    "assets/requirement-questions.template.json": {
        "test_validate_requirement_questions", "test_validate_delivery_bundle",
    },
    "assets/requirement-traceability.template.md": {
        "test_validate_traceability", "test_validate_delivery_bundle", "test_validate_skill",
    },
    "assets/context-manifest.template.md": {"test_validate_context_manifest"},
    "assets/frontend-evidence.template.json": {"test_validate_frontend_evidence"},
    "assets/swimlane-evidence.template.json": {"test_validate_swimlane_evidence"},
    "assets/multi-agent-evidence.template.json": {"test_validate_multi_agent_evidence"},
    "assets/native-review-loop-evidence.template.json": {"test_validate_native_review_loop"},
    "assets/automated-review-evidence.template.md": {"test_validate_delivery_bundle"},
    "assets/automated-review-output.template.json": {"test_validate_delivery_bundle"},
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: list[str]
    returncode: int
    elapsed_seconds: float
    output_tail: str


def build_checks(
    root: Path = SKILL_ROOT,
    mode: str = "full",
    changed_files: tuple[str, ...] = (),
    distribution: bool = False,
    require_direct_skills: bool = False,
    installed_plugin_root: str | None = None,
    direct_skills_root: str | None = None,
) -> list[tuple[str, list[str]]]:
    if mode not in {"quick", "affected", "full"}:
        raise ValueError(f"unsupported validation mode: {mode}")
    if distribution and mode != "full":
        raise ValueError("distribution validation requires full mode")
    if require_direct_skills and not distribution:
        raise ValueError("required direct Skills validation requires distribution mode")
    codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    quick = codex_root / "skills/.system/skill-creator/scripts/quick_validate.py"
    fast_checks = [
        ("skill-package", [sys.executable, str(quick), str(root)]),
        ("code-structure", [sys.executable, "scripts/validate_code_structure.py"]),
        ("cli-smoke", [sys.executable, "scripts/validate_cli_smoke.py"]),
        ("swimlane-js-syntax", ["node", "--check", "scripts/browser_test_swimlane.mjs"]),
    ]
    if mode == "quick":
        return fast_checks
    if mode == "affected":
        affected, must_escalate = _affected_checks(root, changed_files)
        if must_escalate:
            return build_checks(root=root, mode="full")
        return [*fast_checks, *affected]
    checks = [
        *fast_checks[:3],
        (
            "unit-regression",
            [sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-q"],
        ),
        ("mutation", [sys.executable, "scripts/run_mutation_checks.py"]),
        fast_checks[-1],
    ]
    if distribution:
        checks.append((
            "plugin-distribution",
            _distribution_command(
                root, installed_plugin_root, direct_skills_root, require_direct_skills,
            ),
        ))
    return checks


def _distribution_command(
    root: Path, installed_plugin_root: str | None, direct_skills_root: str | None,
    require_direct_skills: bool,
) -> list[str]:
    command = [
        sys.executable, "scripts/validate_plugin_distribution.py",
        "--source-plugin-root", str(root.parent.parent),
        "--require-source-provenance",
    ]
    if installed_plugin_root:
        command.extend(("--installed-plugin-root", installed_plugin_root))
    if direct_skills_root:
        command.extend(("--direct-skills-root", direct_skills_root))
    if require_direct_skills:
        command.append("--require-direct-skills")
    return command


def _affected_checks(
    root: Path, changed_files: tuple[str, ...],
) -> tuple[list[tuple[str, list[str]]], bool]:
    if not changed_files:
        raise ValueError("affected validation requires at least one --changed-file")
    tests: set[str] = set()
    fallback = False
    for raw in changed_files:
        path = Path(raw)
        normalized = path.as_posix()
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe changed file: {raw}")
        if (normalized in FULL_AFFECTED_PATHS
                or normalized.startswith(FULL_AFFECTED_PREFIXES + FULL_AFFECTED_SCRIPT_PREFIXES)):
            fallback = True
            continue
        matched = _map_affected_file(root, normalized, tests)
        if not matched:
            fallback = True
    if fallback or not tests:
        return [], True
    return [
        (
            f"affected-test:{name}",
            [sys.executable, "-m", "unittest", "-q", f"scripts.{name}"],
        )
        for name in sorted(tests)
    ], False


def _map_affected_file(root: Path, normalized: str, tests: set[str]) -> bool:
    matched = False
    if normalized in AFFECTED_ASSET_TESTS:
        tests.update(AFFECTED_ASSET_TESTS[normalized])
        tests.update(_literal_asset_consumer_tests(root, normalized))
        matched = True
    if normalized.startswith("scripts/") and normalized.endswith(".py"):
        dependent_tests = _python_dependent_tests(root, Path(normalized).stem)
        if dependent_tests:
            tests.update(dependent_tests)
            matched = True
    if normalized in {
        "assets/generate-agents-md-swimlanes.html",
        "scripts/browser_test_swimlane.mjs",
    }:
        tests.add("test_swimlane_html")
        matched = True
    return matched


def _literal_asset_consumer_tests(root: Path, normalized: str) -> set[str]:
    filename = Path(normalized).name
    consumers: set[str] = set()
    for test_path in (root / "scripts").glob("test_*.py"):
        try:
            if filename in test_path.read_text(encoding="utf-8"):
                consumers.add(test_path.stem)
        except (OSError, UnicodeError):
            return set()
    return consumers


def _python_dependent_tests(root: Path, changed_module: str) -> set[str]:
    scripts = root / "scripts"
    reverse_imports: dict[str, set[str]] = {}
    for candidate in scripts.glob("*.py"):
        try:
            tree = ast.parse(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError):
            return set()
        dependencies: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                dependencies.add(node.module.split(".")[0])
        for dependency in dependencies:
            reverse_imports.setdefault(dependency, set()).add(candidate.stem)
    reachable = {changed_module}
    pending = [changed_module]
    while pending:
        for importer in reverse_imports.get(pending.pop(), set()):
            if importer not in reachable:
                reachable.add(importer)
                pending.append(importer)
    tests: set[str] = set()
    for module in reachable:
        if module.startswith("test_") and (scripts / f"{module}.py").is_file():
            tests.add(module)
        direct_test = scripts / f"test_{module}.py"
        if direct_test.is_file():
            tests.add(direct_test.stem)
    return tests


def effective_mode(root: Path, mode: str, changed_files: tuple[str, ...]) -> str:
    if mode != "affected":
        return mode
    _, must_escalate = _affected_checks(root, changed_files)
    return "full" if must_escalate else "affected"


def run_check(
    name: str, command: list[str], root: Path, *, timeout_seconds: float = 600.0,
) -> CheckResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        returncode = result.returncode
    except subprocess.TimeoutExpired as error:
        captured = "\n".join(
            part.decode(errors="replace") if isinstance(part, bytes) else (part or "")
            for part in (error.stdout, error.stderr)
        ).strip()
        output = f"check timed out after {timeout_seconds:g}s"
        if captured:
            output += "\n" + captured[-3500:]
        returncode = 124
    except OSError as error:
        output, returncode = str(error), 127
    return CheckResult(name, command, returncode, round(time.monotonic() - started, 3), output[-4000:])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 generate-agents-md Skill 的分层自验证门禁")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", dest="mode", action="store_const", const="quick", help="迭代检查；不作为闭环验收")
    mode.add_argument("--affected", dest="mode", action="store_const", const="affected", help="按显式变更文件运行中等强度验证")
    mode.add_argument("--full", dest="mode", action="store_const", const="full", help="完整闭环验收（默认）")
    parser.add_argument("--changed-file", dest="changed_files", action="append", default=[], help="affected 模式的项目相对变更文件；可重复")
    parser.add_argument("--distribution", action="store_true", help="完整验证后比较源码、当前插件缓存及重复直接安装副本")
    parser.add_argument("--installed-plugin-root", help="覆盖自动推导的当前插件缓存目录")
    parser.add_argument("--direct-skills-root", help="覆盖 ~/.codex/skills 直接安装目录")
    parser.add_argument(
        "--check-timeout-seconds", type=float, default=600.0,
        help="每个子检查的超时秒数（默认 600）",
    )
    parser.add_argument(
        "--require-direct-skills", action="store_true",
        help="分发校验时要求插件内每个 Skill 都有同名直接安装副本",
    )
    parser.set_defaults(mode="full")
    return parser


def _validate_cli_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.mode == "affected" and not args.changed_files:
        parser.error("--affected requires at least one --changed-file")
    if args.distribution and args.mode != "full":
        parser.error("--distribution requires --full")
    if args.require_direct_skills and not args.distribution:
        parser.error("--require-direct-skills requires --distribution")
    if args.check_timeout_seconds <= 0:
        parser.error("--check-timeout-seconds must be positive")


def _execute_checks(args: argparse.Namespace) -> list[CheckResult]:
    results: list[CheckResult] = []
    for name, command in build_checks(
            mode=args.mode,
            changed_files=tuple(args.changed_files),
            distribution=args.distribution,
            require_direct_skills=args.require_direct_skills,
            installed_plugin_root=args.installed_plugin_root,
            direct_skills_root=args.direct_skills_root,
        ):
        if not args.json:
            print(f"RUN {name}", flush=True)
        results.append(run_check(
            name, command, SKILL_ROOT,
            timeout_seconds=args.check_timeout_seconds,
        ))
    return results


def _emit_results(
    args: argparse.Namespace, results: list[CheckResult], resolved_mode: str,
) -> None:
    valid = all(item.returncode == 0 for item in results)
    if args.json:
        print(
            json.dumps(
                {
                    "valid": valid,
                    "requested_mode": args.mode,
                    "effective_mode": resolved_mode,
                    "escalation_reason": (
                        "unknown affected mapping; full validation required"
                        if args.mode == "affected" and resolved_mode == "full" else None
                    ),
                    "checks": [asdict(item) for item in results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in results:
            print(f"{'PASS' if item.returncode == 0 else 'FAIL'} {item.name} {item.elapsed_seconds:.3f}s")
            if item.returncode != 0 and item.output_tail:
                print(item.output_tail)
        suffix = " reason=unknown-affected-mapping" if resolved_mode != args.mode else ""
        print(f"valid={str(valid).lower()} requested={args.mode} effective={resolved_mode} checks={len(results)}{suffix}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    _validate_cli_args(parser, args)
    resolved_mode = effective_mode(SKILL_ROOT, args.mode, tuple(args.changed_files))
    results = _execute_checks(args)
    valid = all(item.returncode == 0 for item in results)
    _emit_results(args, results, resolved_mode)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
