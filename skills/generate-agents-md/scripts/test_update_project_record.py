from __future__ import annotations

import hashlib
import inspect
import json
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
from test_validate_agents_md import project_root_fixture


SCRIPT = Path(__file__).resolve().parent / "update_project_record.py"


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
        value = {
            "schema_version": 1,
            "receipt_kind": "host-attested-project-record-write-lease",
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
        }
        lease.write_text(json.dumps(value), encoding="utf-8")
        write_writer_registry(root, [{
            "module_key": "atomic", "maintainer_title": "Atomic Records Maintainer",
            "agent_id": "agent-atomic", "run_id": "run-atomic-1",
            "lease_id": "lease-atomic-run-1", "role": "module-maintainer",
            "owned_paths": ["records"], "lease_status": "active",
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
            "_test_only_host_attestation_verifier": lambda *_: True,
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
        (outside / "docs/governance").mkdir(parents=True)
        (outside / "docs/governance/module-writer-registry.json").write_bytes(
            (project / "docs/governance/module-writer-registry.json").read_bytes()
        )
        (outside / "records").mkdir()
        (outside / "records/progress.md").write_bytes(b"outside")
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
        self.lease_value = self._lease_value()
        self._write_lease(self.lease_value)
        self.registry = write_writer_registry(self.root, [self._registry_entry()])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _lease_value(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "receipt_kind": "host-attested-project-record-write-lease",
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
            "_test_only_host_attestation_verifier": lambda *_: True,
        }
        arguments.update(overrides)
        return update_project_record._test_only_update_record(**arguments)

    def _local_coordination_update(self, **overrides: object) -> str:
        self.lease_value = dict(
            self.lease_value,
            receipt_kind="local-coordination-project-record-write-lease",
        )
        self._write_lease(self.lease_value)
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

    @staticmethod
    def _lease_authority_verifier(
        *, actual_role: str, active_lease_count: int = 1,
    ) -> object:
        def verify(_path: Path, _value: dict[str, object], expected: dict[str, object]) -> bool:
            return expected.get("host_write_authority") == {
                "required_role": "module-maintainer",
                "unique_active_lease": True,
                "hierarchy_independent": True,
            } and actual_role == "module-maintainer" and active_lease_count == 1
        return verify

    def _rewrite_lease_identity(self, agent_id: str, run_id: str) -> None:
        self.lease_value = dict(
            self.lease_value, agent_id=agent_id, run_id=run_id,
            lease_id=f"lease-{run_id}",
        )
        self._write_lease(self.lease_value)
        self._write_registry([self._registry_entry()])

    def test_cross_module_m02_writer_cannot_overwrite_m01_record(self) -> None:
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

    def test_lease_change_after_host_verification_fails_before_write(self) -> None:
        def drift_after_verification(*_: object) -> bool:
            self.lease.write_text("{}", encoding="utf-8")
            return True

        with self.assertRaisesRegex(RuntimeError, "ownership-or-lease-drift"):
            self._authorized_update(
                _test_only_host_attestation_verifier=drift_after_verification,
            )
        self.assertFalse((self.root / self.target).exists())

    def test_registry_change_after_authorization_fails_before_write(self) -> None:
        def drift_after_verification(*_: object) -> bool:
            self.registry.write_text("{}", encoding="utf-8")
            return True

        with self.assertRaisesRegex(RuntimeError, "ownership-or-lease-drift"):
            self._authorized_update(
                _test_only_host_attestation_verifier=drift_after_verification,
            )
        self.assertFalse((self.root / self.target).exists())

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
        with self.assertRaisesRegex(RuntimeError, "canonical-writer-not-unique"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_rejects_writer_identity_reused_across_modules(self) -> None:
        second = {
            **self._registry_entry(), "module_key": "m02",
            "maintainer_title": "M02 Maintainer", "run_id": "run-m02-1",
            "lease_id": "lease-m02-run-1", "owned_paths": ["src/m02"],
        }
        self._write_registry([self._registry_entry(), second])
        with self.assertRaisesRegex(RuntimeError, "canonical-writer-not-unique"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_rejects_missing_active_writer_for_module(self) -> None:
        self._write_registry([])
        with self.assertRaisesRegex(RuntimeError, "canonical-writer-not-unique"):
            self._local_coordination_update()
        self.assertFalse((self.root / self.target).exists())

    def test_delivery_first_still_rejects_cross_module_target(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "module-ownership-mismatch"):
            self._local_coordination_update(
                module_key="m02", agent_id="agent-m02", run_id="run-m02-1",
            )
        self.assertFalse((self.root / self.target).exists())

    def test_strict_security_still_requires_host_attestation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "host-attested-lease-required"):
            update_record(
                self.target, project_root=self.root, content=b"strict",
                expected_sha256=MISSING_SHA, module_key="m01",
                agent_id="agent-m01", run_id="run-m01-1",
                agents_path=Path("AGENTS.md"), lease_path=Path("leases/m01.json"),
                lease_sha256=hashlib.sha256(self.lease.read_bytes()).hexdigest(),
                authorization_mode="strict-security",
            )
        self.assertFalse((self.root / self.target).exists())

    def test_child_agent_has_no_inherent_write_but_valid_maintainer_lease_passes(self) -> None:
        self._rewrite_lease_identity("child-agent-m01", "child-run-m01")
        self._authorized_update(
            agent_id="child-agent-m01", run_id="child-run-m01",
            _test_only_host_attestation_verifier=self._lease_authority_verifier(
                actual_role="module-maintainer",
            ),
        )
        self.assertEqual(b"authorized", (self.root / self.target).read_bytes())

    def test_main_agent_can_write_only_as_distinct_attested_maintainer_run(self) -> None:
        self._rewrite_lease_identity("main-agent-m01", "main-impl-run-m01")
        self._authorized_update(
            agent_id="main-agent-m01", run_id="main-impl-run-m01",
            _test_only_host_attestation_verifier=self._lease_authority_verifier(
                actual_role="module-maintainer",
            ),
        )
        self.assertEqual(b"authorized", (self.root / self.target).read_bytes())

    def test_dispatcher_and_independent_agents_cannot_use_maintainer_lease(self) -> None:
        for role in ("dispatcher", "independent-reviewer", "black-box"):
            with self.subTest(role=role):
                with self.assertRaisesRegex(RuntimeError, "host-attested-lease-required"):
                    self._authorized_update(
                        _test_only_host_attestation_verifier=self._lease_authority_verifier(
                            actual_role=role,
                        ),
                    )
                self.assertFalse((self.root / self.target).exists())

    def test_second_active_writer_lease_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "host-attested-lease-required"):
            self._authorized_update(
                _test_only_host_attestation_verifier=self._lease_authority_verifier(
                    actual_role="module-maintainer", active_lease_count=2,
                ),
            )
        self.assertFalse((self.root / self.target).exists())

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
            self._authorized_update(
                _test_only_host_attestation_verifier=self._lease_authority_verifier(
                    actual_role="module-maintainer",
                ),
            )
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
        self.assertIn("host-attested-lease-required", completed.stdout)
        bypass = subprocess.run(
            full_command + ["--test-only-host-attestation"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(2, bypass.returncode)
        self.assertFalse((self.root / self.target).exists())

    def test_public_api_without_host_attestation_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "host-attested-lease-required"):
            update_record(
                self.target, project_root=self.root, content=b"bad",
                expected_sha256=MISSING_SHA, module_key="m01",
                agent_id="agent-m01", run_id="run-m01-1",
                agents_path=Path("AGENTS.md"), lease_path=Path("leases/m01.json"),
                lease_sha256=hashlib.sha256(self.lease.read_bytes()).hexdigest(),
                authorization_mode="strict-security",
            )
        self.assertFalse((self.root / self.target).exists())


if __name__ == "__main__":
    unittest.main()
