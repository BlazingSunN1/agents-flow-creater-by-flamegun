from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from delivery_gate_planner import build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint
from validate_delivery_contract import validate_delivery_contract


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets" / "delivery-contract.template.json"


class DeliveryContractValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        for relative in (
            "requirements/baseline.md",
            "docs/traceability.md",
            "docs/questions.json",
            "docs/development-plan.md",
            "docs/progress.md",
            "docs/project-commands.json",
            "docs/commands.txt",
            "src/module.py",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        command_ids = (
            "automated_review", "code_standards", "context_manifest", "delivery_bundle",
            "delivery_contract", "multi_agent_evidence", "swimlane_evidence", "swimlane_freshness",
            "native_mobile_tests", "targeted_tests", "traceability", "full_test_or_build",
            "atomic_record_update",
        )
        source_command = "python3 -m unittest"
        (self.root / "docs/commands.txt").write_text(source_command, encoding="utf-8")
        (self.root / "docs/project-commands.json").write_text(json.dumps({
            "schema_version": 1,
            "frontend_applicable": False,
            "frontend_preview_url": "N/A: not a web frontend",
            "frontend_preview_root": "N/A: not a web frontend",
            "frontend_entry_artifact": "N/A: not a web frontend",
            "commands": [{
                "id": command_id,
                "argv": ["python3", "-m", "unittest"],
                "source": "docs/commands.txt",
                "source_selector": source_command,
                "source_command": source_command,
                "working_directory": ".",
                "applicability": "required",
            } for command_id in command_ids],
        }), encoding="utf-8")
        self.path = self.root / "docs/delivery-contract.json"
        self.path.write_text(json.dumps(self.contract(), indent=2), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ref(self, path: str) -> dict[str, str]:
        return {
            "path": path,
            "sha256": hashlib.sha256((self.root / path).read_bytes()).hexdigest(),
        }

    def contract(self) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": 1,
            "contract_id": "delivery-run-1",
            "stage": "closure_candidate",
            "status": "closure_candidate",
            "baseline": {
                "version": "req-v1",
                **self.ref("requirements/baseline.md"),
            },
            "artifacts": {
                "traceability": self.ref("docs/traceability.md"),
                "questions": self.ref("docs/questions.json"),
                "development_plan": self.ref("docs/development-plan.md"),
                "progress": self.ref("docs/progress.md"),
                "command_manifest": self.ref("docs/project-commands.json"),
            },
            "identity": {
                "code_version": "code-v1",
                "build_id": "build-1",
                "environment_id": "local-test",
            },
            "change": {
                "requirement_ids": ["REQ-001"],
                "modules": ["module"],
                "changed_files": ["src/module.py"],
                "configuration_files": [],
                "input_files": [],
                "direct_dependency_boundaries": "direct callers and tests",
                "risk_level": "standard",
                "risk_reason": "observable behavior changed",
                "surfaces": ["behavior-change"],
                "flow_impact": "none",
                "frontend_applicable": False,
                "swimlane_applicable": True,
                "cross_module": False,
                "human_review_triggered": False,
            },
            "repair_policy": {
                "max_rounds": 3,
                "same_failure_limit": 2,
                "regression_test_before_fix": True,
                "on_exhaustion": "block_completion_and_record_open_defect",
            },
            "gate_plan": {},
            "gate_receipts": {},
        }
        impact = compute_impact_fingerprint(data, self.root)
        data["gate_plan"] = build_gate_plan(
            data["change"], stage="closure_candidate", impact_fingerprint=impact,
            command_fingerprints=compute_command_fingerprints(data, self.root),
        )
        self._write_gate_receipts(data)
        return data

    def _write_gate_receipts(self, data: dict[str, object]) -> None:
        receipts: dict[str, object] = {}
        for command_id, fingerprint in data["gate_plan"]["gate_input_fingerprints"].items():
            output_path = f"docs/gate-output-{command_id}.txt"
            receipt_path = f"docs/gate-receipt-{command_id}.json"
            (self.root / output_path).write_text(f"passed {command_id}", encoding="utf-8")
            receipt = {
                "schema_version": 1,
                "command_id": command_id,
                "gate_input_fingerprint": fingerprint,
                "verdict": "pass",
                "run_id": f"run-{command_id}",
                "output_path": output_path,
                "output_sha256": self.ref(output_path)["sha256"],
            }
            (self.root / receipt_path).write_text(json.dumps(receipt), encoding="utf-8")
            receipts[command_id] = self.ref(receipt_path)
        data["gate_receipts"] = receipts

    def codes(self) -> set[str]:
        return {item.code for item in validate_delivery_contract(self.path, project_root=self.root)}

    def test_public_template_is_valid(self) -> None:
        self.assertEqual([], validate_delivery_contract(PUBLIC_TEMPLATE, project_root=SKILL_ROOT, template=True))

    def test_valid_contract_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_small_completion_rejects_structurally_invalid_command_manifest(self) -> None:
        data = self.contract()
        data["stage"] = "completion"
        data["status"] = "completed"
        data["change"].update({
            "risk_level": "small",
            "risk_reason": "internal refactor",
            "surfaces": ["internal"],
            "swimlane_applicable": False,
        })
        manifest_path = self.root / "docs/project-commands.json"
        manifest_path.write_text(json.dumps({
            "commands": [{"id": "delivery_contract", "applicability": "required"}],
        }), encoding="utf-8")
        data["artifacts"]["command_manifest"] = self.ref("docs/project-commands.json")
        impact = compute_impact_fingerprint(data, self.root)
        data["gate_plan"] = build_gate_plan(
            data["change"], stage="completion", impact_fingerprint=impact,
            command_fingerprints=compute_command_fingerprints(data, self.root),
        )
        self._write_gate_receipts(data)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-command-manifest-fields", self.codes())

    def test_aggregate_validators_do_not_require_self_referential_receipts(self) -> None:
        data = self.contract()
        self.assertTrue({"delivery_contract", "delivery_bundle"} <= set(data["gate_plan"]["required_command_ids"]))
        self.assertTrue({"delivery_contract", "delivery_bundle"}.isdisjoint(data["gate_receipts"]))
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(set(), self.codes())

        data["gate_receipts"]["delivery_contract"] = data["gate_receipts"]["targeted_tests"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unexpected-gate-receipt", self.codes())

    def test_artifact_or_changed_file_drift_invalidates_contract(self) -> None:
        (self.root / "src/module.py").write_text("changed", encoding="utf-8")
        self.assertIn("stale-gate-plan", self.codes())
        (self.root / "docs/questions.json").write_text("changed", encoding="utf-8")
        self.assertIn("stale-artifact-sha256", self.codes())

    def test_manually_weakened_gate_plan_is_rejected(self) -> None:
        data = self.contract()
        data["gate_plan"]["required_command_ids"].remove("automated_review")
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-gate-plan", self.codes())

    def test_planned_command_must_be_enabled(self) -> None:
        data = self.contract()
        manifest_path = self.root / "docs/project-commands.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        next(item for item in manifest["commands"] if item["id"] == "automated_review")["applicability"] = "N/A: disabled"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        data["artifacts"]["command_manifest"] = self.ref("docs/project-commands.json")
        impact = compute_impact_fingerprint(data, self.root)
        data["gate_plan"] = build_gate_plan(
            data["change"], stage="closure_candidate", impact_fingerprint=impact,
            command_fingerprints=compute_command_fingerprints(data, self.root),
        )
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("planned-command-not-enabled", self.codes())

    def test_unknown_fields_and_boolean_integer_aliases_fail_closed(self) -> None:
        data = self.contract()
        data["unknown"] = "hidden"
        data["repair_policy"]["max_rounds"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-contract-fields", self.codes())
        self.assertIn("invalid-repair-policy", self.codes())

    def test_completion_rejects_uncertain_flow_impact(self) -> None:
        data = self.contract()
        data["stage"] = "completion"
        data["status"] = "completed"
        data["change"]["flow_impact"] = "uncertain"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-gate-plan-input", self.codes())

    def test_candidate_identity_must_be_nonempty_strings(self) -> None:
        for identity in (
            {"code_version": "", "build_id": "", "environment_id": ""},
            {"code_version": True, "build_id": [], "environment_id": {}},
        ):
            data = self.contract()
            data["identity"] = identity
            self.path.write_text(json.dumps(data), encoding="utf-8")
            self.assertIn("invalid-candidate-identity", self.codes())

    def test_gate_receipt_must_bind_current_gate_fingerprint(self) -> None:
        data = self.contract()
        command_id = "targeted_tests"
        receipt_ref = data["gate_receipts"][command_id]
        receipt_path = self.root / receipt_ref["path"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["gate_input_fingerprint"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        data["gate_receipts"][command_id] = self.ref(receipt_ref["path"])
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-gate-receipt", self.codes())

    def test_closure_requires_receipt_for_every_planned_gate(self) -> None:
        data = self.contract()
        data["gate_receipts"].pop("targeted_tests")
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-gate-receipt", self.codes())


if __name__ == "__main__":
    unittest.main()
