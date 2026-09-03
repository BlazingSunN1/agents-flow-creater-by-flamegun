from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from delivery_gate_planner import (
    GatePlanError, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)


class DeliveryGatePlannerTests(unittest.TestCase):
    def test_planner_cli_cannot_directly_write_shared_contract(self) -> None:
        source = (Path(__file__).parent / "plan_delivery_gates.py").read_text(encoding="utf-8")
        self.assertNotIn('add_argument("--write"', source)
        self.assertNotIn("os.replace", source)

    def change(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "delivery_phase": "result_candidate",
            "baseline_frozen": False,
            "risk_level": "small",
            "surfaces": ["internal"],
            "flow_impact": "none",
            "frontend_applicable": False,
            "swimlane_applicable": False,
            "cross_module": False,
            "human_review_triggered": False,
        }
        value.update(overrides)
        return value

    def test_small_implementation_uses_quick_without_extra_agents(self) -> None:
        plan = build_gate_plan(self.change(), stage="implementation", impact_fingerprint="a" * 64)
        self.assertEqual("quick", plan["validation_tier"])
        self.assertEqual([], plan["independent_roles"])
        self.assertNotIn("automated_review", plan["required_command_ids"])

    def test_result_candidate_runs_only_affected_business_checks(self) -> None:
        plan = build_gate_plan(
            self.change(
                risk_level="high-risk",
                surfaces=["auth", "security"],
            ),
            stage="implementation",
            impact_fingerprint="f" * 64,
        )
        self.assertEqual(
            ["real_entry_acceptance", "targeted_tests"],
            plan["required_command_ids"],
        )
        for deferred in (
            "code_standards", "full_test_or_build", "traceability",
            "context_manifest", "automated_review", "multi_agent_evidence",
        ):
            self.assertNotIn(deferred, plan["required_command_ids"])

    def test_cross_module_aggregation_waits_until_closure(self) -> None:
        pre_closure = build_gate_plan(
            self.change(
                risk_level="high-risk",
                surfaces=["cross-module"],
                cross_module=True,
            ),
            stage="implementation",
            impact_fingerprint="7" * 64,
        )
        self.assertNotIn("system_delivery_bundle", pre_closure["required_command_ids"])
        self.assertEqual([], pre_closure["aggregate_command_ids"])

        closure = build_gate_plan(
            self.change(
                delivery_phase="closure_candidate",
                baseline_frozen=True,
                risk_level="high-risk",
                surfaces=["cross-module"],
                cross_module=True,
            ),
            stage="closure_candidate",
            impact_fingerprint="7" * 64,
        )
        self.assertIn("system_delivery_bundle", closure["required_command_ids"])
        self.assertIn("system_delivery_bundle", closure["aggregate_command_ids"])

    def test_affected_checks_passed_is_a_representable_unfrozen_phase(self) -> None:
        plan = build_gate_plan(
            self.change(delivery_phase="affected_checks_passed"),
            stage="implementation",
            impact_fingerprint="e" * 64,
        )
        self.assertEqual(
            ["real_entry_acceptance", "targeted_tests"],
            plan["required_command_ids"],
        )
        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(delivery_phase="affected_checks_passed", baseline_frozen=True),
                stage="implementation",
                impact_fingerprint="e" * 64,
            )

    def test_hardening_requires_frozen_baseline_and_adds_mapped_quality(self) -> None:
        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(delivery_phase="hardening"),
                stage="implementation",
                impact_fingerprint="f" * 64,
            )
        plan = build_gate_plan(
            self.change(delivery_phase="hardening", baseline_frozen=True),
            stage="implementation",
            impact_fingerprint="f" * 64,
        )
        self.assertIn("code_standards", plan["required_command_ids"])
        self.assertNotIn("full_test_or_build", plan["required_command_ids"])
        self.assertNotIn("traceability", plan["required_command_ids"])
        self.assertNotIn("context_manifest", plan["required_command_ids"])

    def test_small_completion_stays_single_agent_and_avoids_heavy_bundle(self) -> None:
        plan = build_gate_plan(
            self.change(delivery_phase="completed", baseline_frozen=True),
            stage="completion", impact_fingerprint="1" * 64,
        )
        self.assertEqual("affected", plan["validation_tier"])
        self.assertEqual([], plan["independent_roles"])
        self.assertNotIn("multi_agent_evidence", plan["required_command_ids"])
        self.assertNotIn("delivery_bundle", plan["required_command_ids"])

    def test_standard_closure_uses_affected_and_review(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="closure_candidate",
                baseline_frozen=True,
                risk_level="standard",
                surfaces=["behavior-change"],
            ),
            stage="closure_candidate",
            impact_fingerprint="b" * 64,
        )
        self.assertEqual("affected", plan["validation_tier"])
        self.assertIn("CHANGE_REVIEW", plan["independent_roles"])
        self.assertIn("automated_review", plan["required_command_ids"])
        self.assertNotIn("full_test_or_build", plan["required_command_ids"])

    def test_high_risk_completion_uses_full_and_independent_roles(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="completed",
                baseline_frozen=True,
                risk_level="high-risk",
                surfaces=["public-api", "cross-module"],
                cross_module=True,
                flow_impact="changed",
                swimlane_applicable=True,
            ),
            stage="completion",
            impact_fingerprint="c" * 64,
        )
        self.assertEqual("full", plan["validation_tier"])
        self.assertEqual(
            ["ACCEPTANCE_CASES", "BLACK_BOX", "CHANGE_REVIEW", "REQUIREMENT_REVIEW", "SPECIALIST_REVIEW"],
            plan["independent_roles"],
        )
        self.assertIn("full_test_or_build", plan["required_command_ids"])
        self.assertIn("system_delivery_bundle", plan["required_command_ids"])
        self.assertIn("swimlane_evidence", plan["required_command_ids"])

    def test_ui_completion_requires_browser_evidence_but_not_mobile_by_default(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="completed",
                baseline_frozen=True,
                risk_level="standard",
                surfaces=["ui", "user-visible"],
                frontend_applicable=True,
                flow_impact="changed",
                swimlane_applicable=True,
            ),
            stage="completion",
            impact_fingerprint="d" * 64,
        )
        self.assertIn("UI_UX", plan["independent_roles"])
        self.assertIn("frontend_e2e", plan["required_command_ids"])
        self.assertNotIn("mobile_frontend_e2e", plan["required_command_ids"])

    def test_explicit_mobile_completion_requires_frontend_mobile_and_black_box(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="completed", baseline_frozen=True,
                risk_level="standard", surfaces=["mobile", "touch"],
                frontend_applicable=True,
            ),
            stage="completion", impact_fingerprint="9" * 64,
        )
        self.assertIn("BLACK_BOX", plan["independent_roles"])
        self.assertIn("frontend_evidence", plan["required_command_ids"])
        self.assertIn("frontend_e2e", plan["required_command_ids"])
        self.assertIn("mobile_frontend_e2e", plan["required_command_ids"])

    def test_native_mobile_does_not_require_browser_but_gets_native_verification(self) -> None:
        for surface in ("mobile", "native-mobile"):
            with self.subTest(surface=surface):
                plan = build_gate_plan(
                    self.change(
                        delivery_phase="completed", baseline_frozen=True,
                        risk_level="standard", surfaces=[surface],
                    ),
                    stage="completion", impact_fingerprint="8" * 64,
                )
                self.assertIn("native_mobile_tests", plan["required_command_ids"])
                self.assertNotIn("frontend_e2e", plan["required_command_ids"])
                self.assertNotIn("mobile_frontend_e2e", plan["required_command_ids"])

        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(
                    delivery_phase="completed", baseline_frozen=True,
                    risk_level="standard", surfaces=["native-mobile"],
                    frontend_applicable=True,
                ),
                stage="completion", impact_fingerprint="8" * 64,
            )

    def test_combined_web_and_native_mobile_requires_both_gate_families(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="completed",
                baseline_frozen=True,
                risk_level="standard",
                surfaces=["ui", "native-mobile"],
                frontend_applicable=True,
            ),
            stage="completion", impact_fingerprint="4" * 64,
        )
        self.assertIn("frontend_e2e", plan["required_command_ids"])
        self.assertIn("native_mobile_tests", plan["required_command_ids"])
        self.assertIn("UI_UX", plan["independent_roles"])

    def test_mobile_web_requires_frontend_validation(self) -> None:
        for surface in ("mobile-web", "responsive"):
            with self.subTest(surface=surface), self.assertRaises(GatePlanError):
                build_gate_plan(
                    self.change(
                        delivery_phase="completed", baseline_frozen=True,
                        risk_level="standard", surfaces=[surface],
                    ),
                    stage="completion", impact_fingerprint="8" * 64,
                )

    def test_human_review_trigger_requests_independent_change_review(self) -> None:
        plan = build_gate_plan(
            self.change(human_review_triggered=True),
            stage="implementation", impact_fingerprint="6" * 64,
        )
        self.assertIn("CHANGE_REVIEW", plan["independent_roles"])
        self.assertIn("multi_agent_evidence", plan["required_command_ids"])
        self.assertIn("automated_review", plan["required_command_ids"])
        self.assertNotIn("delivery_bundle", plan["required_command_ids"])
        self.assertEqual([], plan["aggregate_command_ids"])

    def test_user_visible_text_alone_does_not_create_ui_ux_agent(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="closure_candidate", baseline_frozen=True,
                risk_level="standard", surfaces=["user-visible"],
            ),
            stage="closure_candidate", impact_fingerprint="5" * 64,
        )
        self.assertNotIn("UI_UX", plan["independent_roles"])

    def test_flow_none_completion_checks_freshness_only_when_swimlane_applies(self) -> None:
        plan = build_gate_plan(
            self.change(delivery_phase="completed", baseline_frozen=True, swimlane_applicable=True),
            stage="completion", impact_fingerprint="3" * 64,
        )
        self.assertIn("swimlane_freshness", plan["required_command_ids"])
        self.assertNotIn("swimlane_evidence", plan["required_command_ids"])

        no_swimlane = build_gate_plan(
            self.change(delivery_phase="completed", baseline_frozen=True, swimlane_applicable=False),
            stage="completion", impact_fingerprint="2" * 64,
        )
        self.assertNotIn("swimlane_freshness", no_swimlane["required_command_ids"])
        self.assertNotIn("swimlane_evidence", no_swimlane["required_command_ids"])

    def test_flow_change_requires_swimlane_applicability(self) -> None:
        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(flow_impact="changed", swimlane_applicable=False),
                stage="implementation", impact_fingerprint="0" * 64,
            )

    def test_final_aggregate_validators_are_outside_receipt_graph(self) -> None:
        plan = build_gate_plan(
            self.change(
                delivery_phase="closure_candidate", baseline_frozen=True,
                risk_level="standard", surfaces=["behavior-change"],
            ),
            stage="closure_candidate", impact_fingerprint="a" * 64,
        )
        self.assertEqual(
            ["delivery_bundle", "delivery_contract"],
            plan["aggregate_command_ids"],
        )
        for command_id in plan["aggregate_command_ids"]:
            self.assertIn(command_id, plan["required_command_ids"])
            self.assertNotIn(command_id, plan["gate_input_fingerprints"])

    def test_underclassified_or_unresolved_completion_fails(self) -> None:
        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(surfaces=["security"]),
                stage="implementation",
                impact_fingerprint="e" * 64,
            )
        with self.assertRaises(GatePlanError):
            build_gate_plan(
                self.change(
                    delivery_phase="completed", baseline_frozen=True,
                    flow_impact="uncertain",
                ),
                stage="completion",
                impact_fingerprint="f" * 64,
            )

    def test_same_inputs_produce_byte_identical_plan(self) -> None:
        change = self.change(
            delivery_phase="closure_candidate", baseline_frozen=True,
            risk_level="standard", surfaces=["behavior-change"],
        )
        first = build_gate_plan(
            change, stage="closure_candidate", impact_fingerprint="7" * 64,
            command_fingerprints={"targeted_tests": "8" * 64},
        )
        second = build_gate_plan(
            change, stage="closure_candidate", impact_fingerprint="7" * 64,
            command_fingerprints={"targeted_tests": "8" * 64},
        )
        canonical = lambda value: json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(canonical(first), canonical(second))

    def test_progress_churn_does_not_invalidate_candidate_or_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._fingerprint_contract(root)
            before = compute_impact_fingerprint(contract, root)
            commands = compute_command_fingerprints(contract, root)
            plan_before = build_gate_plan(
                contract["change"], stage="closure_candidate",
                impact_fingerprint=before, command_fingerprints=commands,
            )
            (root / "progress.md").write_text("later progress", encoding="utf-8")
            after = compute_impact_fingerprint(contract, root)
            plan_after = build_gate_plan(
                contract["change"], stage="closure_candidate",
                impact_fingerprint=after, command_fingerprints=commands,
            )
            self.assertEqual(before, after)
            self.assertEqual(plan_before, plan_after)

    def test_one_command_change_invalidates_only_its_gate_input(self) -> None:
        change = self.change(risk_level="standard", surfaces=["behavior-change"])
        change.update(delivery_phase="closure_candidate", baseline_frozen=True)
        initial = {"targeted_tests": "1" * 64, "code_standards": "2" * 64}
        changed = {**initial, "targeted_tests": "3" * 64}
        before = build_gate_plan(
            change, stage="closure_candidate", impact_fingerprint="4" * 64,
            command_fingerprints=initial,
        )["gate_input_fingerprints"]
        after = build_gate_plan(
            change, stage="closure_candidate", impact_fingerprint="4" * 64,
            command_fingerprints=changed,
        )["gate_input_fingerprints"]
        self.assertNotEqual(before["targeted_tests"], after["targeted_tests"])
        for command_id in set(before) - {"targeted_tests"}:
            self.assertEqual(before[command_id], after[command_id])

    def _fingerprint_contract(self, root: Path) -> dict[str, object]:
        for name in ("baseline.md", "trace.md", "questions.json", "plan.md", "progress.md", "commands.json", "code.py"):
            (root / name).write_text(name, encoding="utf-8")
        commands = {"commands": [{"id": "targeted_tests", "applicability": "required"}]}
        (root / "commands.json").write_text(json.dumps(commands), encoding="utf-8")
        reference = lambda name: {
            "path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
        }
        return {
            "stage": "closure_candidate", "baseline": {"version": "v1", **reference("baseline.md")},
            "artifacts": {
                "traceability": reference("trace.md"), "questions": reference("questions.json"),
                "development_plan": reference("plan.md"), "progress": reference("progress.md"),
                "command_manifest": reference("commands.json"),
            },
            "identity": {"code_version": "v1", "build_id": "b1", "environment_id": "local"},
            "change": {
                **self.change(
                    delivery_phase="closure_candidate", baseline_frozen=True,
                    risk_level="standard", surfaces=["behavior-change"],
                ),
                "changed_files": ["code.py"], "configuration_files": [], "input_files": [],
            },
        }


if __name__ == "__main__":
    unittest.main()
