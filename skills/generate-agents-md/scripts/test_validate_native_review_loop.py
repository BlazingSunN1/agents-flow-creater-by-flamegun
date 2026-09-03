from __future__ import annotations

import hashlib
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256
from validate_native_review_loop import _test_only_validate_native_review_loop, validate_native_review_loop

SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets/native-review-loop-evidence.template.json"

class NativeReviewLoopValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "evidence").mkdir()
        self.path = self.root / "native-review-loop.json"
        self.data = self._valid_data()
        self._write_bundle()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, relative: str, value: object) -> str:
        path = self.root / relative
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _receipt(self, *, role: str, agent_id: str, run_id: str, kind: str,
                 candidate_sha256: str | None = None, input_sha256: str | None = None,
                 output_sha256: str | None = None, verdict: str | None = None,
                 maintainer_title: str | None = None) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1, "receipt_kind": kind,
            "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol", "agent_id": agent_id,
            "requested_reasoning_effort": "high" if role in {"module-maintainer", "implementation"} else "xhigh",
            "recorded_reasoning_effort": "high" if role in {"module-maintainer", "implementation"} else "xhigh",
            "run_id": run_id, "role": role, "module": "M02",
            "maintainer_title": maintainer_title or role,
        }
        if kind == "codex-native-output-result":
            value.update({
                "input_sha256": input_sha256, "output_sha256": output_sha256,
                "scope_sha256": "a" * 64, "candidate_version": 1,
                "candidate_sha256": candidate_sha256, "verdict": verdict,
            })
        return value

    def _child(self, role: str, agent_id: str, run_id: str, candidate_sha: str) -> dict[str, object]:
        slug = role.replace("_", "-")
        input_path = f"evidence/{slug}-input.json"
        output_path = "evidence/candidate-v1.md" if role == "solution-author" else f"evidence/{slug}-output.json"
        input_value = {
            "schema_version": 1, "role": role, "agent_id": agent_id, "run_id": run_id,
                "scope_sha256": "a" * 64, "candidate_version": 1,
            "candidate_sha256": candidate_sha if role == "black-box-reviewer" else "N/A",
            "includes_full_chat": False, "includes_other_agent_reasoning": False,
            "includes_implementation_self_report": False,
        }
        input_sha = self._write_json(input_path, input_value)
        if role == "black-box-reviewer":
            output_value = {
                "schema_version": 1, "role": role, "agent_id": agent_id, "run_id": run_id,
                "scope_sha256": "a" * 64, "candidate_version": 1,
                "candidate_sha256": candidate_sha, "verdict": "pass",
                "findings": [], "uncertainties": [], "blockers": [], "disagreements": [],
                "black_box_cases": [
                    {"category": name, "case": f"observable {name}"}
                    for name in ("success", "rejection", "failure", "retry", "recovery", "permission", "boundary")
                ],
            }
            output_sha = self._write_json(output_path, output_value)
        else:
            output_sha = candidate_sha
        spawn_path = f"evidence/{slug}-spawn.json"
        spawn_sha = self._write_json(spawn_path, self._receipt(
            role=role, agent_id=agent_id, run_id=run_id, kind="codex-native-spawn-result",
        ))
        output_receipt_path = f"evidence/{slug}-receipt.json"
        output_receipt_sha = self._write_json(output_receipt_path, self._receipt(
            role=role, agent_id=agent_id, run_id=run_id, kind="codex-native-output-result",
            candidate_sha256=candidate_sha, input_sha256=input_sha,
            output_sha256=output_sha, verdict="produced" if role == "solution-author" else "pass",
        ))
        return {
            "provider": "codex-native-agent", "agent_model": "gpt-5.6-sol",
            "agent_reasoning_effort": "xhigh",
            "agent_id": agent_id, "run_id": run_id,
            "spawn_receipt": spawn_path, "spawn_receipt_sha256": spawn_sha,
            "output_receipt": output_receipt_path, "output_receipt_sha256": output_receipt_sha,
            "input_manifest": input_path, "input_sha256": input_sha,
            "output_evidence": output_path, "output_sha256": output_sha,
            "may_modify_code": False, "may_modify_shared_records": False,
            "received_full_chat": False, "received_other_agent_reasoning": False,
            "accepted_implementation_self_report": False,
            "verdict": "produced" if role == "solution-author" else "pass",
        }

    def _valid_data(self) -> dict[str, object]:
        candidate = self.root / "evidence/candidate-v1.md"
        candidate.write_text("complete candidate v1", encoding="utf-8")
        candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        adjudicator_path = "evidence/adjudicator-spawn.json"
        adjudicator_sha = self._write_json(adjudicator_path, self._receipt(
            role="coordinator-adjudicator", agent_id="adjudicator-agent", run_id="adjudicator-run",
            kind="codex-native-spawn-result", maintainer_title="coordinator-adjudicator",
        ))
        writer_path = "evidence/writer-spawn.json"
        writer_sha = self._write_json(writer_path, self._receipt(
            role="module-maintainer", agent_id="writer-agent", run_id="writer-run",
            kind="codex-native-spawn-result", maintainer_title="M02 Maintainer",
        ))
        data = {
            "schema_version": 1, "stage": "design-review",
            "authority_matrix_sha256": AUTHORITY_MATRIX_SHA256,
            "workflow_id": "native-review-M02-001",
            "module": "M02", "maintainer_title": "M02 Maintainer",
            "adjudicator_agent_id": "adjudicator-agent", "adjudicator_run_id": "adjudicator-run",
            "adjudicator_spawn_receipt": adjudicator_path,
            "adjudicator_spawn_receipt_sha256": adjudicator_sha,
            "adjudicator_may_modify_code": False,
            "adjudicator_may_modify_shared_records": False,
            "adjudicator_holds_writer_lease": False,
            "writer_agent_id": "writer-agent", "writer_run_id": "writer-run",
            "writer_role": "module-maintainer", "writer_spawn_receipt": writer_path,
            "writer_spawn_receipt_sha256": writer_sha,
            "scope_version": "scope-v1", "scope_sha256": "a" * 64,
            "baseline_version": "baseline-v1", "baseline_sha256": "b" * 64,
            "code_version": "code-v1", "build_id": "build-v1",
            "max_candidate_versions": 6,
            "candidates": [{
                "version": 1, "candidate_artifact": "evidence/candidate-v1.md",
                "candidate_sha256": candidate_sha,
                "solution_author": self._child("solution-author", "author-agent", "author-run", candidate_sha),
                "black_box_reviewer": self._child("black-box-reviewer", "review-agent", "review-run", candidate_sha),
                "coordinator_adjudication": {
                    "agent_id": "adjudicator-agent", "run_id": "adjudicator-run",
                    "candidate_version": 1, "candidate_sha256": candidate_sha,
                    "verdict": "pass", "findings": [], "uncertainties": [],
                    "blockers": [], "disagreements": [],
                },
            }],
            "final_candidate_version": 1, "final_candidate_sha256": candidate_sha,
            "outcome": "reviewed", "runtime_multi_agent_evidence": "N/A",
            "runtime_multi_agent_evidence_sha256": "N/A",
        }
        checkpoint = {
            "schema_version": 1, "workflow_id": data["workflow_id"],
            "run_id": data["adjudicator_run_id"], "round": 1,
            "scope_sha256": data["scope_sha256"], "candidate_sha256": candidate_sha,
            "code_version": data["code_version"], "build_id": data["build_id"],
            "input_sha256": data["candidates"][0]["solution_author"]["input_sha256"],
            "output_sha256": candidate_sha,
            "completed_gates": ["solution-author", "black-box-reviewer", "coordinator-adjudication"],
            "pending_defects": [], "next_action": "route independent runtime gates",
            "created_at": "2026-09-01T10:00:00Z",
            "previous_checkpoint_locator": None, "previous_checkpoint_sha256": None,
            "recovery_required": False, "recovery_receipt": None,
            "recovery_receipt_sha256": None,
        }
        locator = "evidence/native-review-checkpoint-v1.json"
        data["checkpoint_chain"] = [{
            "current_checkpoint_locator": locator,
            "current_checkpoint_sha256": self._write_json(locator, checkpoint),
            "checkpoint": checkpoint,
        }]
        return data

    def _write_bundle(self) -> None:
        self.path.write_text(json.dumps(self.data), encoding="utf-8")

    def _enable_recovery(self) -> None:
        wrapper = self.data["checkpoint_chain"][0]
        checkpoint = wrapper["checkpoint"]
        receipt_path = "evidence/native-review-recovery-v1.json"
        receipt = {
            "schema_version": 1, "receipt_kind": "codex-native-recovery-result",
            "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol",
            "requested_reasoning_effort": "xhigh", "recorded_reasoning_effort": "xhigh",
            "agent_id": self.data["adjudicator_agent_id"], "run_id": self.data["adjudicator_run_id"],
            "role": "coordinator-adjudicator", "module": self.data["module"],
            "maintainer_title": "coordinator-adjudicator",
            "workflow_id": self.data["workflow_id"], "round": checkpoint["round"],
            "previous_checkpoint_locator": checkpoint["previous_checkpoint_locator"],
            "previous_checkpoint_sha256": checkpoint["previous_checkpoint_sha256"],
            "scope_sha256": checkpoint["scope_sha256"],
            "candidate_sha256": checkpoint["candidate_sha256"],
            "code_version": checkpoint["code_version"], "build_id": checkpoint["build_id"],
            "verdict": "resumed",
        }
        checkpoint["recovery_required"] = True
        checkpoint["recovery_receipt"] = receipt_path
        checkpoint["recovery_receipt_sha256"] = self._write_json(receipt_path, receipt)
        wrapper["current_checkpoint_sha256"] = self._write_json(
            wrapper["current_checkpoint_locator"], checkpoint,
        )
        self._write_bundle()

    def codes(self) -> set[str]:
        return {item.code for item in _test_only_validate_native_review_loop(
            self.path, project_root=self.root, _test_only_host_attestation_verifier=lambda *_: True,
        ) if item.severity == "error"}

    def test_valid_design_review_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_checkpoint_chain_is_mandatory(self) -> None:
        self.data.pop("checkpoint_chain")
        self._write_bundle()
        self.assertIn("missing-native-loop-checkpoint", self.codes())

    def test_checkpoint_candidate_or_previous_link_drift_fails_closed(self) -> None:
        checkpoint = self.data["checkpoint_chain"][0]["checkpoint"]
        checkpoint["candidate_sha256"] = "0" * 64
        self._write_bundle()
        self.assertIn("stale-native-loop-checkpoint", self.codes())

    def test_recovery_requires_host_verified_receipt(self) -> None:
        checkpoint = self.data["checkpoint_chain"][0]["checkpoint"]
        checkpoint["recovery_required"] = True
        self._write_bundle()
        self.assertIn("missing-native-loop-recovery-receipt", self.codes())

    def test_recovery_receipt_is_chain_bound_and_host_verified(self) -> None:
        self._enable_recovery()
        self.assertEqual(set(), self.codes())
        public_codes = {item.code for item in validate_native_review_loop(
            self.path, project_root=self.root,
        )}
        self.assertNotIn("native-loop-recovery-receipt-not-validated", public_codes)
        receipt = self.root / self.data["checkpoint_chain"][0]["checkpoint"]["recovery_receipt"]
        value = json.loads(receipt.read_text(encoding="utf-8"))
        value["candidate_sha256"] = "0" * 64
        receipt.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        checkpoint = self.data["checkpoint_chain"][0]["checkpoint"]
        checkpoint["recovery_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        wrapper = self.data["checkpoint_chain"][0]
        wrapper["current_checkpoint_sha256"] = self._write_json(wrapper["current_checkpoint_locator"], checkpoint)
        self._write_bundle()
        self.assertIn("invalid-native-loop-recovery-receipt", self.codes())

    def test_public_template_is_closed_and_rejects_nested_bypass(self) -> None:
        self.assertEqual([], validate_native_review_loop(
            PUBLIC_TEMPLATE, project_root=self.root, template=True,
        ))
        value = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        value["candidates"][0]["black_box_reviewer"]["may_modify_code"] = True
        self.path.write_text(json.dumps(value), encoding="utf-8")
        codes = {item.code for item in validate_native_review_loop(
            self.path, project_root=self.root, template=True,
        )}
        self.assertIn("unsafe-native-loop-boundary", codes)
        value = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        value["checkpoint_chain"][0]["checkpoint"]["untrusted_resume"] = True
        self.path.write_text(json.dumps(value), encoding="utf-8")
        codes = {item.code for item in validate_native_review_loop(
            self.path, project_root=self.root, template=True,
        )}
        self.assertIn("invalid-native-loop-checkpoint-fields", codes)

    def test_adjudicator_cannot_reuse_child_agent_or_run(self) -> None:
        self.data["candidates"][0]["black_box_reviewer"]["agent_id"] = "adjudicator-agent"
        self._write_bundle()
        self.assertIn("reused-native-loop-identity", self.codes())

    def test_adjudicator_and_writer_must_use_distinct_identity_and_run(self) -> None:
        for field, value in (
            ("writer_agent_id", self.data["adjudicator_agent_id"]),
            ("writer_run_id", self.data["adjudicator_run_id"]),
        ):
            with self.subTest(field=field):
                original = self.data[field]
                self.data[field] = value
                self._write_bundle()
                self.assertIn("reused-native-loop-writer-identity", self.codes())
                self.data[field] = original

    def test_adjudicator_is_read_only_and_cannot_use_writer_role(self) -> None:
        self.data["adjudicator_holds_writer_lease"] = True
        self._write_bundle()
        self.assertIn("unsafe-native-loop-adjudicator-boundary", self.codes())

    def test_reviewer_must_bind_same_candidate_hash(self) -> None:
        self.data["candidates"][0]["black_box_reviewer"]["output_sha256"] = "0" * 64
        self._write_bundle()
        self.assertIn("stale-agent-artifact", self.codes())

    def test_seventh_candidate_is_rejected(self) -> None:
        self.data["candidates"] = self.data["candidates"] * 7
        self._write_bundle()
        self.assertIn("too-many-candidate-versions", self.codes())

    def test_project_receipts_allow_local_coordination_without_claiming_host_trust(self) -> None:
        issues = validate_native_review_loop(self.path, project_root=self.root)
        codes = {item.code for item in issues}
        self.assertNotIn("native-loop-adjudicator-receipt-not-validated", codes)
        self.assertNotIn("native-loop-writer-receipt-not-validated", codes)
        self.data["candidates"][0]["black_box_reviewer"]["agent_reasoning_effort"] = "high"
        self._write_bundle()
        self.assertIn("invalid-native-loop-effort", self.codes())

    def test_public_api_cannot_inject_host_verifier(self) -> None:
        self.assertNotIn("host_attestation_verifier", inspect.signature(validate_native_review_loop).parameters)
        with self.assertRaises(TypeError):
            validate_native_review_loop(
                self.path, project_root=self.root, host_attestation_verifier=lambda *_: True,
            )

    def test_design_review_cannot_claim_runtime_pass(self) -> None:
        self.data["outcome"] = "pass"
        self._write_bundle()
        self.assertIn("invalid-native-loop-outcome", self.codes())

    def test_pass_requires_empty_review_and_adjudication_open_items(self) -> None:
        adjudication = self.data["candidates"][0]["coordinator_adjudication"]
        adjudication["uncertainties"] = ["unknown"]
        self._write_bundle()
        self.assertIn("open-native-loop-items", self.codes())
        adjudication["uncertainties"] = []
        adjudication["agent_id"] = self.data["writer_agent_id"]
        self._write_bundle()
        self.assertIn("stale-coordinator-adjudication", self.codes())


if __name__ == "__main__":
    unittest.main()
