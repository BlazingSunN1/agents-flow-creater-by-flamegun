from __future__ import annotations

import json
import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_delivery_bundle as bundle_test_support
from validate_delivery_bundle import validate_delivery_bundle


class GoldenWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = bundle_test_support.DeliveryBundleValidatorTests()
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _codes(self, *, allow_passwords: bool = False) -> set[str]:
        return {
            issue.code
            for issue in validate_delivery_bundle(
                agents_path=self.fixture.agents,
                trace_path=self.fixture.trace_fixture.matrix,
                context_path=self.fixture.context,
                command_manifest_path=self.fixture.commands,
                multi_agent_evidence_path=self.fixture.multi_agent,
                swimlane_evidence_path=self.fixture.swimlane,
                frontend_evidence_path=self.fixture.frontend,
                project_root=self.fixture.root,
                allow_passwords=allow_passwords,
            )
            if issue.severity == "error"
        }

    def _make_non_ui(self, *, risk: str, reason: str, surfaces: str) -> None:
        trace = self.fixture.trace_fixture.matrix.read_text(encoding="utf-8")
        trace = trace.replace("Risk level: standard", f"Risk level: {risk}")
        trace = trace.replace("Risk reason: user-visible interaction", f"Risk reason: {reason}")
        trace = trace.replace("Change surfaces: ui,user-visible", f"Change surfaces: {surfaces}")
        trace = trace.replace("[UI-001](ui/prototype.html)", "N/A: no UI behavior")
        trace = trace.replace(
            "| UI_UX | required | ui-run-1 | req-v1 |",
            "| UI_UX | N/A: no UI behavior |  | req-v1 |",
        )
        trace = trace.replace(
            "[EVD-UI-001](evidence/ui-output.md) | pass |",
            "[EVD-UI-001](evidence/ui-output.md) | not_applicable |",
        )
        self.fixture.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.fixture.multi_agent.read_text(encoding="utf-8"))
        evidence["gates"] = [item for item in evidence["gates"] if item["role"] != "UI_UX"]
        if risk == "small":
            evidence["gates"] = [item for item in evidence["gates"] if item["role"] != "CHANGE_REVIEW"]
        if risk == "high-risk":
            for role, run_id in (("REQUIREMENT_REVIEW", "requirement-run-1"), ("SPECIALIST_REVIEW", "specialist-run-1")):
                input_path = f"evidence/{role.casefold()}-input.md"
                output_path = f"evidence/{role.casefold()}-output.md"
                role_paths = {
                    "REQUIREMENT_REVIEW": ["requirements/baseline.md", "flows/system.html", "features/list.md"],
                    "SPECIALIST_REVIEW": ["requirements/baseline.md", "flows/system.html", "tests/unit.md", "src/module.py"],
                }
                self.fixture._write_agent_input(role, run_id, input_path, role_paths[role])
                self.fixture._write_agent_output(role, run_id, output_path)
                evidence["gates"].append(self.fixture._agent_gate(role, run_id, input_path, output_path))
        for gate in evidence["gates"]:
            input_path = self.fixture.root / gate["input_manifest"]
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            payload["artifacts"] = [
                item for item in payload["artifacts"] if item["path"] != "ui/prototype.html"
            ]
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            gate["input_sha256"] = hashlib.sha256(input_path.read_bytes()).hexdigest()
            output_path = self.fixture.root / gate["output_evidence"]
            output = json.loads(output_path.read_text(encoding="utf-8"))
            output["input_sha256"] = gate["input_sha256"]
            output_path.write_text(json.dumps(output), encoding="utf-8")
            gate["output_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        self.fixture.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        commands = json.loads(self.fixture.commands.read_text(encoding="utf-8"))
        commands["frontend_applicable"] = False
        commands.update({
            "frontend_preview_url": "N/A: no frontend",
            "frontend_preview_root": "N/A: no frontend",
            "frontend_entry_artifact": "N/A: no frontend",
        })
        for command in commands["commands"]:
            if command["id"] in {"frontend_evidence", "frontend_e2e"}:
                command["applicability"] = "N/A: no frontend"
        self.fixture.commands.write_text(json.dumps(commands), encoding="utf-8")
        self._refresh_context_dependent_records(f"{risk}; {reason}; no expansion")

    def _refresh_context_dependent_records(self, risk_reason: str) -> None:
        self.fixture.context.write_text(
            self.fixture._context_manifest(risk_reason=risk_reason), encoding="utf-8",
        )
        context = self.fixture.context.read_text(encoding="utf-8")
        command_fingerprint = re.search(
            r"^- Command manifest fingerprint: (.+)$", context, re.MULTILINE,
        ).group(1)
        self.fixture.module_run.write_text(
            self.fixture._module_run_record(risk_reason=risk_reason), encoding="utf-8",
        )
        transcript = self.fixture.root / "evidence/automated-review.json"
        payload = json.loads(transcript.read_text(encoding="utf-8"))
        payload["command_manifest_fingerprint"] = command_fingerprint
        transcript.write_text(json.dumps(payload), encoding="utf-8")
        review = self.fixture.review.read_text(encoding="utf-8")
        review = re.sub(
            r"Command manifest fingerprint: [0-9a-f]{64}",
            f"Command manifest fingerprint: {command_fingerprint}", review,
        )
        review = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {hashlib.sha256(transcript.read_bytes()).hexdigest()}", review,
        )
        self.fixture.review.write_text(review, encoding="utf-8")

    def test_standard_ui_workflow(self) -> None:
        self.assertEqual(set(), self._codes())

    def test_small_non_ui_workflow(self) -> None:
        self._make_non_ui(risk="small", reason="internal refactor", surfaces="internal")
        self.assertEqual(set(), self._codes())

    def test_high_risk_auth_workflow(self) -> None:
        self._make_non_ui(risk="high-risk", reason="authentication boundary", surfaces="auth,security")
        self.assertEqual(set(), self._codes())

    def test_high_risk_cross_module_async_workflow(self) -> None:
        self._make_non_ui(risk="high-risk", reason="async cross-module flow", surfaces="async,cross-module")
        self.assertEqual(set(), self._codes())

    def test_authorized_password_uri_workflow(self) -> None:
        agents = self.fixture.agents.read_text(encoding="utf-8") + """

## Password Authorization

- Scope: project test service only
- Purpose: connect to the approved test service
- Update method: replace after credential rotation
- Access boundary: project maintainers only
- Authorized endpoints: https://example.test/service
- Endpoint: https://user:pass@example.test/service
"""
        self.fixture.agents.write_text(agents, encoding="utf-8")
        self._refresh_context_dependent_records("standard; user-visible interaction; no expansion")
        self.assertEqual(set(), self._codes(allow_passwords=True))


if __name__ == "__main__":
    unittest.main()
