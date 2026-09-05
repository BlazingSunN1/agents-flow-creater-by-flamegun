from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from implementation_agent_validation import validate_implementation_agent
from native_gate_agent_validation import validate_native_gate_agent
from system_actor_validation import validate_system_actors
from validate_multi_agent_evidence import _validate_structure
from delivery_authority_binding import AUTHORITY_SHA256


AUTHORITY_SHA = AUTHORITY_SHA256
BASELINE_SHA = "b" * 64
CANDIDATE_SHA = "c" * 64
OWNED_PATHS = ["src/module.py", "docs/flows/modules/module.html"]
class RoleSpecificReceiptV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "AGENTS.md").write_text(
            "authority_matrix_sha256: " + AUTHORITY_SHA + "\n\n"
            "## Module Agent Ownership and Dispatcher\n\n"
            "| Module | Stable scope | Owned project-relative paths | Long-term maintenance Agent title |\n"
            "| --- | --- | --- | --- |\n"
            "| module | scope | `src/module.py`, `docs/flows/modules/module.html` | Module Maintainer |\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, relative: str, value: dict[str, object]) -> tuple[str, str]:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return relative, hashlib.sha256(path.read_bytes()).hexdigest()

    def _common(self, *, read_only: bool, effort: str) -> dict[str, object]:
        return {
            "schema_version": 2,
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "requested_reasoning_effort": effort,
            "recorded_reasoning_effort": effort,
            "module": "module",
            "read_only": read_only,
            "authority_matrix_sha256": AUTHORITY_SHA,
            "owned_paths": OWNED_PATHS,
            "baseline_sha256": BASELINE_SHA,
            "code_version": "code-v2",
            "build_id": "build-v2",
            "candidate_sha256": CANDIDATE_SHA,
        }

    def _implementation_data(self) -> dict[str, object]:
        lease_path, lease_sha = self._write(
            "evidence/leases/module-run-1.json",
            {"lease_id": "lease-module-run-1", "lease_status": "active"},
        )
        lease = {
            "lease_id": "lease-module-run-1", "path": lease_path,
            "sha256": lease_sha,
        }
        receipt = {
            **self._common(read_only=False, effort="medium"),
            "receipt_kind": "codex-native-spawn-result",
            "agent_id": "implementation-agent",
            "run_id": "implementation-run",
            "role": "module-maintainer",
            "maintainer_title": "Module Maintainer",
            "active_write_lease": lease,
        }
        path, digest = self._write("evidence/implementation.json", receipt)
        return {
            "schema_version": 2,
            "implementation_agent_provider": "codex-native-agent",
            "implementation_agent_model": "gpt-6-astra",
            "implementation_agent_reasoning_effort": "medium",
            "implementation_agent_id": "implementation-agent",
            "implementation_run_id": "implementation-run",
            "implementation_agent_title": "Module Maintainer",
            "implementation_spawn_receipt": path,
            "implementation_spawn_receipt_sha256": digest,
            "authority_matrix_sha256": AUTHORITY_SHA,
            "owned_paths": OWNED_PATHS,
            "active_write_lease": lease,
            "baseline_sha256": BASELINE_SHA,
            "code_version": "code-v2",
            "build_id": "build-v2",
            "candidate_sha256": CANDIDATE_SHA,
        }

    def test_implementation_v2_binds_role_specific_closed_fields(self) -> None:
        data = self._implementation_data()
        self.assertEqual([], validate_implementation_agent(
            data, {"Modules": "module"}, self.root,
        ))
        for field in (
            "read_only", "authority_matrix_sha256", "owned_paths",
            "active_write_lease", "baseline_sha256", "code_version",
            "build_id", "candidate_sha256",
        ):
            with self.subTest(field=field):
                receipt = self.root / str(data["implementation_spawn_receipt"])
                payload = json.loads(receipt.read_text(encoding="utf-8"))
                payload.pop(field)
                receipt.write_text(json.dumps(payload), encoding="utf-8")
                data["implementation_spawn_receipt_sha256"] = hashlib.sha256(
                    receipt.read_bytes()
                ).hexdigest()
                codes = {item.code for item in validate_implementation_agent(
                    data, {"Modules": "module"}, self.root,
                )}
                self.assertIn("invalid-implementation-spawn-receipt", codes)
                data = self._implementation_data()

    def test_implementation_v2_rejects_invalid_outer_lease_and_paths(self) -> None:
        data = self._implementation_data()
        data["active_write_lease"] = {
            "lease_id": "lease-module-run-1", "path": "../lease.json",
            "sha256": "D" * 64,
        }
        codes = {item.code for item in validate_implementation_agent(
            data, {"Modules": "module"}, self.root,
        )}
        self.assertIn("invalid-implementation-runtime-binding", codes)

    def test_v2_receipt_locator_hash_is_strict_lowercase(self) -> None:
        data = self._implementation_data()
        data["implementation_spawn_receipt_sha256"] = str(
            data["implementation_spawn_receipt_sha256"]
        ).upper()
        codes = {item.code for item in validate_implementation_agent(
            data, {"Modules": "module"}, self.root,
        )}
        self.assertIn("invalid-implementation-receipt-sha256", codes)

    def test_outer_schema_v2_requires_exact_role_binding_sources(self) -> None:
        data = self._implementation_data()
        data.update({
            "stage": "implementation", "baseline_version": "baseline-v2",
            "single_writer_run_id": "implementation-run", "gates": [],
            "open_disagreements": [],
        })
        issues = []
        _validate_structure(data, issues)
        self.assertEqual([], issues)
        data.pop("authority_matrix_sha256")
        issues = []
        _validate_structure(data, issues)
        self.assertIn("invalid-agent-evidence-fields", {item.code for item in issues})

    def test_gate_v2_is_read_only_same_candidate_and_has_no_lease(self) -> None:
        evidence = self._implementation_data()
        spawn = {
            **self._common(read_only=True, effort="high"),
            "receipt_kind": "codex-native-spawn-result",
            "agent_id": "review-agent", "run_id": "review-run",
            "role": "change-review-gate",
            "maintainer_title": "CHANGE_REVIEW Gate Reviewer",
        }
        output = {
            **spawn, "receipt_kind": "codex-native-output-result",
            "input_sha256": "e" * 64, "output_sha256": "f" * 64,
            "baseline_version": "baseline-v2", "verdict": "pass",
        }
        spawn_path, spawn_sha = self._write("evidence/review-spawn.json", spawn)
        output_path, output_sha = self._write("evidence/review-output.json", output)
        gate = {
            "agent_id": "review-agent", "run_id": "review-run",
            "provider": "codex-native-agent", "agent_model": "gpt-6-astra",
            "agent_reasoning_effort": "high", "input_sha256": "e" * 64,
            "output_sha256": "f" * 64, "verdict": "pass",
            "spawn_receipt": spawn_path, "spawn_receipt_sha256": spawn_sha,
            "output_receipt": output_path, "output_receipt_sha256": output_sha,
        }
        evidence["baseline_version"] = "baseline-v2"
        self.assertEqual([], validate_native_gate_agent(
            gate, "CHANGE_REVIEW", "module", self.root,
            {"implementation-agent"}, {"implementation-run"}, None, evidence,
        ))
        output["candidate_sha256"] = "0" * 64
        output_path, output_sha = self._write("evidence/review-output.json", output)
        gate["output_receipt_sha256"] = output_sha
        codes = {item.code for item in validate_native_gate_agent(
            gate, "CHANGE_REVIEW", "module", self.root,
            {"implementation-agent"}, {"implementation-run"}, None, evidence,
        )}
        self.assertIn("invalid-gate-output-receipt", codes)

    def test_system_actor_v2_receipts_bind_read_only_authority_and_candidate(self) -> None:
        value: dict[str, object] = {
            "schema_version": 2,
            "runtime_receipt_schema_version": 2,
            "code_version": "code-v2", "build_id": "build-v2",
            "baseline_sha256": BASELINE_SHA, "candidate_sha256": CANDIDATE_SHA,
            "authority_binding": {"sha256": AUTHORITY_SHA},
            "dispatcher_agent_id": "dispatcher-agent",
            "dispatcher_run_id": "dispatcher-run",
            "dispatcher_title": "System Dispatcher",
            "dispatcher_provider": "codex-native-agent",
            "dispatcher_model": "gpt-6-astra",
            "dispatcher_owned_paths": [],
            "aggregation_writer_agent_id": "aggregation-agent",
            "aggregation_writer_run_id": "aggregation-run",
            "aggregation_writer_role": "SYSTEM_AGGREGATION",
            "aggregation_writer_title": "System Aggregation Writer",
            "aggregation_writer_provider": "codex-native-agent",
            "aggregation_writer_model": "gpt-6-astra",
            "aggregation_writer_owned_paths": ["docs/evidence/system-delivery/latest.json"],
        }
        dispatcher = {
            "schema_version": 2, "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent", "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra", "requested_reasoning_effort": "high",
            "recorded_reasoning_effort": "high", "agent_id": "dispatcher-agent",
            "run_id": "dispatcher-run", "role": "dispatcher", "module": "system",
            "maintainer_title": "System Dispatcher", "read_only": True,
            "authority_matrix_sha256": AUTHORITY_SHA, "owned_paths": [],
            "baseline_sha256": BASELINE_SHA, "code_version": "code-v2",
            "build_id": "build-v2", "candidate_sha256": CANDIDATE_SHA,
        }
        aggregation = {
            **dispatcher, "receipt_kind": "codex-native-output-result",
            "agent_id": "aggregation-agent", "run_id": "aggregation-run",
            "role": "system-aggregation", "maintainer_title": "System Aggregation Writer",
            "requested_reasoning_effort": "medium",
            "recorded_reasoning_effort": "medium",
            "read_only": False,
            "owned_paths": ["docs/evidence/system-delivery/latest.json"],
            "candidate_payload_sha256": "pending", "authority_binding": value["authority_binding"],
        }
        dispatcher_path, dispatcher_sha = self._write("evidence/dispatcher.json", dispatcher)
        aggregation_path, _ = self._write("evidence/aggregation.json", aggregation)
        value.update({
            "dispatcher_spawn_receipt": dispatcher_path,
            "dispatcher_spawn_receipt_sha256": dispatcher_sha,
            "aggregation_spawn_receipt": aggregation_path,
            "aggregation_spawn_receipt_sha256": "pending",
        })
        from system_actor_validation import system_candidate_payload_sha256
        aggregation["candidate_payload_sha256"] = system_candidate_payload_sha256(value)
        aggregation_path, aggregation_sha = self._write("evidence/aggregation.json", aggregation)
        value["aggregation_spawn_receipt_sha256"] = aggregation_sha
        self.assertEqual([], validate_system_actors(value, self.root, None))


if __name__ == "__main__":
    unittest.main()
