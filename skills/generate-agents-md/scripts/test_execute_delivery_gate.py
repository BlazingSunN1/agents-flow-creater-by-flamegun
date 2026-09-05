from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_delivery_gate import execute_gate
from test_validate_delivery_contract import DeliveryContractValidatorTests


class DeliveryGateExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = DeliveryContractValidatorTests("test_valid_contract_passes")
        self.fixture.setUp()
        self.root = self.fixture.root
        self.contract = self.fixture.path
        (self.root / "test_success.py").write_text(
            "import unittest\nclass TestSuccess(unittest.TestCase):\n"
            "    def test_success(self): self.assertEqual(2, 1 + 1)\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_runner_executes_registered_argv_and_writes_schema_v2_receipt(self) -> None:
        output = "docs/executed-targeted-tests.txt"
        receipt = "docs/executed-targeted-tests.json"
        self.assertEqual(0, execute_gate(
            self.contract,
            "targeted_tests",
            project_root=self.root,
            output_path=output,
            receipt_path=receipt,
            run_id="gate-run-1",
        ))
        payload = json.loads((self.root / receipt).read_text(encoding="utf-8"))
        self.assertEqual(2, payload["schema_version"])
        self.assertEqual("flowctl-gate-runner", payload["producer"])
        self.assertEqual(0, payload["exit_code"])
        self.assertEqual("pass", payload["verdict"])
        self.assertEqual(
            ["python3", "-m", "unittest"], payload["command_argv"],
        )
        contract = json.loads(self.contract.read_text(encoding="utf-8"))
        contract["gate_receipts"]["targeted_tests"] = self.fixture.ref(receipt)
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        self.assertEqual(set(), self.fixture.codes())


if __name__ == "__main__":
    unittest.main()
