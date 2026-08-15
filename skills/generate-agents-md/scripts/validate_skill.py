from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: list[str]
    returncode: int
    elapsed_seconds: float
    output_tail: str


def build_checks(root: Path = SKILL_ROOT) -> list[tuple[str, list[str]]]:
    codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    quick = codex_root / "skills/.system/skill-creator/scripts/quick_validate.py"
    return [
        ("skill-package", [sys.executable, str(quick), str(root)]),
        ("code-structure", [sys.executable, "scripts/validate_code_structure.py"]),
        ("cli-smoke", [sys.executable, "scripts/validate_cli_smoke.py"]),
        (
            "unit-regression",
            [sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-q"],
        ),
        ("mutation", [sys.executable, "scripts/run_mutation_checks.py"]),
        ("swimlane-js-syntax", ["node", "--check", "scripts/browser_test_swimlane.mjs"]),
    ]


def run_check(name: str, command: list[str], root: Path) -> CheckResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        returncode = result.returncode
    except OSError as error:
        output, returncode = str(error), 127
    return CheckResult(name, command, returncode, round(time.monotonic() - started, 3), output[-4000:])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 generate-agents-md Skill 的完整自验证门禁")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = [run_check(name, command, SKILL_ROOT) for name, command in build_checks()]
    valid = all(item.returncode == 0 for item in results)
    if args.json:
        print(json.dumps({"valid": valid, "checks": [asdict(item) for item in results]}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"{'PASS' if item.returncode == 0 else 'FAIL'} {item.name} {item.elapsed_seconds:.3f}s")
            if item.returncode != 0 and item.output_tail:
                print(item.output_tail)
        print(f"valid={str(valid).lower()} checks={len(results)}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
