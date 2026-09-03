from __future__ import annotations

import json
import hashlib
import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_requirement_questions import (
    _test_only_validate_requirement_questions,
    validate_requirement_questions,
)


SHA = "a" * 64


class RequirementQuestionValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "questions.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "baseline_version": "req-v1",
            "baseline_sha256": SHA,
            "questions": [{
                "question_id": "Q-001",
                "impact_scope": ["REQ-001", "ACCEPTANCE_CASES"],
                "risk": "standard",
                "proposed_default": "Keep the existing API response shape.",
                "safe_fallback": "Use an additive feature flag that can be disabled.",
                "answer_status": "NOT_PROVIDED",
                "delivery_disposition": "NON_BLOCKING_P2",
                "assumption": "Existing clients require backward compatibility.",
                "owner": "product-owner",
                "review_due": "2026-09-03T10:00:00+08:00",
            }],
            "gate_reruns": [],
        }

    def codes(self, payload: dict[str, object]) -> set[str]:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return {item.code for item in validate_requirement_questions(self.path)}

    def write_artifact(self, name: str, value: dict[str, object]) -> tuple[str, str]:
        artifact = Path(self.temporary.name) / name
        raw = json.dumps(value, sort_keys=True).encode()
        artifact.write_bytes(raw)
        return name, hashlib.sha256(raw).hexdigest()

    def answered_payload(self) -> dict[str, object]:
        payload = self.payload()
        question = payload["questions"][0]
        payload["baseline_version"] = "req-v2"
        payload["baseline_sha256"] = "b" * 64
        question.update({
            "answer_status": "ANSWERED",
            "human_answer": "Keep the response backward compatible.",
            "pre_answer_baseline_version": "req-v1",
            "pre_answer_baseline_sha256": SHA,
        })
        answer_path, answer_sha = self.write_artifact("answer.json", {
            "schema_version": 1,
            "evidence_kind": "human-requirement-answer",
            "question_id": "Q-001",
            "human_answer": question["human_answer"],
            "pre_answer_baseline_version": "req-v1",
            "pre_answer_baseline_sha256": SHA,
            "post_answer_baseline_version": "req-v2",
            "post_answer_baseline_sha256": "b" * 64,
        })
        question["answer_evidence_locator"] = answer_path
        question["answer_evidence_sha256"] = answer_sha
        receipt_path, receipt_sha = self.write_artifact("rerun.json", {
            "schema_version": 1,
            "receipt_kind": "requirement-gate-rerun",
            "question_id": "Q-001",
            "baseline_version": "req-v2",
            "baseline_sha256": "b" * 64,
            "affected_scope": ["REQ-001", "ACCEPTANCE_CASES"],
            "status": "COMPLETED",
        })
        payload["gate_reruns"] = [{
            "question_id": "Q-001", "baseline_version": "req-v2",
            "baseline_sha256": "b" * 64,
            "affected_scope": ["REQ-001", "ACCEPTANCE_CASES"],
            "status": "COMPLETED", "receipt_locator": receipt_path,
            "receipt_sha256": receipt_sha,
        }]
        return payload

    def trusted_codes(self, payload: dict[str, object]) -> set[str]:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return {item.code for item in _test_only_validate_requirement_questions(
            self.path, project_root=Path(self.temporary.name),
            _test_only_host_attestation_verifier=lambda *_: True,
        )}

    def test_unanswered_reversible_question_continues_with_safe_default(self) -> None:
        self.assertEqual(set(), self.codes(self.payload()))

    def test_question_fields_are_closed_and_required(self) -> None:
        payload = self.payload()
        del payload["questions"][0]["safe_fallback"]
        self.assertIn("invalid-question-fields", self.codes(payload))
        payload = self.payload()
        payload["questions"][0]["human_answer"] = "must not impersonate ANSWERED"
        self.assertIn("invalid-question-fields", self.codes(payload))
        payload = self.payload()
        payload["questions"][0]["delivery_disposition"] = "BLOCKING"
        self.assertIn("invalid-question-delivery-disposition", self.codes(payload))

    def test_unanswered_question_requires_explicit_default_fallback_and_assumption(self) -> None:
        for field in ("proposed_default", "safe_fallback", "assumption"):
            with self.subTest(field=field):
                payload = self.payload()
                payload["questions"][0][field] = ""
                self.assertIn("invalid-question-safe-default", self.codes(payload))

    def test_all_unanswered_questions_remain_non_blocking_p2(self) -> None:
        for risk in ("legal", "security", "irreversible-destruction", "missing-required-permission"):
            with self.subTest(risk=risk):
                payload = self.payload()
                payload["questions"][0]["risk"] = risk
                self.assertEqual(set(), self.codes(payload))

    def test_answer_requires_current_baseline_and_affected_gate_rerun(self) -> None:
        payload = self.payload()
        payload["questions"][0]["answer_status"] = "ANSWERED"
        self.assertIn("answered-question-rerun-required", self.codes(payload))
        self.assertNotEqual(set(), self.codes(payload))

    def test_answered_requires_human_evidence_baseline_change_and_closed_receipt(self) -> None:
        payload = self.answered_payload()
        self.assertEqual(set(), self.trusted_codes(payload))
        for field in ("human_answer", "answer_evidence_locator", "answer_evidence_sha256",
                      "pre_answer_baseline_version", "pre_answer_baseline_sha256"):
            with self.subTest(field=field):
                broken = self.answered_payload()
                del broken["questions"][0][field]
                self.assertIn("invalid-question-fields", self.trusted_codes(broken))
        payload = self.answered_payload()
        payload["questions"][0]["pre_answer_baseline_version"] = "req-v2"
        payload["questions"][0]["pre_answer_baseline_sha256"] = "b" * 64
        self.assertIn("answered-question-baseline-not-updated", self.trusted_codes(payload))

    def test_answer_and_rerun_evidence_are_bound_and_allow_local_coordination(self) -> None:
        payload = self.answered_payload()
        payload["gate_reruns"][0]["baseline_version"] = "req-v1"
        payload["gate_reruns"][0]["baseline_sha256"] = SHA
        self.assertIn("answered-question-rerun-required", self.trusted_codes(payload))
        payload = self.answered_payload()
        payload["questions"][0]["answer_evidence_sha256"] = "c" * 64
        self.assertIn("invalid-answer-evidence", self.trusted_codes(payload))
        self.path.write_text(json.dumps(self.answered_payload()), encoding="utf-8")
        self.assertNotIn("question-rerun-receipt-not-validated", {
            item.code for item in validate_requirement_questions(self.path, project_root=Path(self.temporary.name))
        })
        self.assertNotIn("host_attestation_verifier", inspect.signature(validate_requirement_questions).parameters)

    def test_strict_verifier_rejection_blocks_answered_rerun(self) -> None:
        self.path.write_text(json.dumps(self.answered_payload()), encoding="utf-8")
        codes = {
            item.code for item in _test_only_validate_requirement_questions(
                self.path, project_root=Path(self.temporary.name),
                _test_only_host_attestation_verifier=lambda *_: False,
            )
        }
        self.assertIn("question-rerun-receipt-not-validated", codes)

    def test_cli_accepts_explicit_project_root_for_standard_nested_path(self) -> None:
        root = Path(self.temporary.name)
        nested = root / "docs" / "requirements" / "questions.json"
        nested.parent.mkdir(parents=True)
        nested.write_text(json.dumps(self.answered_payload()), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable, str(Path(__file__).parent / "validate_requirement_questions.py"),
                str(nested), "--project-root", str(root), "--json",
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
