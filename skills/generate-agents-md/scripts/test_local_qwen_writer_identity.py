from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_qwen_writer_identity as identity_module
from test_update_project_record import (
    TURN2_UUID,
    TURN_UUID,
    qwen_evidence_bytes,
    qwen_writer_identity,
    synthetic_rollout_bytes,
)

RUN_ID = "run-identity-test-1"


class DirectWriterIdentitySourceTests(unittest.TestCase):
    """Direct source-binding regressions for validate_writer_identity.

    All rollout bytes here are SYNTHETIC fixtures mirroring the real Codex
    rollout shape; they are never real runtime evidence.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_evidence_tree(self, *, source: bytes, agent_id: str,
                             run_id: str, model: str = "qwen3.8:27b-bf16",
                             effort: str = "none",
                             invocation_id: str = TURN_UUID) -> dict:
        (self.root / "docs/governance").mkdir(parents=True, exist_ok=True)
        source_file = self.root / "docs/governance/qwen-synthetic-rollout.jsonl"
        source_file.write_bytes(source)
        evidence = qwen_evidence_bytes(agent_id, run_id, model=model, source=source,
                                       invocation_id=invocation_id)
        if effort != "none":
            value = json.loads(evidence)
            value.update({
                "requested_reasoning_effort": effort,
                "reported_reasoning_effort": effort,
            })
            evidence = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        evidence_file = self.root / "docs/governance/qwen-invocation-evidence.json"
        evidence_file.write_bytes(evidence)
        identity = qwen_writer_identity(agent_id, run_id, evidence=evidence, model=model)
        if effort != "none":
            identity.update({
                "requested_reasoning_effort": effort,
                "reported_reasoning_effort": effort,
            })
        return identity

    def test_two_valid_turns_with_target_bound_pass(self) -> None:
        # A resumed session contains the target turn plus one other unique
        # turn; the target must validate and the extra turn must be tolerated.
        lines = synthetic_rollout_bytes(session_id=RUN_ID).decode("utf-8").splitlines()
        turn1 = json.loads(lines[1])
        turn2 = dict(turn1)
        turn2["payload"] = dict(turn1["payload"], turn_id=TURN2_UUID,
                                root_turn_id=TURN2_UUID)
        turn2["ordinal"] = 2
        crafted = "\n".join([
            lines[0],
            json.dumps(turn1, sort_keys=True),
            json.dumps(turn2, sort_keys=True),
            lines[2],
        ]) + "\n"
        source = crafted.encode("utf-8")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-identity", run_id=RUN_ID,
            invocation_id=TURN2_UUID)
        result = identity_module.validate_writer_identity(
            self.root, identity, "agent-identity", RUN_ID)
        self.assertEqual("agent-identity", result["writer_agent_id"])
        self.assertEqual(RUN_ID, result["writer_run_id"])
        self.assertEqual(TURN2_UUID, result["invocation_id"])

    def test_different_identities_pass_independently(self) -> None:
        # Two different writers with their own consistent evidence/source
        # bindings must each validate (no cross-identity contamination).
        for run in ("run-a-1", "run-b-1"):
            source = synthetic_rollout_bytes(session_id=run)
            identity = self._write_evidence_tree(
                source=source, agent_id=f"agent-{run[:8]}", run_id=run)
            result = identity_module.validate_writer_identity(
                self.root, identity, f"agent-{run[:8]}", run)
            self.assertEqual(run, result["writer_run_id"])

    def test_target_turn_absent_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID, turn_id=TURN2_UUID)
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-source"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_identical_target_turn_replay_is_accepted(self) -> None:
        lines = synthetic_rollout_bytes(session_id=RUN_ID).decode("utf-8").splitlines()
        duplicated = "\n".join([lines[0], lines[1], lines[1]]) + "\n"
        source = duplicated.encode("utf-8")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        result = identity_module.validate_writer_identity(
            self.root, identity, "agent-x", RUN_ID)
        self.assertEqual(TURN_UUID, result["invocation_id"])

    def test_conflicting_target_turn_replay_is_rejected(self) -> None:
        lines = synthetic_rollout_bytes(session_id=RUN_ID).decode("utf-8").splitlines()
        conflicting = json.loads(lines[1])
        conflicting["payload"]["effort"] = "xhigh"
        source = ("\n".join([lines[0], lines[1], json.dumps(conflicting)]) + "\n").encode()
        identity = self._write_evidence_tree(source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "writer-source-turn-mismatch"):
            identity_module.validate_writer_identity(self.root, identity, "agent-x", RUN_ID)

    def test_compacted_and_inter_agent_metadata_are_accepted(self) -> None:
        lines = synthetic_rollout_bytes(session_id=RUN_ID).decode("utf-8").splitlines()
        records = [
            lines[0], lines[1],
            json.dumps({"type": "compacted", "payload": {"summary": "synthetic"}}),
            json.dumps({"type": "inter_agent_communication_metadata", "payload": {"synthetic": True}}),
        ]
        source = ("\n".join(records) + "\n").encode()
        identity = self._write_evidence_tree(source=source, agent_id="agent-x", run_id=RUN_ID)
        identity_module.validate_writer_identity(self.root, identity, "agent-x", RUN_ID)

    def test_unknown_rollout_record_is_rejected(self) -> None:
        lines = synthetic_rollout_bytes(session_id=RUN_ID).decode("utf-8").splitlines()
        source = ("\n".join([lines[0], lines[1], json.dumps({"type": "unknown", "payload": {}})]) + "\n").encode()
        identity = self._write_evidence_tree(source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-source"):
            identity_module.validate_writer_identity(self.root, identity, "agent-x", RUN_ID)

    def test_none_and_xhigh_efforts_bind_exact_target_turn(self) -> None:
        for effort in ("none", "xhigh"):
            with self.subTest(effort=effort):
                source = synthetic_rollout_bytes(session_id=RUN_ID, effort=effort)
                identity = self._write_evidence_tree(
                    source=source, agent_id="agent-x", run_id=RUN_ID, effort=effort,
                )
                result = identity_module.validate_writer_identity(
                    self.root, identity, "agent-x", RUN_ID,
                )
                self.assertEqual(effort, result["requested_reasoning_effort"])

    def test_bf16_and_q8_models_are_exact_closed_set(self) -> None:
        for model in ("qwen3.8:27b-bf16", "qwen3.8:27b-q8_0"):
            with self.subTest(model=model):
                source = synthetic_rollout_bytes(session_id=RUN_ID, model=model)
                identity = self._write_evidence_tree(
                    source=source, agent_id="agent-x", run_id=RUN_ID, model=model,
                )
                self.assertEqual(model, identity_module.validate_writer_identity(
                    self.root, identity, "agent-x", RUN_ID,
                )["reported_model"])
        source = synthetic_rollout_bytes(session_id=RUN_ID, model="qwen3.8:27b-q8_0")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID, model="qwen3.8:27b-q8_0",
        )
        identity["reported_model"] = "qwen3.8:27b-bf16"
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            identity_module.validate_writer_identity(self.root, identity, "agent-x", RUN_ID)

    def test_non_string_model_and_effort_fields_are_rejected_normally(self) -> None:
        fields = (
            "requested_model", "reported_model",
            "requested_reasoning_effort", "reported_reasoning_effort",
        )
        for field in fields:
            for malformed in ([], {}):
                with self.subTest(field=field, malformed=type(malformed).__name__):
                    source = synthetic_rollout_bytes(session_id=RUN_ID, effort="xhigh")
                    identity = self._write_evidence_tree(
                        source=source, agent_id="agent-x", run_id=RUN_ID, effort="xhigh",
                    )
                    identity[field] = malformed
                    with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
                        identity_module.validate_writer_identity(
                            self.root, identity, "agent-x", RUN_ID,
                        )

    def test_target_turn_wrong_model_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID, model="llama3:8b")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "writer-source-turn-mismatch"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_wrong_effort_on_target_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID, effort="high")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "writer-source-turn-mismatch"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_session_provider_mismatch_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID,
                                         provider="openai")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_duplicate_session_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID,
                                         duplicate_session=True)
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "duplicate-writer-source-session"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_duplicate_json_keys_in_source_line_are_rejected(self) -> None:
        line = json.loads(synthetic_rollout_bytes(session_id=RUN_ID)
                          .decode("utf-8").splitlines()[1])
        raw = '{"timestamp": "t", "timestamp": "t2", "ordinal": 1, ' \
              '"type": "turn_context", "payload": %s}' % json.dumps(
                  line["payload"], sort_keys=True)
        source = (synthetic_rollout_bytes(session_id=RUN_ID)
                  .decode("utf-8").splitlines()[0] + "\n" + raw + "\n")
        source = source.encode("utf-8")
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-source"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_source_hash_drift_is_rejected(self) -> None:
        source = synthetic_rollout_bytes(session_id=RUN_ID)
        identity = self._write_evidence_tree(
            source=source, agent_id="agent-x", run_id=RUN_ID)
        (self.root / "docs/governance/qwen-synthetic-rollout.jsonl").write_bytes(
            source + b"tampered")
        with self.assertRaisesRegex(RuntimeError, "writer-source-hash-mismatch"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)

    def test_invocation_misbound_to_different_run_is_rejected(self) -> None:
        # Evidence claims writer_run_id A but its source session is run B:
        # the invocation is bound to the wrong session.
        source = synthetic_rollout_bytes(session_id="run-other-1")
        evidence = qwen_evidence_bytes("agent-x", RUN_ID, source=source)
        (self.root / "docs/governance").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/governance/qwen-synthetic-rollout.jsonl").write_bytes(source)
        (self.root / "docs/governance/qwen-invocation-evidence.json").write_bytes(evidence)
        identity = qwen_writer_identity("agent-x", RUN_ID, evidence=evidence)
        with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
            identity_module.validate_writer_identity(
                self.root, identity, "agent-x", RUN_ID)


if __name__ == "__main__":
    unittest.main()
