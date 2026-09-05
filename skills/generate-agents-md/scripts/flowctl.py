from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable


CORE_COMMANDS = {
    "doctor": "validate_skill",
    "scope": "validate_task_write_scope",
    "plan": "plan_delivery_gates",
    "gate": "execute_delivery_gate",
    "record": "update_project_record",
}

CHECK_COMMANDS = {
    "agents": "validate_agents_md",
    "commands": "validate_project_commands",
    "context": "validate_context_manifest",
    "contract": "validate_delivery_contract",
    "frontend": "validate_frontend_evidence",
    "module-close": "validate_delivery_bundle",
    "multi-agent": "validate_multi_agent_evidence",
    "native-review": "validate_native_review_loop",
    "questions": "validate_requirement_questions",
    "swimlane": "validate_swimlane_evidence",
    "system-close": "validate_system_delivery_bundle",
    "trace": "validate_traceability",
}

STRICT_COMMANDS = {
    "activate-lease": "activate_local_controlled_module_lease",
    "apply-write": "apply_local_controlled_module_write",
    "bootstrap": "apply_system_governance_bootstrap_v2",
    "validate-lease": "validate_local_controlled_module_lease",
    "validate-trust": "validate_local_controlled_trust",
}


def _delegate(module_name: str, arguments: list[str]) -> int:
    module = importlib.import_module(module_name)
    entry: Callable[[], int] = module.main
    previous = sys.argv
    try:
        sys.argv = [f"flowctl:{module_name}", *arguments]
        return int(entry())
    finally:
        sys.argv = previous


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agents Flow 的单一命令入口；旧 scripts/*.py 入口继续兼容。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module_name in CORE_COMMANDS.items():
        child = subparsers.add_parser(name, add_help=False)
        child.set_defaults(module_name=module_name)

    check = subparsers.add_parser("check", add_help=False)
    check.add_argument("kind", choices=sorted(CHECK_COMMANDS))

    strict = subparsers.add_parser(
        "strict",
        add_help=False,
        help="仅在显式启用 strict-delivery-security 时使用",
    )
    strict.add_argument("kind", choices=sorted(STRICT_COMMANDS))
    return parser


def main() -> int:
    args, delegated_arguments = _build_parser().parse_known_args()
    if args.command == "check":
        module_name = CHECK_COMMANDS[args.kind]
    elif args.command == "strict":
        module_name = STRICT_COMMANDS[args.kind]
    else:
        module_name = args.module_name
    return _delegate(module_name, delegated_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
