from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agents_dispatcher_policy_validation import module_ownership_mapping
from agents_policy_common import REQUIRED_MACHINE_POLICY
from project_record_authorization import (
    LEASE_FIELDS,
    _authority_matrix_sha256,
    _bound_project_file,
    _canonical_identity,
    _registered_writer,
    _require_registered_writer,
    _target_is_owned,
    _validate_lease_writer_identity,
    _valid_owned_paths,
)
from strict_json import loads as strict_json_loads


SHA256_FIELDS = (
    "baseline_sha256", "candidate_sha256", "lease_sha256",
    "registry_snapshot_sha256", "agents_snapshot_sha256",
    "writer_evidence_sha256", "writer_source_sha256",
)
PROOF_FIELDS = {
    "schema_version", "proof_kind", "module_key", "maintainer_title",
    "agent_id", "run_id", "lease_id", "target_path", "owned_paths",
    "lease_path", "lease_sha256", "registry_snapshot_path",
    "registry_snapshot_sha256", "agents_snapshot_path",
    "agents_snapshot_sha256", "writer_evidence_path",
    "writer_evidence_sha256", "writer_source_path", "writer_source_sha256",
    "baseline_sha256", "code_version", "build_id", "candidate_sha256",
}


def validate_historical_project_record_write_proof(
    *, root: Path, proof_path: Path, proof_sha256: str,
    target: Path, module_key: str, maintainer_title: str, agent_id: str, run_id: str,
    lease_id: str, owned_paths: list[str], baseline_sha256: str,
    code_version: str, build_id: str, candidate_sha256: str,
) -> dict[str, Any]:
    """Validate a closed, same-user coordination proof without granting a write."""
    proof_file = _hashed_file(root, proof_path, proof_sha256, "historical-proof")
    proof = _strict_object(proof_file, PROOF_FIELDS, "invalid-historical-write-proof")
    if (type(proof.get("schema_version")) is not int or proof["schema_version"] != 1
            or proof.get("proof_kind") != "local-coordination-historical-project-record-write-proof"):
        raise RuntimeError("invalid-historical-write-proof")
    expected_outer = {
        "module_key": module_key, "maintainer_title": maintainer_title,
        "agent_id": agent_id, "run_id": run_id,
        "lease_id": lease_id, "target_path": target.as_posix(),
        "owned_paths": owned_paths, "baseline_sha256": baseline_sha256,
        "code_version": code_version, "build_id": build_id,
        "candidate_sha256": candidate_sha256,
    }
    if any(proof.get(key) != value for key, value in expected_outer.items()):
        raise RuntimeError("historical-write-proof-binding-mismatch")
    if not _valid_owned_paths(proof.get("owned_paths")):
        raise RuntimeError("invalid-historical-write-proof")
    for field in SHA256_FIELDS:
        value = proof.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError("invalid-historical-write-proof")

    agents_text, canonical_paths, canonical_title = _historical_ownership(
        root, proof, target, module_key, owned_paths)
    lease, writer_identity = _historical_lease(
        root, proof, target, module_key, canonical_title, agent_id, run_id,
        lease_id, owned_paths, agents_text)
    _historical_registry(
        root, proof, module_key, canonical_title, agent_id, run_id,
        canonical_paths, lease, writer_identity)

    resolved = {
        "writer_evidence_path": writer_identity["evidence_path"],
        "writer_evidence_sha256": writer_identity["evidence_sha256"],
        "writer_source_path": writer_identity["source_path"],
        "writer_source_sha256": writer_identity["source_sha256"],
    }
    if any(proof.get(key) != value for key, value in resolved.items()):
        raise RuntimeError("historical-writer-source-binding-mismatch")
    _hashed_file(root, Path(str(proof["writer_evidence_path"])), str(proof["writer_evidence_sha256"]), "writer-evidence")
    _hashed_file(root, Path(str(proof["writer_source_path"])), str(proof["writer_source_sha256"]), "writer-source")
    return {"policy": lease["writer_identity"].get("policy"), **writer_identity}


def _historical_ownership(
    root: Path, proof: dict[str, Any], target: Path, module_key: str,
    owned_paths: list[str],
) -> tuple[str, tuple[str, ...], str]:
    agents_file = _hashed_file(
        root, Path(str(proof["agents_snapshot_path"])),
        str(proof["agents_snapshot_sha256"]), "historical-agents-snapshot")
    agents_text = agents_file.read_text(encoding="utf-8")
    ownership = module_ownership_mapping(agents_text)
    if module_key not in ownership:
        raise RuntimeError("historical-owner-not-registered")
    canonical_paths, canonical_title = ownership[module_key]
    if (list(canonical_paths) != owned_paths or proof.get("maintainer_title") != canonical_title
            or not _target_is_owned(target, canonical_paths)):
        raise RuntimeError("historical-ownership-mismatch")
    return agents_text, canonical_paths, canonical_title


def _historical_lease(
    root: Path, proof: dict[str, Any], target: Path, module_key: str,
    canonical_title: str, agent_id: str, run_id: str, lease_id: str,
    owned_paths: list[str], agents_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lease_file = _hashed_file(
        root, Path(str(proof["lease_path"])), str(proof["lease_sha256"]), "historical-lease")
    lease = _strict_object(lease_file, set(LEASE_FIELDS), "invalid-historical-write-lease")
    writer_identity = _validate_lease_writer_identity(root, lease, agent_id, run_id)
    expected_lease: dict[str, Any] = {
        "schema_version": 1, "receipt_kind": "local-coordination-project-record-write-lease",
        "lease_id": lease_id, "module_key": module_key, "maintainer_title": canonical_title,
        "agent_id": agent_id, "run_id": run_id, "target_path": target.as_posix(),
        "owned_paths": owned_paths, "agents_path": "AGENTS.md",
        "agents_sha256": str(proof["agents_snapshot_sha256"]),
        "authority_matrix_path": REQUIRED_MACHINE_POLICY["authority_matrix_path"],
        "authority_matrix_sha256": _authority_matrix_sha256(agents_text),
        "lease_status": "closed", "writer_identity": lease.get("writer_identity"),
    }
    if lease != expected_lease:
        raise RuntimeError("invalid-historical-write-lease")
    return lease, writer_identity


def _historical_registry(
    root: Path, proof: dict[str, Any], module_key: str, canonical_title: str,
    agent_id: str, run_id: str, canonical_paths: tuple[str, ...],
    lease: dict[str, Any], writer_identity: dict[str, Any],
) -> None:
    registry_file = _hashed_file(
        root, Path(str(proof["registry_snapshot_path"])),
        str(proof["registry_snapshot_sha256"]), "historical-registry-snapshot")
    entry = _registered_writer(registry_file, module_key)
    active_lease = {**lease, "lease_status": "active"}
    _require_registered_writer(
        entry, module_key, canonical_title, agent_id, run_id,
        canonical_paths, active_lease, writer_identity)


def _hashed_file(root: Path, relative: Path, expected_sha256: str, label: str) -> Path:
    path = _bound_project_file(root, relative, label)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"{label}-sha256-drift")
    return path


def _strict_object(path: Path, fields: set[str], code: str) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError(code) from error
    if not isinstance(value, dict) or set(value) != fields:
        raise RuntimeError(code)
    for field in ("module_key", "agent_id", "run_id", "lease_id"):
        _canonical_identity(value.get(field), field.replace("_", "-"))
    return value
