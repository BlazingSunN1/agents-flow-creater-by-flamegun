from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import flowctl


class FlowctlTests(unittest.TestCase):
    def test_core_and_check_commands_delegate_without_changing_arguments(self) -> None:
        cases = (
            (["doctor", "--quick"], "validate_skill", ["--quick"]),
            (["plan", "contract.json"], "plan_delivery_gates", ["contract.json"]),
            (["check", "frontend", "evidence.json"], "validate_frontend_evidence", ["evidence.json"]),
            (["check", "module-close", "bundle.json"], "validate_delivery_bundle", ["bundle.json"]),
        )
        for arguments, module_name, delegated in cases:
            with self.subTest(arguments=arguments), mock.patch.object(
                flowctl, "_delegate", return_value=0,
            ) as call, mock.patch.object(sys, "argv", ["flowctl.py", *arguments]):
                self.assertEqual(0, flowctl.main())
                call.assert_called_once_with(module_name, delegated)

    def test_strict_commands_are_explicitly_namespaced(self) -> None:
        with mock.patch.object(flowctl, "_delegate", return_value=0) as call, mock.patch.object(
            sys, "argv", ["flowctl.py", "strict", "validate-lease", "lease.json"],
        ):
            self.assertEqual(0, flowctl.main())
        call.assert_called_once_with("validate_local_controlled_module_lease", ["lease.json"])

    def test_help_does_not_load_a_delegated_module(self) -> None:
        with mock.patch.object(flowctl, "_delegate") as call, mock.patch.object(
            sys, "argv", ["flowctl.py", "--help"],
        ), self.assertRaises(SystemExit) as raised:
            flowctl.main()
        self.assertEqual(0, raised.exception.code)
        call.assert_not_called()

    def test_process_level_black_box_routes_public_and_optional_commands(self) -> None:
        cases = (
            (["check", "agents", "--help"], "校验项目 AGENTS.md 或脱敏公共模板"),
            (["strict", "validate-lease", "--help"], "usage:"),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT_ROOT / "flowctl.py"), *arguments],
                    cwd=SCRIPT_ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stdout)
                self.assertIn(expected, completed.stdout)


if __name__ == "__main__":
    unittest.main()
