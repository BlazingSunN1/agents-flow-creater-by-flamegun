from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import codex_native_writer_identity as subject


RUN = "01a09c1f-a13f-70c2-83e8-c887561fa55f"
TURN = "01a09c1f-a1a0-7192-96dd-3ddfed847e39"
AGENT = "sol-writer"
AGENT_PATH = "/root/sol_implementation"


class CodexNativeWriterIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "evidence").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _source(self, *, provider: str = "openai", model: str = "gpt-5.6-sol",
                effort: str = "medium", run: str = RUN, turn: str = TURN) -> bytes:
        records = [
            {"type": "session_meta", "payload": {
                "id": run, "session_id": "parent-thread", "model_provider": provider,
                "agent_path": AGENT_PATH,
                "source": {"subagent": {"thread_spawn": {"agent_path": AGENT_PATH}}},
            }},
            {"type": "turn_context", "payload": {
                "turn_id": turn, "model": model, "effort": effort,
            }},
        ]
        return ("\n".join(json.dumps(item, separators=(",", ":")) for item in records) + "\n").encode()

    def _identity(self, source: bytes, *, schema_version: object = 1) -> dict[str, object]:
        source_path = self.root / "evidence" / "rollout.jsonl"
        source_path.write_bytes(source)
        evidence = {
            "schema_version": schema_version,
            "evidence_kind": subject.EVIDENCE_KIND,
            "provider": subject.SUPPORTED_PROVIDER,
            "raw_model_provider": subject.SUPPORTED_RAW_PROVIDER,
            "requested_model": subject.SUPPORTED_MODEL,
            "recorded_model": subject.SUPPORTED_MODEL,
            "requested_reasoning_effort": subject.SUPPORTED_EFFORT,
            "recorded_reasoning_effort": subject.SUPPORTED_EFFORT,
            "runtime_kind": subject.SUPPORTED_RUNTIME,
            "writer_agent_id": AGENT,
            "writer_run_id": RUN,
            "invocation_id": TURN,
            "source_agent_path": AGENT_PATH,
            "source_path": "evidence/rollout.jsonl",
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "source_capture": "immutable-local-snapshot",
        }
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        (self.root / "evidence" / "invocation.json").write_bytes(payload)
        return {
            "provider": subject.SUPPORTED_PROVIDER,
            "requested_model": subject.SUPPORTED_MODEL,
            "recorded_model": subject.SUPPORTED_MODEL,
            "requested_reasoning_effort": subject.SUPPORTED_EFFORT,
            "recorded_reasoning_effort": subject.SUPPORTED_EFFORT,
            "runtime_kind": subject.SUPPORTED_RUNTIME,
            "writer_agent_id": AGENT,
            "writer_run_id": RUN,
            "evidence_path": "evidence/invocation.json",
            "evidence_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def test_accepts_real_subagent_rollout_shape(self) -> None:
        resolved = subject.validate_writer_identity(self.root, self._identity(self._source()), AGENT, RUN)
        self.assertEqual("openai", resolved["raw_model_provider"])
        self.assertEqual(AGENT_PATH, resolved["source_agent_path"])

    def test_accepts_real_auxiliary_records_and_consistent_turn_replay(self) -> None:
        records = [json.loads(line) for line in self._source().decode().splitlines()]
        records.extend([
            {"type": "inter_agent_communication_metadata", "payload": {"sender": "/root"}},
            {"type": "compacted", "payload": {"replacement": "bounded-summary"}},
            {"type": "turn_context", "payload": {
                "turn_id": TURN, "model": "gpt-5.6-sol", "effort": "medium",
            }},
        ])
        source = ("\n".join(json.dumps(item) for item in records) + "\n").encode()
        resolved = subject.validate_writer_identity(self.root, self._identity(source), AGENT, RUN)
        self.assertEqual(TURN, resolved["invocation_id"])

    def test_rejects_conflicting_replay_of_same_turn(self) -> None:
        records = [json.loads(line) for line in self._source().decode().splitlines()]
        records.append({"type": "turn_context", "payload": {
            "turn_id": TURN, "model": "gpt-5.6-sol", "effort": "high",
        }})
        source = ("\n".join(json.dumps(item) for item in records) + "\n").encode()
        with self.assertRaisesRegex(RuntimeError, "writer-source-turn-mismatch"):
            subject.validate_writer_identity(self.root, self._identity(source), AGENT, RUN)

    def test_rejects_wrong_raw_provider(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
            subject.validate_writer_identity(self.root, self._identity(self._source(provider="ollama_local")), AGENT, RUN)

    def test_rejects_non_integer_evidence_schema_version(self) -> None:
        source = self._source()
        for schema_version in (True, False, "1", 1.0):
            with self.subTest(schema_version=schema_version):
                with self.assertRaisesRegex(RuntimeError, "invalid-writer-evidence"):
                    subject.validate_writer_identity(
                        self.root, self._identity(source, schema_version=schema_version), AGENT, RUN,
                    )

    def test_rejects_wrong_target_model_or_effort(self) -> None:
        for source in (self._source(model="gpt-6-astra"), self._source(effort="high")):
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "writer-source-turn-mismatch"):
                    subject.validate_writer_identity(self.root, self._identity(source), AGENT, RUN)

    def test_rejects_wrong_session_or_target_turn(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
            subject.validate_writer_identity(self.root, self._identity(self._source(run="other-run")), AGENT, RUN)
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-source"):
            subject.validate_writer_identity(self.root, self._identity(self._source(turn="other-turn")), AGENT, RUN)

    def test_rejects_source_agent_path_mismatch(self) -> None:
        identity = self._identity(self._source())
        path = self.root / "evidence" / "invocation.json"
        evidence = json.loads(path.read_text())
        evidence["source_agent_path"] = "/root/other"
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        path.write_bytes(payload)
        identity["evidence_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
            subject.validate_writer_identity(self.root, identity, AGENT, RUN)

    def test_rejects_malformed_nested_spawn_source_without_crashing(self) -> None:
        for malformed in ({"subagent": "bad"}, {"subagent": {"thread_spawn": "bad"}}):
            records = [
                {"type": "session_meta", "payload": {
                    "id": RUN, "model_provider": "openai", "agent_path": AGENT_PATH,
                    "source": malformed,
                }},
                {"type": "turn_context", "payload": {
                    "turn_id": TURN, "model": "gpt-5.6-sol", "effort": "medium",
                }},
            ]
            source = ("\n".join(json.dumps(item) for item in records) + "\n").encode()
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(RuntimeError, "writer-source-session-mismatch"):
                    subject.validate_writer_identity(self.root, self._identity(source), AGENT, RUN)

    def _v2_identity(self, source: bytes, parent: str = "parent-thread") -> dict[str, object]:
        identity = self._identity(source)
        path = self.root / "evidence" / "invocation.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        evidence.update({
            "schema_version": 2,
            "source_agent_path": None,
            "source_parent_thread_id": parent,
        })
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        path.write_bytes(payload)
        identity["evidence_sha256"] = hashlib.sha256(payload).hexdigest()
        return identity

    def _v2_source(self, *, parent: str = "parent-thread", path: object = None,
                   run: str = RUN, model: str = "gpt-5.6-sol",
                   effort: str = "medium") -> bytes:
        records = [
            {"type": "session_meta", "payload": {
                "id": run, "model_provider": "openai", "agent_path": path,
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent}}},
            }},
            {"type": "turn_context", "payload": {
                "turn_id": TURN, "model": model, "effort": effort,
            }},
        ]
        return ("\n".join(json.dumps(item) for item in records) + "\n").encode()

    def test_accepts_real_null_agent_path_with_parent_and_target_turn(self) -> None:
        source = self._v2_source()
        resolved = subject.validate_writer_identity(
            self.root, self._v2_identity(source), AGENT, RUN,
        )
        self.assertIsNone(resolved["source_agent_path"])
        self.assertEqual("parent-thread", resolved["source_parent_thread_id"])

    def test_v2_rejects_parent_session_model_effort_and_path_conflicts(self) -> None:
        cases = (
            (self._v2_source(parent="other-parent"), "parent-thread"),
            (self._v2_source(run="other-run"), "parent-thread"),
            (self._v2_source(model="gpt-6-astra"), "parent-thread"),
            (self._v2_source(effort="high"), "parent-thread"),
            (self._v2_source(path="/root/fake"), "parent-thread"),
        )
        for source, parent in cases:
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "writer-source-(session|turn)-mismatch"):
                    subject.validate_writer_identity(
                        self.root, self._v2_identity(source, parent), AGENT, RUN,
                    )


if __name__ == "__main__":
    unittest.main()
