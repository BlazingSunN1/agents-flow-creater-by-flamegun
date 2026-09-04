from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
CLI_SCRIPTS = (
    "flowctl.py",
    "activate_local_controlled_module_lease.py",
    "apply_local_controlled_module_write.py",
    "apply_system_governance_bootstrap_v2.py",
    "plan_delivery_gates.py",
    "update_project_record.py",
    "validate_agents_md.py",
    "validate_code_structure.py",
    "validate_context_manifest.py",
    "validate_delivery_bundle.py",
    "validate_delivery_contract.py",
    "validate_frontend_evidence.py",
    "validate_local_controlled_trust.py",
    "validate_local_controlled_module_lease.py",
    "validate_multi_agent_evidence.py",
    "validate_native_review_loop.py",
    "validate_plugin_distribution.py",
    "validate_project_commands.py",
    "validate_requirement_questions.py",
    "validate_skill.py",
    "validate_swimlane_evidence.py",
    "validate_system_delivery_bundle.py",
    "validate_task_write_scope.py",
    "validate_traceability.py",
)


@dataclass(frozen=True)
class Failure:
    script: str
    returncode: int
    output: str


def run_cli_smoke(root: Path = SCRIPT_ROOT) -> list[Failure]:
    failures: list[Failure] = []
    for name in CLI_SCRIPTS:
        result = subprocess.run(
            [sys.executable, str(root / name), "--help"],
            cwd=root.parent,
            text=True,
            capture_output=True,
            check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode != 0:
            output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
            failures.append(Failure(name, result.returncode, output[-2000:]))
    return failures


def main() -> int:
    failures = run_cli_smoke()
    for item in failures:
        print(f"FAIL {item.script} rc={item.returncode}\n{item.output}")
    print(f"valid={str(not failures).lower()} commands={len(CLI_SCRIPTS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
