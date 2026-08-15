from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_traceability as trace_support
from validate_multi_agent_evidence import _trace_role_paths, _validate_hashed_path, validate_multi_agent_evidence
from validate_traceability import _parse_metadata


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets/multi-agent-evidence.template.json"


class MultiAgentEvidenceValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = trace_support.TraceabilityValidatorTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.path = self.root / "multi-agent.json"
        self.context = self.root / "context.md"
        self.context.write_text(
            "- Baseline artifact: requirements/baseline.md\n- Requirement IDs: REQ-001\n"
            "- Changed files: src/module.py\n- Configuration files: N/A: none\n- Input files: N/A: none\n",
            encoding="utf-8",
        )
        for relative in ("evidence/change-input.md", "evidence/change-output.md"):
            target = self.root / relative
            target.write_text(relative, encoding="utf-8")
        self._write_inputs()
        self._write_outputs()
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def artifact(self, role: str, run_id: str, input_path: str, output_path: str) -> dict[str, object]:
        return {
            "role": role,
            "run_id": run_id,
            "provider": "independent-agent",
            "focus": f"{role} bounded review",
            "input_manifest": input_path,
            "input_sha256": hashlib.sha256((self.root / input_path).read_bytes()).hexdigest(),
            "output_evidence": output_path,
            "output_sha256": hashlib.sha256((self.root / output_path).read_bytes()).hexdigest(),
            "may_modify_code": False,
            "may_modify_shared_records": False,
            "received_full_chat": False,
            "received_other_agent_reasoning": False,
            "accepted_implementation_self_report": False,
            "verdict": "pass",
        }

    def valid_data(self) -> dict[str, object]:
        metadata = _parse_metadata(self.fixture.matrix.read_text(encoding="utf-8"))
        gates = [
            self.artifact("UI_UX", "ui-run-1", "evidence/ui-input.md", "evidence/ui-output.md"),
            self.artifact("ACCEPTANCE_CASES", "at-run-1", "evidence/at-input.md", "evidence/at-output.md"),
            self.artifact("CHANGE_REVIEW", "change-run-1", "evidence/change-input.md", "evidence/change-output.md"),
            self.artifact("BLACK_BOX", "bb-run-1", "evidence/bb-input.md", "evidence/bb-output.md"),
        ]
        return {
            "schema_version": 1,
            "stage": "completion",
            "baseline_version": metadata["Baseline version"],
            "baseline_sha256": metadata["Baseline SHA-256"],
            "code_version": metadata["Code version"],
            "build_id": metadata["Build ID"],
            "implementation_run_id": metadata["Implementation run ID"],
            "single_writer_run_id": metadata["Implementation run ID"],
            "gates": gates,
            "open_disagreements": [],
        }

    def codes(self) -> set[str]:
        return {
            issue.code
            for issue in validate_multi_agent_evidence(
                self.path,
                trace_path=self.fixture.matrix,
                context_path=self.context,
                project_root=self.root,
            )
            if issue.severity == "error"
        }

    def test_valid_standard_ui_evidence_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_public_template_structure_passes_and_rejects_nested_gate_bypass(self) -> None:
        self.assertEqual([], validate_multi_agent_evidence(
            PUBLIC_TEMPLATE, trace_path=self.fixture.matrix, context_path=self.context,
            project_root=self.root, template=True,
        ))
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["gates"] = [{"role": True, "may_modify_code": True}]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_multi_agent_evidence(
            self.path, trace_path=self.fixture.matrix, context_path=self.context,
            project_root=self.root, template=True,
        )}
        self.assertIn("invalid-gate-fields", codes)

        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["open_disagreements"] = ["unresolved"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_multi_agent_evidence(
            self.path, trace_path=self.fixture.matrix, context_path=self.context,
            project_root=self.root, template=True,
        )}
        self.assertIn("open-agent-disagreement", codes)

    def test_boolean_schema_version_is_rejected(self) -> None:
        data = self.valid_data()
        data["schema_version"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-schema-version", self.codes())

    def test_top_level_identity_fields_must_be_nonempty_strings(self) -> None:
        data = self.valid_data()
        data["build_id"] = 456
        data["implementation_run_id"] = 123
        data["single_writer_run_id"] = 123
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-agent-evidence-types", self.codes())

    def test_top_level_and_gate_unknown_or_duplicate_fields_fail_closed(self) -> None:
        for target in ("top", "gate"):
            with self.subTest(target=target):
                data = self.valid_data()
                if target == "top":
                    data["unknown_failure_state"] = "P1 unresolved"
                else:
                    data["gates"][0]["unknown_failure_state"] = "P1 unresolved"
                self.path.write_text(json.dumps(data), encoding="utf-8")
                self.assertTrue(
                    {"invalid-agent-evidence-fields", "invalid-gate-fields"} & self.codes()
                )
        raw = json.dumps(self.valid_data()).replace(
            '"schema_version": 1', '"schema_version": 999, "schema_version": 1', 1,
        )
        self.path.write_text(raw, encoding="utf-8")
        self.assertIn("invalid-agent-evidence", self.codes())

    def test_writer_and_read_only_boundaries_fail_closed(self) -> None:
        data = self.valid_data()
        data["single_writer_run_id"] = "change-run-1"
        data["gates"][0]["may_modify_code"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"multiple-or-wrong-writer", "unsafe-agent-boundary"} <= self.codes())

    def test_reused_run_and_open_disagreement_fail(self) -> None:
        data = self.valid_data()
        data["gates"][1]["run_id"] = "ui-run-1"
        data["open_disagreements"] = ["scope mismatch"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"reused-or-missing-agent-run", "open-agent-disagreement"} <= self.codes())

    def test_stale_artifact_fails(self) -> None:
        (self.root / "evidence/change-output.md").write_text("changed", encoding="utf-8")
        self.assertIn("stale-agent-artifact", self.codes())

    def test_missing_input_or_output_returns_structured_issue_without_crash(self) -> None:
        for relative in ("evidence/bb-input.md", "evidence/bb-output.md"):
            with self.subTest(relative=relative):
                artifact = self.root / relative
                payload = artifact.read_bytes()
                artifact.unlink()
                try:
                    self.assertIn("missing-agent-artifact", self.codes())
                finally:
                    artifact.write_bytes(payload)

    def test_high_risk_requires_requirement_and_specialist_reviews(self) -> None:
        trace = self.fixture.matrix.read_text(encoding="utf-8")
        trace = trace.replace("Risk level: standard", "Risk level: high-risk")
        trace = trace.replace("Change surfaces: ui,user-visible", "Change surfaces: auth,security")
        self.fixture.matrix.write_text(trace, encoding="utf-8")
        self.assertIn("missing-agent-role", self.codes())

    def test_nonapplicable_extra_role_is_rejected(self) -> None:
        trace = self.fixture.matrix.read_text(encoding="utf-8").replace("Risk level: standard", "Risk level: small").replace("Change surfaces: ui,user-visible", "Change surfaces: internal")
        self.fixture.matrix.write_text(trace, encoding="utf-8")
        self.assertIn("nonapplicable-agent-role", self.codes())

    def test_shared_record_writer_boundary_is_rejected(self) -> None:
        data = self.valid_data()
        data["gates"][0]["may_modify_shared_records"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-agent-boundary", self.codes())

    def test_symlinked_agent_artifact_cannot_escape_project(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside-agent.md"
        outside.write_text("outside", encoding="utf-8")
        target = self.root / "evidence/change-output.md"
        target.unlink()
        target.symlink_to(outside)
        data = self.valid_data()
        for gate in data["gates"]:
            if gate["role"] == "CHANGE_REVIEW":
                gate["output_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        try:
            self.assertIn("unsafe-agent-artifact-path", self.codes())
        finally:
            outside.unlink(missing_ok=True)

    def test_path_alias_cannot_reuse_another_role_artifact(self) -> None:
        data = self.valid_data()
        change = next(gate for gate in data["gates"] if gate["role"] == "CHANGE_REVIEW")
        ui = next(gate for gate in data["gates"] if gate["role"] == "UI_UX")
        change["input_manifest"] = "evidence/./ui-input.md"
        change["input_sha256"] = ui["input_sha256"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("reused-agent-artifact", self.codes())

    def test_hardlinked_outputs_cannot_claim_independent_evidence(self) -> None:
        change = self.root / "evidence/change-output.md"
        acceptance = self.root / "evidence/at-output.md"
        change.unlink()
        os.link(acceptance, change)
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("reused-agent-artifact", self.codes())

    def test_agent_output_cannot_reuse_changed_source(self) -> None:
        data = self.valid_data()
        change = next(gate for gate in data["gates"] if gate["role"] == "CHANGE_REVIEW")
        change["output_evidence"] = "src/module.py"
        change["output_sha256"] = hashlib.sha256((self.root / "src/module.py").read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("agent-output-reuses-workset", self.codes())

    def test_agent_output_must_bind_role_run_and_verdict(self) -> None:
        output = self.root / "evidence/change-output.md"
        data = json.loads(output.read_text(encoding="utf-8"))
        data["run_id"] = "stale-run"
        output.write_text(json.dumps(data), encoding="utf-8")
        evidence = self.valid_data()
        self.path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("stale-agent-output", self.codes())

    def test_role_inputs_must_not_reuse_identical_content(self) -> None:
        source = self.root / "evidence/ui-input.md"
        target = self.root / "evidence/change-input.md"
        target.write_bytes(source.read_bytes())
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("reused-agent-artifact-content", self.codes())

    def test_role_inputs_cannot_bypass_content_reuse_with_whitespace(self) -> None:
        source = self.root / "evidence/ui-input.md"
        target = self.root / "evidence/change-input.md"
        target.write_bytes(source.read_bytes() + b"\n")
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("reused-agent-artifact-content", self.codes())

    def test_agent_run_id_must_be_a_string(self) -> None:
        data = self.valid_data()
        change = next(gate for gate in data["gates"] if gate["role"] == "CHANGE_REVIEW")
        change["run_id"] = 123
        output = self.root / "evidence/change-output.md"
        payload = json.loads(output.read_text(encoding="utf-8"))
        payload["run_id"] = 123
        output.write_text(json.dumps(payload), encoding="utf-8")
        change["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("reused-or-missing-agent-run", self.codes())

    def test_agent_artifact_path_must_be_a_json_string(self) -> None:
        alias = self.root / "True"
        alias.write_text("valid alias target", encoding="utf-8")
        issues = []
        resolved = _validate_hashed_path(
            True, hashlib.sha256(alias.read_bytes()).hexdigest(), self.root,
            "UI_UX", issues,
        )
        self.assertIsNone(resolved)
        self.assertIn("unsafe-agent-artifact-path", {item.code for item in issues})

    def test_role_input_rejects_full_chat_or_unrelated_paths(self) -> None:
        unrelated = self.root / "docs/full-chat.md"
        unrelated.parent.mkdir(exist_ok=True)
        unrelated.write_text("full chat and implementation self-report", encoding="utf-8")
        input_path = self.root / "evidence/bb-input.md"
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        payload["artifacts"].append(self._input_artifact("docs/full-chat.md"))
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-agent-input-paths", self.codes())

    def test_role_input_requires_all_role_specific_artifacts(self) -> None:
        input_path = self.root / "evidence/bb-input.md"
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        payload["artifacts"] = [self._input_artifact("requirements/baseline.md")]
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-agent-input-paths", self.codes())

    def test_role_input_artifact_hash_detects_post_capture_drift(self) -> None:
        (self.root / "tests/acceptance.md").write_text("changed after capture", encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-agent-input-paths", self.codes())

    def test_role_input_rejects_unstructured_self_report(self) -> None:
        input_path = self.root / "evidence/bb-input.md"
        input_path.write_text("Implementation self-report: all tests pass", encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-agent-input", self.codes())

    def test_role_input_exclusion_flags_must_be_json_booleans(self) -> None:
        for field in (
            "includes_full_chat", "includes_other_agent_reasoning",
            "includes_implementation_self_report",
        ):
            with self.subTest(field=field):
                self._write_inputs()
                input_path = self.root / "evidence/bb-input.md"
                payload = json.loads(input_path.read_text(encoding="utf-8"))
                payload[field] = 0
                input_path.write_text(json.dumps(payload), encoding="utf-8")
                self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
                self.assertIn("invalid-agent-input", self.codes())

    def test_agent_output_binds_exact_input_manifest_hash(self) -> None:
        input_path = self.root / "evidence/bb-input.md"
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        input_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("stale-agent-output", self.codes())

    def test_trace_role_paths_only_include_current_requirement_ids(self) -> None:
        text = self.fixture.matrix.read_text(encoding="utf-8").replace(
            "\n## Independent Gate Evidence",
            "\n| [REQ-002](requirements/other.md) | [FLOW-002](flows/other.html) | "
            "[FEAT-002](features/other.md) | [UI-002](ui/other.html) | "
            "[UT-002](tests/other-unit.md) | [AT-002](tests/other-at.md) | "
            "[MOD-002](src/other.py) | [BB-002](evidence/other.md) | completed |\n\n"
            "## Independent Gate Evidence",
        )
        paths = _trace_role_paths(text, {"REQ-001"})
        self.assertNotIn("flows/other.html", paths["UI_UX"])
        self.assertNotIn("src/other.py", paths["CHANGE_REVIEW"])

    def test_provider_and_focus_must_be_nonempty_strings(self) -> None:
        data = self.valid_data()
        data["gates"][0]["provider"] = {"name": "independent-agent"}
        data["gates"][0]["focus"] = ["ui"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-agent-scope", self.codes())

    def test_external_model_cannot_satisfy_native_black_box_gate(self) -> None:
        data = self.valid_data()
        black_box = next(item for item in data["gates"] if item["role"] == "BLACK_BOX")
        for provider in ("deepseek", "kimi", "multi-model-review-loop"):
            with self.subTest(provider=provider):
                black_box["provider"] = provider
                self.path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("external-provider-cannot-satisfy-native-gate", self.codes())

    def _write_outputs(self) -> None:
        metadata = _parse_metadata(self.fixture.matrix.read_text(encoding="utf-8"))
        roles = {
            "UI_UX": ("ui-run-1", "evidence/ui-input.md", "evidence/ui-output.md"),
            "ACCEPTANCE_CASES": ("at-run-1", "evidence/at-input.md", "evidence/at-output.md"),
            "CHANGE_REVIEW": ("change-run-1", "evidence/change-input.md", "evidence/change-output.md"),
            "BLACK_BOX": ("bb-run-1", "evidence/bb-input.md", "evidence/bb-output.md"),
        }
        for role, (run_id, input_relative, relative) in roles.items():
            payload = {
                "schema_version": 1, "role": role, "run_id": run_id,
                "baseline_version": metadata["Baseline version"],
                "baseline_sha256": metadata["Baseline SHA-256"],
                "code_version": metadata["Code version"],
                "input_sha256": hashlib.sha256((self.root / input_relative).read_bytes()).hexdigest(),
                "verdict": "pass", "findings": [],
            }
            (self.root / relative).write_text(json.dumps(payload), encoding="utf-8")

    def _write_inputs(self) -> None:
        metadata = _parse_metadata(self.fixture.matrix.read_text(encoding="utf-8"))
        roles = {
            "UI_UX": ("ui-run-1", "evidence/ui-input.md", ["requirements/baseline.md", "flows/system.html", "features/list.md", "ui/prototype.html"]),
            "ACCEPTANCE_CASES": ("at-run-1", "evidence/at-input.md", ["requirements/baseline.md", "features/list.md", "ui/prototype.html", "tests/unit.md", "tests/acceptance.md"]),
            "CHANGE_REVIEW": ("change-run-1", "evidence/change-input.md", ["requirements/baseline.md", "flows/system.html", "tests/unit.md", "src/module.py"]),
            "BLACK_BOX": ("bb-run-1", "evidence/bb-input.md", ["requirements/baseline.md", "ui/prototype.html", "tests/acceptance.md"]),
        }
        for role, (run_id, relative, paths) in roles.items():
            payload = {
                "schema_version": 1, "role": role, "run_id": run_id,
                "baseline_version": metadata["Baseline version"],
                "baseline_sha256": metadata["Baseline SHA-256"],
                "requirement_ids": ["REQ-001"],
                "artifacts": [self._input_artifact(item) for item in paths],
                "includes_full_chat": False, "includes_other_agent_reasoning": False,
                "includes_implementation_self_report": False,
            }
            (self.root / relative).write_text(json.dumps(payload), encoding="utf-8")

    def _input_artifact(self, relative: str) -> dict[str, str]:
        return {
            "path": relative,
            "sha256": hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
        }


if __name__ == "__main__":
    unittest.main()
