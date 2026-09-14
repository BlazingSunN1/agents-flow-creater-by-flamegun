from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from historical_project_record_authorization import validate_historical_project_record_write_proof
from project_record_authorization import DELIVERY_FIRST_MODE, authorize_project_record_write
from test_update_project_record import sol_writer_identity, write_writer_registry
from test_validate_agents_md import project_root_fixture


AUTHORITY_SHA = "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643"


class HistoricalProjectRecordAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        agents = project_root_fixture().replace(
            "| module | verified module scope | `src/` | ModuleMaintainer |",
            "| governance | records | `records/` | Governance Maintainer |",
        )
        (self.root / "AGENTS.md").write_text(agents, encoding="utf-8")
        (self.root / "history").mkdir()
        (self.root / "leases").mkdir()
        self.identity = sol_writer_identity(self.root, "aggregation-agent", "aggregation-run")
        self.agents_sha = hashlib.sha256((self.root / "AGENTS.md").read_bytes()).hexdigest()
        (self.root / "history/AGENTS.md").write_bytes((self.root / "AGENTS.md").read_bytes())
        self.history_target = Path("records/aggregation-receipt.json")
        self.live_target = Path("records/system-manifest.json")
        (self.root / "records").mkdir()
        (self.root / self.history_target).write_text("{}\n", encoding="utf-8")
        (self.root / self.live_target).write_text("{}\n", encoding="utf-8")
        self.history_lease = self._lease("lease-history", self.history_target, "closed")
        self.live_lease = self._lease("lease-live", self.live_target, "active")
        self._write_json("leases/history.json", self.history_lease)
        self.live_sha = self._write_json("leases/live.json", self.live_lease)
        history_entry = self._entry("lease-history")
        history_registry = {
            "schema_version": 1,
            "registry_kind": "local-coordination-module-writer-registry",
            "active_leases": [history_entry],
        }
        self.history_registry_sha = self._write_json("history/registry.json", history_registry)
        write_writer_registry(self.root, [self._entry("lease-live")])
        resolved = authorize_project_record_write(
            root=self.root, target=self.live_target, module_key="governance",
            agent_id="aggregation-agent", run_id="aggregation-run",
            agents_path=Path("AGENTS.md"), lease_path=Path("leases/live.json"),
            lease_sha256=self.live_sha, authorization_mode=DELIVERY_FIRST_MODE,
        )
        self.proof = {
            "schema_version": 1,
            "proof_kind": "local-coordination-historical-project-record-write-proof",
            "module_key": "governance", "maintainer_title": "Governance Maintainer",
            "agent_id": "aggregation-agent", "run_id": "aggregation-run",
            "lease_id": "lease-history", "target_path": self.history_target.as_posix(),
            "owned_paths": ["records"],
            "lease_path": "leases/history.json",
            "lease_sha256": hashlib.sha256((self.root / "leases/history.json").read_bytes()).hexdigest(),
            "registry_snapshot_path": "history/registry.json",
            "registry_snapshot_sha256": self.history_registry_sha,
            "agents_snapshot_path": "history/AGENTS.md", "agents_snapshot_sha256": self.agents_sha,
            "writer_evidence_path": resolved.writer_evidence_path.as_posix(),
            "writer_evidence_sha256": resolved.writer_evidence_sha256,
            "writer_source_path": resolved.writer_source_path.as_posix(),
            "writer_source_sha256": resolved.writer_source_sha256,
            "baseline_sha256": "b" * 64, "code_version": "code-v1",
            "build_id": "build-v1", "candidate_sha256": "c" * 64,
        }
        self.proof_sha = self._write_json("history/proof.json", self.proof)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_json(self, relative: str, value: object) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _lease(self, lease_id: str, target: Path, status: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "receipt_kind": "local-coordination-project-record-write-lease",
            "lease_id": lease_id, "module_key": "governance",
            "maintainer_title": "Governance Maintainer",
            "agent_id": "aggregation-agent", "run_id": "aggregation-run",
            "target_path": target.as_posix(), "owned_paths": ["records"],
            "agents_path": "AGENTS.md", "agents_sha256": self.agents_sha,
            "authority_matrix_path": "AGENTS.md#machine-enforced-authority-matrix",
            "authority_matrix_sha256": AUTHORITY_SHA,
            "lease_status": status, "writer_identity": self.identity,
        }

    def _entry(self, lease_id: str) -> dict[str, object]:
        return {
            "module_key": "governance", "maintainer_title": "Governance Maintainer",
            "agent_id": "aggregation-agent", "run_id": "aggregation-run",
            "lease_id": lease_id, "role": "module-maintainer",
            "owned_paths": ["records"], "lease_status": "active",
            "writer_identity": self.identity,
        }

    def _validate(self, **updates: object) -> None:
        args = {
            "root": self.root, "proof_path": Path("history/proof.json"),
            "proof_sha256": self.proof_sha, "target": self.history_target,
            "module_key": "governance", "maintainer_title": "Governance Maintainer",
            "agent_id": "aggregation-agent", "run_id": "aggregation-run",
            "lease_id": "lease-history", "owned_paths": ["records"],
            "baseline_sha256": "b" * 64, "code_version": "code-v1",
            "build_id": "build-v1", "candidate_sha256": "c" * 64,
        }
        args.update(updates)
        validate_historical_project_record_write_proof(**args)

    def test_closed_history_survives_transfer_but_cannot_authorize_current_write(self) -> None:
        self._validate()
        with self.assertRaises(RuntimeError):
            authorize_project_record_write(
                root=self.root, target=self.history_target, module_key="governance",
                agent_id="aggregation-agent", run_id="aggregation-run",
                agents_path=Path("AGENTS.md"), lease_path=Path("leases/history.json"),
                lease_sha256=str(self.proof["lease_sha256"]), authorization_mode=DELIVERY_FIRST_MODE,
            )
        authorize_project_record_write(
            root=self.root, target=self.live_target, module_key="governance",
            agent_id="aggregation-agent", run_id="aggregation-run",
            agents_path=Path("AGENTS.md"), lease_path=Path("leases/live.json"),
            lease_sha256=self.live_sha, authorization_mode=DELIVERY_FIRST_MODE,
        )

    def test_history_is_bound_to_candidate_code_build_and_target(self) -> None:
        for change in (
            {"candidate_sha256": "d" * 64}, {"code_version": "code-v2"},
            {"build_id": "build-v2"}, {"target": self.live_target},
            {"lease_id": "lease-other"},
        ):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self._validate(**change)

    def test_history_rejects_non_integer_schema_version(self) -> None:
        for schema_version in (True, False, "1", 1.0):
            with self.subTest(schema_version=schema_version):
                self.proof["schema_version"] = schema_version
                self.proof_sha = self._write_json("history/proof.json", self.proof)
                with self.assertRaisesRegex(RuntimeError, "invalid-historical-write-proof"):
                    self._validate()
        self.proof["schema_version"] = 1
        self.proof_sha = self._write_json("history/proof.json", self.proof)
        self._validate()

    def test_history_registry_must_have_one_matching_active_writer(self) -> None:
        for entries in ([], [self._entry("lease-history"), self._entry("lease-other")]):
            with self.subTest(count=len(entries)):
                registry = {
                    "schema_version": 1,
                    "registry_kind": "local-coordination-module-writer-registry",
                    "active_leases": entries,
                }
                self.proof["registry_snapshot_sha256"] = self._write_json("history/registry.json", registry)
                self.proof_sha = self._write_json("history/proof.json", self.proof)
                with self.assertRaises(RuntimeError):
                    self._validate()

    def test_historical_source_or_snapshot_hash_drift_fails(self) -> None:
        (self.root / str(self.proof["writer_source_path"])).write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self._validate()


if __name__ == "__main__":
    unittest.main()
