from __future__ import annotations

import hashlib
import json
from pathlib import Path

from test_update_project_record import (
    qwen_evidence_bytes, qwen_writer_identity, sol_writer_identity,
    synthetic_rollout_bytes,
)


AUTHORITY_SHA = "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643"


def write_historical_sol_write_proof(
    root: Path, *, module_key: str, maintainer_title: str, owned_paths: list[str],
    agent_id: str, run_id: str, lease_id: str, target_path: str,
    baseline_sha256: str, code_version: str, build_id: str, candidate_sha256: str,
    prefix: str = "implementation",
) -> dict[str, str]:
    identity = sol_writer_identity(root, agent_id, run_id, prefix=prefix)
    agents_payload = (root / "AGENTS.md").read_bytes()
    agents_sha = hashlib.sha256(agents_payload).hexdigest()
    history = root / "docs/governance/history" / prefix
    history.mkdir(parents=True, exist_ok=True)
    agents_relative = f"docs/governance/history/{prefix}/AGENTS.md"
    (root / agents_relative).write_bytes(agents_payload)
    lease_relative = f"docs/governance/history/{prefix}/lease.json"
    lease = {
        "schema_version": 1,
        "receipt_kind": "local-coordination-project-record-write-lease",
        "lease_id": lease_id, "module_key": module_key,
        "maintainer_title": maintainer_title,
        "agent_id": agent_id, "run_id": run_id,
        "target_path": target_path, "owned_paths": owned_paths,
        "agents_path": "AGENTS.md", "agents_sha256": agents_sha,
        "authority_matrix_path": "AGENTS.md#machine-enforced-authority-matrix",
        "authority_matrix_sha256": AUTHORITY_SHA,
        "lease_status": "closed", "writer_identity": identity,
    }
    lease_sha = _write_json(root / lease_relative, lease)
    registry_relative = f"docs/governance/history/{prefix}/registry.json"
    registry_sha = _write_json(root / registry_relative, {
        "schema_version": 1,
        "registry_kind": "local-coordination-module-writer-registry",
        "active_leases": [{
            "module_key": module_key, "maintainer_title": maintainer_title,
            "agent_id": agent_id, "run_id": run_id, "lease_id": lease_id,
            "role": "module-maintainer", "owned_paths": owned_paths,
            "lease_status": "active", "writer_identity": identity,
        }],
    })
    evidence = json.loads((root / str(identity["evidence_path"])).read_text(encoding="utf-8"))
    proof_relative = f"docs/governance/history/{prefix}/proof.json"
    proof = {
        "schema_version": 1,
        "proof_kind": "local-coordination-historical-project-record-write-proof",
        "module_key": module_key, "maintainer_title": maintainer_title,
        "agent_id": agent_id, "run_id": run_id, "lease_id": lease_id,
        "target_path": target_path, "owned_paths": owned_paths,
        "lease_path": lease_relative, "lease_sha256": lease_sha,
        "registry_snapshot_path": registry_relative,
        "registry_snapshot_sha256": registry_sha,
        "agents_snapshot_path": agents_relative,
        "agents_snapshot_sha256": agents_sha,
        "writer_evidence_path": identity["evidence_path"],
        "writer_evidence_sha256": identity["evidence_sha256"],
        "writer_source_path": evidence["source_path"],
        "writer_source_sha256": evidence["source_sha256"],
        "baseline_sha256": baseline_sha256, "code_version": code_version,
        "build_id": build_id, "candidate_sha256": candidate_sha256,
    }
    proof_sha = _write_json(root / proof_relative, proof)
    return {
        "lease_id": lease_id, "target_path": target_path,
        "path": proof_relative, "sha256": proof_sha,
    }


def write_historical_qwen_write_proof(
    root: Path, *, module_key: str, maintainer_title: str, owned_paths: list[str],
    agent_id: str, run_id: str, lease_id: str, target_path: str,
    baseline_sha256: str, code_version: str, build_id: str, candidate_sha256: str,
    prefix: str = "implementation-qwen", model: str = "qwen3.8:27b-q8_0",
    effort: str = "xhigh",
) -> dict[str, str]:
    descriptor = write_historical_sol_write_proof(
        root, module_key=module_key, maintainer_title=maintainer_title,
        owned_paths=owned_paths, agent_id=agent_id, run_id=run_id,
        lease_id=lease_id, target_path=target_path,
        baseline_sha256=baseline_sha256, code_version=code_version,
        build_id=build_id, candidate_sha256=candidate_sha256, prefix=prefix,
    )
    source = synthetic_rollout_bytes(session_id=run_id, model=model, effort=effort)
    source_path = root / "docs/governance/qwen-synthetic-rollout.jsonl"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(source)
    evidence = json.loads(qwen_evidence_bytes(agent_id, run_id, model=model, source=source))
    evidence.update({
        "requested_reasoning_effort": effort,
        "reported_reasoning_effort": effort,
    })
    evidence_payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    evidence_path = root / "docs/governance/qwen-invocation-evidence.json"
    evidence_path.write_bytes(evidence_payload)
    identity = qwen_writer_identity(
        agent_id, run_id, evidence=evidence_payload, source=source, model=model,
    )
    identity.update({
        "requested_reasoning_effort": effort,
        "reported_reasoning_effort": effort,
    })
    proof_path = root / descriptor["path"]
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    lease_path = root / proof["lease_path"]
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["writer_identity"] = identity
    proof["lease_sha256"] = _write_json(lease_path, lease)
    registry_path = root / proof["registry_snapshot_path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["active_leases"][0]["writer_identity"] = identity
    proof["registry_snapshot_sha256"] = _write_json(registry_path, registry)
    proof.update({
        "writer_evidence_path": identity["evidence_path"],
        "writer_evidence_sha256": identity["evidence_sha256"],
        "writer_source_path": evidence["source_path"],
        "writer_source_sha256": evidence["source_sha256"],
    })
    descriptor["sha256"] = _write_json(proof_path, proof)
    return descriptor


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()
