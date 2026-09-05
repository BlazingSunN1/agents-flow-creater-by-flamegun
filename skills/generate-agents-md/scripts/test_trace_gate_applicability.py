from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_delivery_contract as contract_tests
import test_validate_traceability as trace_tests
from delivery_gate_planner import build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint
from validate_delivery_contract import validate_delivery_contract
from validate_traceability import validate_traceability


class TraceGateApplicabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = contract_tests.DeliveryContractValidatorTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        trace = trace_tests.TraceabilityValidatorTests()
        trace.setUp()
        self.addCleanup(trace.tearDown)
        self.root = self.fixture.root
        shutil.copytree(trace.root, self.root, dirs_exist_ok=True)
        self.path = self.root / "traceability.md"
        text = self.path.read_text(encoding="utf-8")
        text = text.replace("Risk level: standard", "Risk level: small")
        text = text.replace("Risk reason: user-visible interaction", "Risk reason: internal change")
        text = text.replace("Change surfaces: ui,user-visible", "Change surfaces: internal")
        text = text.replace("[FLOW-001](flows/system.html)", "N/A: no applicable flow")
        text = text.replace("[BB-001](evidence/black-box.md)", "N/A: no planned black-box role")
        lines = text.splitlines()
        lines = [line.replace("required | bb-run-1", "N/A: small internal task | ")
                 .replace("[CTX-BB-001](evidence/bb-input.md)", "N/A: small internal task")
                 .replace("[EVD-BB-001](evidence/bb-output.md)", "N/A: small internal task")
                 .replace("| pass |", "| not_applicable |")
                 if line.startswith("| BLACK_BOX |") else line for line in lines]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.data = self.fixture.contract()
        self.data.update(stage="completion", status="completed", gate_receipts={})
        self.data["artifacts"]["traceability"] = self.fixture.ref("traceability.md")
        self.data["identity"]["environment_id"] = "local-release"
        self.data["change"].update(delivery_phase="completed", risk_level="small",
                                   risk_reason="internal change", surfaces=["internal"],
                                   swimlane_applicable=False)
        self.save()

    def save(self, *, replan: bool = True) -> None:
        self.data["artifacts"]["traceability"] = self.fixture.ref("traceability.md")
        if replan:
            self.data["gate_plan"] = build_gate_plan(
                self.data["change"], stage=self.data["stage"],
                impact_fingerprint=compute_impact_fingerprint(self.data, self.root),
                command_fingerprints=compute_command_fingerprints(self.data, self.root),
            )
        self.fixture.path.write_text(json.dumps(self.data), encoding="utf-8")

    def issues(self):
        return validate_traceability(self.path, project_root=self.root,
                                     delivery_contract_path=self.fixture.path)

    def test_valid_small_plan_allows_na_without_self_receipt_cycle(self) -> None:
        self.assertEqual([], self.issues())
        self.assertIn("missing-gate-receipt", {
            issue.code for issue in validate_delivery_contract(self.fixture.path, project_root=self.root)
        })

    def test_legacy_without_contract_remains_strict(self) -> None:
        self.assertEqual(2, sum(issue.code == "invalid-na" for issue in
                                validate_traceability(self.path, project_root=self.root)))

    def test_applicable_swimlane_still_requires_flow(self) -> None:
        self.data["change"]["swimlane_applicable"] = True
        self.save()
        self.assertIn("Flow 不允许 N/A", [issue.message for issue in self.issues()])

    def test_required_black_box_cannot_be_skipped(self) -> None:
        self.data["change"].update(risk_level="standard", surfaces=["behavior-change"])
        text = self.path.read_text(encoding="utf-8").replace("Risk level: small", "Risk level: standard")
        text = text.replace("Change surfaces: internal", "Change surfaces: behavior-change")
        self.path.write_text(text, encoding="utf-8")
        self.save()
        self.assertIn("Black-box result 不允许 N/A", [issue.message for issue in self.issues()])

    def test_stale_plan_and_trace_hash_fail_closed(self) -> None:
        self.data["gate_plan"]["required_command_ids"] = []
        self.save(replan=False)
        self.assertTrue(self.issues())
        self.save()
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertTrue(self.issues())

    def test_other_requirement_does_not_inherit_workset_exemption(self) -> None:
        self.path.write_text(self.path.read_text(encoding="utf-8").replace("REQ-001", "REQ-002"), encoding="utf-8")
        self.save()
        self.assertEqual(2, sum(issue.code == "invalid-na" for issue in self.issues()))

    def test_candidate_metadata_mismatch_fails_closed(self) -> None:
        for field in ("code_version", "build_id", "environment_id"):
            with self.subTest(field=field):
                previous = self.data["identity"][field]
                self.data["identity"][field] = "other-candidate"
                self.save()
                self.assertTrue(self.issues())
                self.data["identity"][field] = previous

    def test_cli_accepts_bound_plan(self) -> None:
        result = subprocess.run([
            sys.executable, str(Path(__file__).with_name("validate_traceability.py")),
            str(self.path), "--project-root", str(self.root),
            "--delivery-contract", str(self.fixture.path), "--json",
        ], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], json.loads(result.stdout)["issues"])


if __name__ == "__main__":
    unittest.main()
