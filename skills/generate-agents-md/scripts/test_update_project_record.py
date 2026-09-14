from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from update_project_record import MISSING_SHA, update_record
import update_project_record
from project_record_authorization import (
    authorize_project_record_write,
    require_codex_native_sol_writer_profile,
)
from test_validate_agents_md import project_root_fixture


SCRIPT = Path(__file__).resolve().parent / "update_project_record.py"


# ---------------------------------------------------------------------------
# SYNTHETIC test fixtures ONLY (explicit per scripts/AGENTS.md: synthetic data
# allowed in test_*/fixtures). They mirror the real Codex rollout shape
# (top-level: timestamp/ordinal/type/payload; session_meta payload has
# id+session_id+model_provider; turn_context payload has turn_id/model/effort
# with effort "none") but every uuid/hash/agent/run id below is synthetic and
# must never be presented as real runtime evidence.
SESSION_UUID = "11111111-aaaa-bbbb-cccc-000000000001"
SESSION2_UUID = "22222222-aaaa-bbbb-cccc-000000000002"
TURN_UUID = "33333333-aaaa-bbbb-cccc-000000000003"
TURN2_UUID = "44444444-aaaa-bbbb-cccc-000000000004"


def synthetic_session_line(session_id: str = SESSION_UUID, provider: str = "ollama_local") -> bytes:
    payload = {
        "base_instructions": "", "cli_version": "synthetic",
        "context_window": 0, "cwd": "/synthetic", "git": {},
        "history_mode": "synthetic", "id": session_id,
        "model_provider": provider, "originator": "synthetic",
        "session_id": session_id, "source": "synthetic",
        "thread_source": "user", "timestamp": "1970-01-01T00:00:00Z",
    }
    return (json.dumps({"timestamp": "1970-01-01T00:00:00Z", "ordinal": 0,
                        "type": "session_meta", "payload": payload},
                       sort_keys=True) + "\n").encode("utf-8")


def synthetic_turn_line(turn_id: str = TURN_UUID, session_id: str = SESSION_UUID,
                        model: str = "qwen3.8:27b-bf16") -> bytes:
    payload = {
        "approval_policy": "never", "approvals_reviewer": "synthetic",
        "collaboration_mode": "synthetic", "current_date": "1970-01-01",
        "cwd": "/synthetic", "effort": "none",
        "file_system_sandbox_policy": "synthetic", "model": model,
        "multi_agent_version": "v1", "permission_profile": "synthetic",
        "personality": "", "realtime_active": False,
        "root_turn_id": turn_id, "sandbox_policy": "synthetic",
        "summary": "", "timezone": "UTC", "turn_id": turn_id,
        "workspace_roots": ["/synthetic"],
    }
    return (json.dumps({"timestamp": "1970-01-01T00:00:01Z", "ordinal": 1,
                        "type": "turn_context", "payload": payload},
                       sort_keys=True) + "\n").encode("utf-8")


def synthetic_event_line(event_type: str = "token_count",
                         turn_id: str = TURN_UUID) -> bytes:
    payload = {"type": event_type, "info": "synthetic"}
    if event_type != "token_count":
        payload = {"type": event_type, "turn_id": turn_id,
                   "started_at": "1970-01-01T00:00:02Z"}
    return (json.dumps({"timestamp": "1970-01-01T00:00:02Z", "ordinal": 2,
                        "type": "event_msg", "payload": payload},
                       sort_keys=True) + "\n").encode("utf-8")


def synthetic_rollout_bytes(*, session_id: str = SESSION_UUID,
                            turn_id: str = TURN_UUID,
                            provider: str = "ollama_local",
                            model: str = "qwen3.8:27b-bf16",
                            effort: str = "none",
                            with_event_lines: bool = True,
                            duplicate_session: bool = False,
                            missing_fields: set[str] | None = None,
                            ) -> bytes:
    session_payload = {
        "base_instructions": "", "cli_version": "synthetic",
        "context_window": 0, "cwd": "/synthetic", "git": {},
        "history_mode": "synthetic", "id": session_id,
        "model_provider": provider, "originator": "synthetic",
        "session_id": session_id, "source": "synthetic",
        "thread_source": "user", "timestamp": "1970-01-01T00:00:00Z",
    }
    turn_payload = {
        "approval_policy": "never", "approvals_reviewer": "synthetic",
        "collaboration_mode": "synthetic", "current_date": "1970-01-01",
        "cwd": "/synthetic", "effort": effort,
        "file_system_sandbox_policy": "synthetic", "model": model,
        "multi_agent_version": "v1", "permission_profile": "synthetic",
        "personality": "", "realtime_active": False,
        "root_turn_id": turn_id, "sandbox_policy": "synthetic",
        "summary": "", "timezone": "UTC", "turn_id": turn_id,
        "workspace_roots": ["/synthetic"],
    }
    if missing_fields:
        for key in missing_fields:
            if key in session_payload:
                del session_payload[key]
            elif key in turn_payload:
                del turn_payload[key]
    lines = [
        json.dumps({"timestamp": "1970-01-01T00:00:00Z", "ordinal": 0,
                    "type": "session_meta", "payload": session_payload},
                   sort_keys=True),
        json.dumps({"timestamp": "1970-01-01T00:00:01Z", "ordinal": 1,
                    "type": "turn_context", "payload": turn_payload},
                   sort_keys=True),
    ]
    if duplicate_session:
        lines.insert(2, json.dumps({"timestamp": "1970-01-01T00:00:01Z", "ordinal": 1,
                                    "type": "session_meta", "payload": session_payload},
                                   sort_keys=True))
    if with_event_lines:
        lines.append(json.dumps({"timestamp": "1970-01-01T00:00:02Z", "ordinal": 2,
                                 "type": "event_msg",
                                 "payload": {"type": "token_count",
                                             "info": "synthetic"}},
                                sort_keys=True))
        lines.append(json.dumps({"timestamp": "1970-01-01T00:00:03Z", "ordinal": 3,
                                 "type": "response_item",
                                 "payload": {"type": "synthetic_item"}},
                                sort_keys=True))
    return "\n".join(lines).encode("utf-8")


def qwen_evidence_bytes(agent_id: str, run_id: str, model: str = "qwen3.8:27b-bf16",
                        source: bytes | None = None,
                        invocation_id: str = TURN_UUID) -> bytes:
    if source is None:
        source = synthetic_rollout_bytes(session_id=run_id)
    return json.dumps({
        "schema_version": 1,
        "evidence_kind": "local-qwen-invocation-evidence",
        "provider": "ollama_local",
        "requested_model": model,
        "reported_model": model,
        "runtime_kind": "local-qwen-codex-exec",
        "endpoint": "http://127.0.0.1:11434/v1/",
        "writer_agent_id": agent_id,
        "writer_run_id": run_id,
        "invocation_id": invocation_id,
        "source_path": "docs/governance/qwen-synthetic-rollout.jsonl",
        "source_sha256": hashlib.sha256(source).hexdigest(),
    }, sort_keys=True).encode("utf-8")


def qwen_writer_identity(agent_id: str, run_id: str, *, evidence_path: str = "docs/governance/qwen-invocation-evidence.json",
                         evidence: bytes | None = None,
                         model: str = "qwen3.8:27b-bf16",
                         source: bytes | None = None,
                         invocation_id: str = TURN_UUID) -> dict[str, object]:
    payload = evidence if evidence is not None else qwen_evidence_bytes(
        agent_id, run_id, model, source=source, invocation_id=invocation_id)
    return {
        "policy": "local-qwen-writer-v1",
        "provider": "ollama_local",
        "requested_model": model,
        "reported_model": model,
        "runtime_kind": "local-qwen-codex-exec",
        "endpoint": "http://127.0.0.1:11434/v1/",
        "writer_agent_id": agent_id,
        "writer_run_id": run_id,
        "evidence_path": evidence_path,
        "evidence_sha256": hashlib.sha256(payload).hexdigest(),
    }


def sol_writer_identity(
    root: Path, agent_id: str, run_id: str, *, prefix: str = "sol",
) -> dict[str, object]:
    source_relative = f"docs/governance/{prefix}-synthetic-rollout.jsonl"
    turn_id = "sol-turn-01"
    source = (
        json.dumps({"type": "session_meta", "payload": {
            "id": run_id, "session_id": "parent-thread", "model_provider": "openai",
            "agent_path": "/root/sol_writer", "source": {"subagent": {"thread_spawn": {
                "agent_path": "/root/sol_writer",
            }}},
        }}) + "\n" +
        json.dumps({"type": "turn_context", "payload": {
            "turn_id": turn_id, "model": "gpt-5.6-sol", "effort": "medium",
        }}) + "\n"
    ).encode()
    source_path = root / source_relative
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(source)
    evidence_relative = f"docs/governance/{prefix}-invocation-evidence.json"
    evidence = {
        "schema_version": 1, "evidence_kind": "codex-native-writer-invocation-evidence",
        "provider": "codex-native-agent", "raw_model_provider": "openai",
        "requested_model": "gpt-5.6-sol", "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "medium", "recorded_reasoning_effort": "medium",
        "runtime_kind": "codex-rollout-jsonl", "writer_agent_id": agent_id,
        "writer_run_id": run_id, "invocation_id": turn_id,
        "source_agent_path": "/root/sol_writer", "source_path": source_relative,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_capture": "immutable-local-snapshot",
    }
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    (root / evidence_relative).write_bytes(payload)
    return {
        "policy": "codex-native-sol-writer-v1", "provider": "codex-native-agent",
        "requested_model": "gpt-5.6-sol", "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "medium", "recorded_reasoning_effort": "medium",
        "runtime_kind": "codex-rollout-jsonl", "writer_agent_id": agent_id,
        "writer_run_id": run_id, "evidence_path": evidence_relative,
        "evidence_sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_synthetic_source(root: Path, source: bytes,
                           relative: str = "docs/governance/qwen-synthetic-rollout.jsonl") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source)
    return path


def write_writer_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    path = root / "docs/governance/module-writer-registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "registry_kind": "local-coordination-module-writer-registry",
        "active_leases": entries,
    }, sort_keys=True), encoding="utf-8")
    return path


class AtomicProjectRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self._write_agents(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_sol_profile_gate_rejects_explicit_qwen_identity(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "writer-profile-mismatch"):
            require_codex_native_sol_writer_profile(
                qwen_writer_identity("agent-atomic", "run-atomic-1")
            )

    @staticmethod
    def _write_agents(root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        agents = project_root_fixture().replace(
            "| module | verified module scope | `src/` | ModuleMaintainer |",
            "| atomic | records | `records/` | Atomic Records Maintainer |",
        )
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")

    def _arguments(self, root: Path, target: Path) -> dict[str, object]:
        lease = root / "leases/atomic.json"
        lease.parent.mkdir(exist_ok=True)
        identity = qwen_writer_identity("agent-atomic", "run-atomic-1",
                                        evidence_path="docs/governance/qwen-atomic-evidence.json")
        (root / "docs/governance").mkdir(parents=True, exist_ok=True)
        write_synthetic_source(root, synthetic_rollout_bytes(session_id="run-atomic-1"))
        (root / identity["evidence_path"]).write_bytes(
            qwen_evidence_bytes("agent-atomic", "run-atomic-1"))
        value = {
            "schema_version": 1,
            "receipt_kind": "local-coordination-project-record-write-lease",
            "lease_id": "lease-atomic-run-1",
            "module_key": "atomic",
            "maintainer_title": "Atomic Records Maintainer",
            "agent_id": "agent-atomic",
            "run_id": "run-atomic-1",
            "target_path": target.as_posix(),
            "owned_paths": ["records"],
            "agents_path": "AGENTS.md",
            "agents_sha256": hashlib.sha256((root / "AGENTS.md").read_bytes()).hexdigest(),
            "authority_matrix_path": "AGENTS.md#machine-enforced-authority-matrix",
            "authority_matrix_sha256": "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643",
            "lease_status": "active",
            "writer_identity": identity,
        }
        lease.write_text(json.dumps(value), encoding="utf-8")
        write_writer_registry(root, [{
            "module_key": "atomic", "maintainer_title": "Atomic Records Maintainer",
            "agent_id": "agent-atomic", "run_id": "run-atomic-1",
            "lease_id": "lease-atomic-run-1", "role": "module-maintainer",
            "owned_paths": ["records"], "lease_status": "active",
            "writer_identity": identity,
        }])
        return {
            "target": target,
            "project_root": root,
            "module_key": "atomic",
            "agent_id": "agent-atomic",
            "run_id": "run-atomic-1",
            "agents_path": Path("AGENTS.md"),
            "lease_path": Path("leases/atomic.json"),
            "lease_sha256": hashlib.sha256(lease.read_bytes()).hexdigest(),
        }

    def _update(self, target: Path, *, content: bytes, expected_sha256: str) -> str:
        return update_project_record._test_only_update_record(
            **self._arguments(self.root, target), content=content,
            expected_sha256=expected_sha256,
        )

    def test_create_and_compare_and_swap_update(self) -> None:
        first_sha = self._update(Path("records/docs/progress.md"), content=b"first", expected_sha256=MISSING_SHA)
        self.assertEqual(hashlib.sha256(b"first").hexdigest(), first_sha)
        second_sha = self._update(Path("records/docs/progress.md"), content=b"second", expected_sha256=first_sha)
        self.assertEqual(hashlib.sha256(b"second").hexdigest(), second_sha)
        self.assertEqual(b"second", (self.root / "records/docs/progress.md").read_bytes())

    def test_stale_writer_is_rejected_without_overwrite(self) -> None:
        self._update(Path("records/progress.md"), content=b"current", expected_sha256=MISSING_SHA)
        with self.assertRaisesRegex(RuntimeError, "stale-write"):
            self._update(Path("records/progress.md"), content=b"stale", expected_sha256="0" * 64)
        self.assertEqual(b"current", (self.root / "records/progress.md").read_bytes())

    def test_two_concurrent_writers_cannot_both_commit(self) -> None:
        target_path = Path("records/progress.md")
        target = self.root / target_path
        target.parent.mkdir()
        target.write_bytes(b"base")
        expected = hashlib.sha256(b"base").hexdigest()
        arguments = self._arguments(self.root, target_path)

        def write(index: int) -> bool:
            try:
                update_project_record._test_only_update_record(
                    **arguments, content=f"writer-{index}".encode(), expected_sha256=expected,
                )
                return True
            except RuntimeError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, range(2)))
        self.assertEqual([False, True], sorted(results))
        self.assertIn(target.read_text(encoding="utf-8"), {"writer-0", "writer-1"})

    def test_target_cannot_escape_project_root(self) -> None:
        with self.assertRaises(ValueError):
            self._update(Path("../outside.md"), content=b"bad", expected_sha256=MISSING_SHA)

    def test_native_windows_fails_with_actionable_wsl_message(self) -> None:
        arguments = self._arguments(self.root, Path("records/progress.md"))
        with mock.patch.object(update_project_record, "fcntl", None):
            with self.assertRaisesRegex(RuntimeError, "native-windows-unsupported-use-wsl"):
                update_project_record._test_only_update_record(
                    **arguments, content=b"bad", expected_sha256=MISSING_SHA,
                )

    def test_symlinked_parent_cannot_redirect_write_outside_project(self) -> None:
        outside = Path(tempfile.mkdtemp())
        (self.root / "records").mkdir()
        (self.root / "records/linked").symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises((ValueError, OSError)):
                self._update(Path("records/linked/progress.md"), content=b"bad", expected_sha256=MISSING_SHA)
            self.assertFalse((outside / "progress.md").exists())
        finally:
            outside.rmdir()

    def test_project_root_swap_cannot_redirect_write_outside_project(self) -> None:
        project = self.root / "project"
        outside = self.root / "outside"
        moved = self.root / "project-original"
        project.mkdir()
        outside.mkdir()
        self._write_agents(project)
        arguments = self._arguments(project, Path("records/progress.md"))
        (outside / "AGENTS.md").write_bytes((project / "AGENTS.md").read_bytes())
        (outside / "leases").mkdir()
        (outside / "leases/atomic.json").write_bytes(
            (project / "leases/atomic.json").read_bytes()
        )
        shutil.copytree(project / "docs/governance", outside / "docs/governance")
        (outside / "records").mkdir()
        (outside / "records/progress.md").write_bytes(b"outside")
        authorize_project_record_write(
            root=outside, target=Path("records/progress.md"), module_key="atomic",
            agent_id="agent-atomic", run_id="run-atomic-1", agents_path=Path("AGENTS.md"),
            lease_path=Path("leases/atomic.json"), lease_sha256=arguments["lease_sha256"],
            authorization_mode="delivery-first-local-coordination",
        )
        original_resolve = update_project_record._resolve_target

        def swap_root(target: Path, root: Path) -> Path:
            resolved = original_resolve(target, root)
            project.rename(moved)
            project.symlink_to(outside, target_is_directory=True)
            return resolved

        with mock.patch.object(update_project_record, "_resolve_target", side_effect=swap_root):
            with self.assertRaises((OSError, RuntimeError)):
                update_project_record._test_only_update_record(
                    **arguments, content=b"bad",
                    expected_sha256=hashlib.sha256(b"outside").hexdigest(),
                )
        self.assertEqual(b"outside", (outside / "records/progress.md").read_bytes())


class AuthorizedProjectRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        agents = project_root_fixture().replace(
            "| module | verified module scope | `src/` | ModuleMaintainer |",
            "| m01 | records | `docs/m01/` | M01 Maintainer |\n"
            "| m02 | records | `docs/m02/` | M02 Maintainer |",
        )
        self.agents = self.root / "AGENTS.md"
        self.agents.write_text(agents, encoding="utf-8")
        self.lease = self.root / "leases/m01.json"
        self.lease.parent.mkdir()
        self.target = Path("docs/m01/progress.md")
        self.source = synthetic_rollout_bytes(session_id="run-m01-1")
        self.source_file = write_synthetic_source(self.root, self.source)
        self.evidence = qwen_evidence_bytes("agent-m01", "run-m01-1")
        self.evidence_file = self.root / "docs/governance/qwen-invocation-evidence.json"
        self.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_file.write_bytes(self.evidence)
        self.lease_value = self._lease_value()
        self._write_lease(self.lease_value)
        self.registry = write_writer_registry(self.root, [self._registry_entry()])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _lease_value(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "receipt_kind": "local-coordination-project-record-write-lease",
            "lease_id": "lease-m01-run-1",
            "module_key": "m01",
            "maintainer_title": "M01 Maintainer",
            "agent_id": "agent-m01",
            "run_id": "run-m01-1",
            "target_path": self.target.as_posix(),
            "owned_paths": ["docs/m01"],
            "agents_path": "AGENTS.md",
            "agents_sha256": hashlib.sha256(self.agents.read_bytes()).hexdigest(),
            "authority_matrix_path": "AGENTS.md#machine-enforced-authority-matrix",
            "authority_matrix_sha256": "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643",
            "lease_status": "active",
            "writer_identity": qwen_writer_identity(
                "agent-m01", "run-m01-1", evidence=self.evidence,
            ),
        }


    def _write_lease(self, value: dict[str, object]) -> str:
        self.lease.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return hashlib.sha256(self.lease.read_bytes()).hexdigest()

    def _registry_entry(self) -> dict[str, object]:
        return {
            "module_key": "m01", "maintainer_title": "M01 Maintainer",
            "agent_id": self.lease_value["agent_id"], "run_id": self.lease_value["run_id"],
            "lease_id": self.lease_value["lease_id"], "role": "module-maintainer",
            "owned_paths": ["docs/m01"], "lease_status": "active",
            "writer_identity": self.lease_value["writer_identity"],
        }


    def _write_registry(self, entries: list[dict[str, object]]) -> None:
        self.registry = write_writer_registry(self.root, entries)

    def _authorized_update(self, **overrides: object) -> str:
        arguments: dict[str, object] = {
            "target": self.target,
            "project_root": self.root,
            "content": b"authorized",
            "expected_sha256": MISSING_SHA,
            "module_key": "m01",
            "agent_id": "agent-m01",
            "run_id": "run-m01-1",
            "agents_path": Path("AGENTS.md"),
            "lease_path": Path("leases/m01.json"),
            "lease_sha256": hashlib.sha256(self.lease.read_bytes()).hexdigest(),
        }
        arguments.update(overrides)
        return update_project_record._test_only_update_record(**arguments)

    def _local_coordination_update(self, **overrides: object) -> str:
        arguments: dict[str, object] = {
            "target": self.target,
            "project_root": self.root,
            "content": b"delivery-first",
            "expected_sha256": MISSING_SHA,
            "module_key": "m01",
            "agent_id": "agent-m01",
            "run_id": "run-m01-1",
            "agents_path": Path("AGENTS.md"),
            "lease_path": Path("leases/m01.json"),
            "lease_sha256": hashlib.sha256(self.lease.read_bytes()).hexdigest(),
        }
        arguments.update(overrides)
        return update_record(**arguments)

    def _rewrite_lease_identity(self, agent_id: str, run_id: str) -> None:
        self.source = synthetic_rollout_bytes(session_id=run_id)
        self.source_file.write_bytes(self.source)
        self.evidence = qwen_evidence_bytes(
            agent_id, run_id, source=self.source)
        self.evidence_file.write_bytes(self.evidence)
        self.lease_value = dict(
            self.lease_value, agent_id=agent_id, run_id=run_id,
            lease_id=f"lease-{run_id}",
            writer_identity=qwen_writer_identity(
                agent_id, run_id, evidence=self.evidence,
            ),
        )
        self._write_lease(self.lease_value)
        self._write_registry([self._registry_entry()])

    def _drift_after_authorization(self, mutation: "object") -> None:
        original_authorize = update_project_record.authorize_project_record_write
        state = {"done": False}

        def authorize_after_drift(**kwargs: object) -> object:
            binding = original_authorize(**kwargs)
            if not state["done"]:
                state["done"] = True
                mutation()
            return binding

        with mock.patch.object(update_project_record, "authorize_project_record_write",
                               side_effect=authorize_after_drift):
            return self._authorized_update()

    def test_cross_module_m02_writer_cannot_overwrite_m01_record(self) -> None:
        m02_source = synthetic_rollout_bytes(session_id="run-m02-1",
                                             turn_id=TURN2_UUID)
        write_synthetic_source(
            self.root, m02_source,
            relative="docs/governance/qwen-m02-synthetic-rollout.jsonl")
        ev = qwen_evidence_bytes("agent-m02", "run-m02-1", source=m02_source,
                                 invocation_id=TURN2_UUID)
        # point the m02 evidence at its own synthetic source file
        ev = ev.replace(b"docs/governance/qwen-synthetic-rollout.jsonl",
                        b"docs/governance/qwen-m02-synthetic-rollout.jsonl")
        (self.root / "docs/governance/qwen-m02-evidence.json").write_bytes(ev)
        identity = qwen_writer_identity("agent-m02", "run-m02-1",
                                        evidence_path="docs/governance/qwen-m02-evidence.json",
                                        evidence=ev)
        mutated = dict(self.lease_value, module_key="m02",
                       maintainer_title="M02 Maintainer", agent_id="agent-m02",
                       run_id="run-m02-1", owned_paths=["docs/m02"],
                       writer_identity=identity)
        self._write_lease(mutated)
        self._write_registry([{
            "module_key": "m02", "maintainer_title": "M02 Maintainer",
            "agent_id": "agent-m02", "run_id": "run-m02-1",
            "lease_id": self.lease_value["lease_id"], "role": "module-maintainer",
            "owned_paths": ["docs/m02"], "lease_status": "active",
            "writer_identity": identity,
        }])
        with self.assertRaisesRegex(RuntimeError, "module-ownership-mismatch"):
            self._authorized_update(module_key="m02", agent_id="agent-m02", run_id="run-m02-1")
        self.assertFalse((self.root / self.target).exists())

    def test_missing_host_attested_lease_fails_closed(self) -> None:
        self.lease.unlink()
        with self.assertRaisesRegex((OSError, RuntimeError), "lease"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_lease_or_canonical_ownership_drift_fails_closed(self) -> None:
        self.agents.write_text(
            self.agents.read_text(encoding="utf-8").replace("`docs/m01/`", "`docs/m01-renamed/`"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "ownership-or-agents-drift"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_lease_identity_mismatch_fails_closed(self) -> None:
        mutated = dict(self.lease_value, agent_id="agent-m02")
        self._write_lease(mutated)
        with self.assertRaisesRegex(RuntimeError, "invalid-record-write-lease"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_lease_change_after_authorization_fails_before_write(self) -> None:
        def mutation() -> None:
            self.lease.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, 'ownership-or-lease-drift'):
            self._drift_after_authorization(mutation)
        self.assertFalse((self.root / self.target).exists())

    def test_registry_change_after_authorization_fails_before_write(self) -> None:
        def mutation() -> None:
            self.registry.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, 'ownership-or-lease-drift'):
            self._drift_after_authorization(mutation)
        self.assertFalse((self.root / self.target).exists())

    def test_writer_evidence_change_after_authorization_fails_before_write(self) -> None:
        def mutation() -> None:
            self.evidence_file.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, 'ownership-or-lease-drift'):
            self._drift_after_authorization(mutation)
        self.assertFalse((self.root / self.target).exists())

    def test_rejection_happens_before_target_dir_or_content_creation(self) -> None:
        old_identity = dict(self.lease_value["writer_identity"],
                            evidence_sha256="0" * 64)
        self._write_lease(dict(self.lease_value, writer_identity=old_identity))
        try:
            self._authorized_update()
            self.fail("expected writer identity rejection")
        except RuntimeError as error:
            self.assertIn("writer-evidence-hash-mismatch", str(error))
        self.assertFalse((self.root / self.target).exists())
        self.assertFalse((self.root / "docs/m01").exists())
        created = [path for path in self.root.rglob("*") if path.name == ".project-record-authority.lock"]
        self.assertEqual(1, len(created))

    def test_write_lease_schema_is_closed(self) -> None:
        schema = json.loads(
            (SCRIPT.parent.parent / "assets/project-record-write-lease.schema.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(self.lease_value), set(schema["required"]))
        mutated = dict(self.lease_value, project_override=True)
        self._write_lease(mutated)
        with self.assertRaisesRegex(RuntimeError, "invalid-record-write-lease"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_write_lease_schema_requires_exact_qwen_model_and_effort_pairs(self) -> None:
        schema = json.loads(
            (SCRIPT.parent.parent / "assets/project-record-write-lease.schema.json").read_text(
                encoding="utf-8",
            )
        )
        qwen = schema["$defs"]["writerIdentity"]["oneOf"][1]
        model_pairs = qwen["allOf"][0]["oneOf"]
        self.assertEqual({
            ("qwen3.8:27b-bf16", "qwen3.8:27b-bf16"),
            ("qwen3.8:27b-q8_0", "qwen3.8:27b-q8_0"),
        }, {
            (branch["properties"]["requested_model"]["const"],
             branch["properties"]["reported_model"]["const"])
            for branch in model_pairs
        })
        effort_pairs = qwen["allOf"][1]["oneOf"][1:]
        self.assertEqual({("none", "none"), ("xhigh", "xhigh")}, {
            (branch["properties"]["requested_reasoning_effort"]["const"],
             branch["properties"]["reported_reasoning_effort"]["const"])
            for branch in effort_pairs
        })

    def test_writer_registry_schema_is_closed_and_matches_runtime_contract(self) -> None:
        schema = json.loads(
            (SCRIPT.parent.parent / "assets/module-writer-registry.schema.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["active_leases"]["items"]["additionalProperties"])
        self.assertEqual(
            set(self._registry_entry()),
            set(schema["properties"]["active_leases"]["items"]["required"]),
        )

    def test_registered_m01_maintainer_with_host_lease_can_update(self) -> None:
        new_sha = self._authorized_update()
        self.assertEqual(hashlib.sha256(b"authorized").hexdigest(), new_sha)
        self.assertEqual(b"authorized", (self.root / self.target).read_bytes())

    def test_delivery_first_local_coordination_is_default_and_does_not_need_host_verifier(self) -> None:
        new_sha = self._local_coordination_update()
        self.assertEqual(hashlib.sha256(b"delivery-first").hexdigest(), new_sha)
        self.assertEqual(b"delivery-first", (self.root / self.target).read_bytes())

    def test_delivery_first_rejects_self_selected_dispatcher_identity(self) -> None:
        self._rewrite_lease_identity("dispatcher-agent", "dispatcher-run")
        self._write_registry([{
            **self._registry_entry(), "agent_id": "agent-m01", "run_id": "run-m01-1",
            "lease_id": "lease-m01-run-1",
            "writer_identity": qwen_writer_identity(
                "agent-m01", "run-m01-1", evidence=self.evidence,
            ),
        }])
        with self.assertRaisesRegex(RuntimeError, "registered-writer-binding-mismatch"):
            self._local_coordination_update(
                agent_id="dispatcher-agent", run_id="dispatcher-run",
            )
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_rejects_multiple_active_writers_for_module(self) -> None:
        second = {
            **self._registry_entry(), "agent_id": "second-agent", "run_id": "second-run",
            "lease_id": "second-lease",
        }
        self._write_registry([self._registry_entry(), second])
        with self.assertRaisesRegex(RuntimeError, "duplicate-registry-identity"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_rejects_writer_identity_reused_across_modules(self) -> None:
        second = {
            **self._registry_entry(), "module_key": "m02",
            "maintainer_title": "M02 Maintainer", "run_id": "run-m02-1",
            "lease_id": "lease-m02-run-1", "owned_paths": ["src/m02"],
        }
        self._write_registry([self._registry_entry(), second])
        with self.assertRaisesRegex(RuntimeError, "duplicate-registry-identity"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_rejects_distinct_active_writers_across_modules(self) -> None:
        second_identity = qwen_writer_identity(
            "agent-m02", "run-m02-1", evidence_path="docs/governance/qwen-m02.json",
        )
        second = {
            **self._registry_entry(), "module_key": "m02", "agent_id": "agent-m02",
            "maintainer_title": "M02 Maintainer", "run_id": "run-m02-1",
            "lease_id": "lease-m02-run-1", "owned_paths": ["src/m02"],
            "writer_identity": second_identity,
        }
        self._write_registry([self._registry_entry(), second])
        with self.assertRaisesRegex(RuntimeError, "canonical-writer-not-unique"):
            self._local_coordination_update()

    def test_delivery_first_rejects_missing_active_writer_for_module(self) -> None:
        self._write_registry([])
        with self.assertRaisesRegex(RuntimeError, "canonical-writer-not-unique"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_still_rejects_cross_module_target(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            self._local_coordination_update(
                module_key="m02", agent_id="agent-m02", run_id="run-m02-1",
            )
        self.assertFalse((self.root / self.target).exists())

    def test_strict_security_native_writer_route_fails_closed_unsupported(self) -> None:
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        with self.assertRaisesRegex(RuntimeError, "strict-native-writer-unsupported"):
            update_record(
                self.target, project_root=self.root, content=b"strict",
                expected_sha256=MISSING_SHA, module_key="m01",
                agent_id="agent-m01", run_id="run-m01-1",
                agents_path=Path("AGENTS.md"), lease_path=Path("leases/m01.json"),
                lease_sha256=hashlib.sha256(self.lease.read_bytes()).hexdigest(),
                authorization_mode="strict-security",
            )
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertFalse((self.root / self.target).exists())

    def test_authorization_helper_rejects_strict_native_writer_route(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "strict-native-writer-unsupported"):
            authorize_project_record_write(
                root=self.root, target=self.target, module_key="m01",
                agent_id="agent-m01", run_id="run-m01-1",
                agents_path=Path("AGENTS.md"), lease_path=Path("leases/m01.json"),
                lease_sha256=hashlib.sha256(self.lease.read_bytes()).hexdigest(),
                authorization_mode="strict-security",
            )

    def test_child_qwen_run_with_matching_lease_and_evidence_can_write(self) -> None:
        self._rewrite_lease_identity("child-agent-m01", "child-run-m01")
        self._authorized_update(agent_id="child-agent-m01", run_id="child-run-m01")
        self.assertEqual(b"authorized", (self.root / self.target).read_bytes())

    def test_mutated_current_authority_matrix_cannot_authorize_write(self) -> None:
        dispatcher = '"dispatcher":{'
        text = self.agents.read_text(encoding="utf-8")
        self.agents.write_text(
            text.replace(dispatcher, dispatcher + '"write":"allow",', 1), encoding="utf-8",
        )
        self.lease_value = dict(
            self.lease_value,
            agents_sha256=hashlib.sha256(self.agents.read_bytes()).hexdigest(),
        )
        self._write_lease(self.lease_value)
        with self.assertRaisesRegex(RuntimeError, "authority-matrix"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_public_api_and_cli_cannot_inject_test_verifier(self) -> None:
        self.assertNotIn("host_attestation_verifier", inspect.signature(update_record).parameters)
        with self.assertRaises(TypeError):
            update_record(
                self.target, project_root=self.root, content=b"bad", expected_sha256=MISSING_SHA,
                host_attestation_verifier=lambda *_: True,
            )
        source = self.root / "content.txt"
        source.write_bytes(b"legacy-cli-bypass")
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPT), self.target.as_posix(),
                "--project-root", str(self.root), "--content-file", str(source),
                "--expected-sha256", MISSING_SHA,
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse((self.root / self.target).exists())

        full_command = [
            sys.executable, str(SCRIPT), self.target.as_posix(),
            "--project-root", str(self.root), "--content-file", str(source),
            "--expected-sha256", MISSING_SHA, "--module-key", "m01",
            "--agent-id", "agent-m01", "--run-id", "run-m01-1",
            "--agents-path", "AGENTS.md", "--lease-path", "leases/m01.json",
            "--lease-sha256", hashlib.sha256(self.lease.read_bytes()).hexdigest(),
            "--authorization-mode", "strict-security",
        ]
        completed = subprocess.run(full_command, text=True, capture_output=True, check=False)
        self.assertEqual(1, completed.returncode)
        self.assertIn("strict-native-writer-unsupported", completed.stdout)
        self.assertFalse((self.root / self.target).exists())
        self.assertFalse((self.root / "docs/m01").exists())

    def test_bound_local_qwen_writer_identity_is_accepted(self) -> None:
        new_sha = self._authorized_update()
        self.assertEqual(hashlib.sha256(b"authorized").hexdigest(), new_sha)

    def test_bound_codex_native_sol_writer_identity_is_accepted(self) -> None:
        identity = sol_writer_identity(self.root, "agent-m01", "run-m01-1")
        self._write_lease(dict(self.lease_value, writer_identity=identity))
        self._write_registry([{**self._registry_entry(), "writer_identity": identity}])
        new_sha = self._authorized_update()
        self.assertEqual(hashlib.sha256(b"authorized").hexdigest(), new_sha)

    def test_native_gpt_writer_identity_is_rejected(self) -> None:
        ev = qwen_evidence_bytes("agent-m01", "run-m01-1", model="gpt-6-astra",
                                 source=self.source)
        (self.root / "docs/governance/qwen-gpt-evidence.json").write_bytes(ev)
        identity = qwen_writer_identity(
            "agent-m01", "run-m01-1", model="gpt-6-astra",
            evidence_path="docs/governance/qwen-gpt-evidence.json", evidence=ev,
        )
        self._write_lease(dict(self.lease_value, writer_identity=identity))
        self._write_registry([{**self._registry_entry(), "writer_identity": identity}])
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_other_local_model_writer_identity_is_rejected(self) -> None:
        ev = qwen_evidence_bytes("agent-m01", "run-m01-1", model="llama3:8b",
                                 source=self.source)
        (self.root / "docs/governance/qwen-llama-evidence.json").write_bytes(ev)
        identity = qwen_writer_identity(
            "agent-m01", "run-m01-1", model="llama3:8b",
            evidence_path="docs/governance/qwen-llama-evidence.json", evidence=ev,
        )
        self._write_lease(dict(self.lease_value, writer_identity=identity))
        self._write_registry([{**self._registry_entry(), "writer_identity": identity}])
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_old_lease_without_writer_identity_is_rejected(self) -> None:
        old = {key: value for key, value in self.lease_value.items() if key != "writer_identity"}
        self._write_lease(old)
        with self.assertRaisesRegex(RuntimeError, "invalid-record-write-lease"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_missing_evidence_file_is_rejected(self) -> None:
        self.evidence_file.unlink()
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_evidence_model_or_run_mismatch_is_rejected(self) -> None:
        ev = qwen_evidence_bytes("agent-m01", "run-m01-2", source=self.source)
        (self.root / "docs/governance/qwen-mismatch-evidence.json").write_bytes(ev)
        identity = qwen_writer_identity(
            "agent-m01", "run-m01-1",
            evidence_path="docs/governance/qwen-mismatch-evidence.json", evidence=ev,
        )
        self._write_lease(dict(self.lease_value, writer_identity=identity))
        self._write_registry([{**self._registry_entry(), "writer_identity": identity}])
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-evidence"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_registry_writer_identity_mismatch_is_rejected(self) -> None:
        identity = self.lease_value["writer_identity"]
        other = dict(identity,
                     evidence_sha256=hashlib.sha256(self.evidence + b"x").hexdigest())
        self._write_registry([{**self._registry_entry(), "writer_identity": other}])
        with self.assertRaisesRegex(RuntimeError, "registered-writer-binding-mismatch"):
            self._authorized_update()
        self.assertFalse((self.root / self.target).exists())

    def test_existing_scope_and_cas_still_apply_with_qwen_writer(self) -> None:
        self._authorized_update()
        with self.assertRaisesRegex(RuntimeError, "stale-write"):
            self._authorized_update(expected_sha256="0" * 64)
        self.assertEqual(b"authorized", (self.root / self.target).read_bytes())
        with self.assertRaisesRegex(RuntimeError, "invalid-writer-identity"):
            self._local_coordination_update(
                module_key="m02", agent_id="agent-m02", run_id="run-m02-1",
            )


if __name__ == "__main__":
    unittest.main()
