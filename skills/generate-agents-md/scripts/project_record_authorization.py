from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents_dispatcher_policy_validation import (
    module_ownership_mapping,
    validate_dispatcher_ownership_policy,
)
from agents_policy_common import REQUIRED_MACHINE_POLICY
from agents_authority_matrix_validation import validate_authority_matrix
from codex_native_writer_identity import (
    POLICY as CODEX_NATIVE_SOL_POLICY,
    validate_writer_identity as validate_codex_native_writer_identity,
)
from local_qwen_writer_identity import (
    SUPPORTED_ENDPOINT,
    SUPPORTED_MODELS,
    SUPPORTED_PROVIDER,
    SUPPORTED_RUNTIME,
    validate_writer_identity,
)
from strict_json import loads as strict_json_loads


LEASE_FIELDS = (
    "schema_version", "receipt_kind", "lease_id", "module_key",
    "maintainer_title", "agent_id", "run_id", "target_path", "owned_paths",
    "agents_path", "agents_sha256", "authority_matrix_path",
    "authority_matrix_sha256", "lease_status", "writer_identity",
)
WRITER_REGISTRY_PATH = Path("docs/governance/module-writer-registry.json")
WRITER_REGISTRY_FIELDS = {"schema_version", "registry_kind", "active_leases"}
WRITER_ENTRY_FIELDS = {
    "module_key", "maintainer_title", "agent_id", "run_id", "lease_id",
    "role", "owned_paths", "lease_status", "writer_identity",
}
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,127}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
DELIVERY_FIRST_MODE = "delivery-first-local-coordination"
STRICT_SECURITY_MODE = "strict-security"
AUTHORIZATION_MODES = (DELIVERY_FIRST_MODE, STRICT_SECURITY_MODE)


@dataclass(frozen=True)
class AuthorizationBinding:
    agents_path: Path
    agents_sha256: str
    lease_path: Path
    lease_sha256: str
    registry_path: Path
    registry_sha256: str
    writer_evidence_path: Path
    writer_evidence_sha256: str
    writer_source_path: Path
    writer_source_sha256: str
    writer_profile: dict[str, Any]


def authorize_project_record_write(
    *, root: Path, target: Path, module_key: str, agent_id: str, run_id: str,
    agents_path: Path, lease_path: Path, lease_sha256: str,
    authorization_mode: str,
) -> AuthorizationBinding:
    module, agent, run = _canonical_authorization_identity(
        authorization_mode, module_key, agent_id, run_id, agents_path,
    )
    if authorization_mode == STRICT_SECURITY_MODE:
        raise RuntimeError("strict-native-writer-unsupported")
    agents_file = _bound_project_file(root, agents_path, "agents")
    agents_payload = agents_file.read_bytes()
    agents_sha256 = hashlib.sha256(agents_payload).hexdigest()
    agents_text = agents_payload.decode("utf-8")
    authority_sha256 = _authority_matrix_sha256(agents_text)
    if any(issue.severity == "error" for issue in validate_dispatcher_ownership_policy(
        agents_text, mode="project")):
        raise RuntimeError("canonical-ownership-invalid")
    lease_file = _bound_project_file(root, lease_path, "lease")
    actual_lease_sha = hashlib.sha256(lease_file.read_bytes()).hexdigest()
    if not SHA256_RE.fullmatch(lease_sha256.casefold()) or actual_lease_sha != lease_sha256.casefold():
        raise RuntimeError("lease-sha256-drift")
    value = _strict_lease(lease_file)
    if value.get("agents_sha256") != agents_sha256:
        raise RuntimeError("ownership-or-agents-drift")
    ownership = module_ownership_mapping(agents_text)
    if module not in ownership:
        raise RuntimeError("module-owner-not-registered")
    owned_paths, maintainer_title = ownership[module]
    writer_identity = _validate_lease_writer_identity(root, value, agent, run)
    if not _target_is_owned(target, owned_paths):
        raise RuntimeError("module-ownership-mismatch")
    registry_sha256 = _validate_registered_writer(
        root, module, maintainer_title, agent, run, owned_paths, value, writer_identity)
    expected = _expected_lease(value, module, maintainer_title, agent, run, target,
                               owned_paths, agents_sha256, authority_sha256)
    if value != expected:
        if value.get("owned_paths") != list(owned_paths):
            raise RuntimeError("ownership-or-agents-drift")
        raise RuntimeError("invalid-record-write-lease")
    return AuthorizationBinding(
        agents_path, agents_sha256, lease_path, actual_lease_sha,
        WRITER_REGISTRY_PATH, registry_sha256,
        Path(writer_identity["evidence_path"]),
        writer_identity["evidence_sha256"],
        Path(writer_identity["source_path"]),
        writer_identity["source_sha256"],
        {"policy": value["writer_identity"].get("policy"), **writer_identity},
    )


def require_codex_native_sol_writer_profile(profile: dict[str, Any]) -> None:
    expected = {
        "policy": CODEX_NATIVE_SOL_POLICY,
        "provider": "codex-native-agent",
        "requested_model": "gpt-5.6-sol",
        "recorded_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "medium",
        "recorded_reasoning_effort": "medium",
    }
    if any(profile.get(key) != value for key, value in expected.items()):
        raise RuntimeError("writer-profile-mismatch")


def writer_runtime_expectation(profile: dict[str, Any]) -> dict[str, str]:
    policy = profile.get("policy")
    if policy == CODEX_NATIVE_SOL_POLICY:
        require_codex_native_sol_writer_profile(profile)
        return {
            "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol", "requested_reasoning_effort": "medium",
            "recorded_reasoning_effort": "medium",
        }
    if policy != "local-qwen-writer-v1":
        raise RuntimeError("unsupported-writer-policy")
    requested_model = profile.get("requested_model")
    requested_effort = profile.get("requested_reasoning_effort", "none")
    if (requested_model not in SUPPORTED_MODELS
            or requested_effort not in {"none", "xhigh"}
            or profile.get("provider") != SUPPORTED_PROVIDER
            or profile.get("runtime_kind") != SUPPORTED_RUNTIME
            or profile.get("endpoint") != SUPPORTED_ENDPOINT
            or profile.get("reported_model") != requested_model
            or profile.get("reported_reasoning_effort", "none") != requested_effort):
        raise RuntimeError("writer-profile-mismatch")
    return {
        "provider": SUPPORTED_PROVIDER,
        "requested_model": requested_model,
        "recorded_model": requested_model,
        "requested_reasoning_effort": requested_effort,
        "recorded_reasoning_effort": requested_effort,
    }


def _canonical_authorization_identity(
    mode: str, module_key: str, agent_id: str, run_id: str, agents_path: Path,
) -> tuple[str, str, str]:
    if mode not in AUTHORIZATION_MODES:
        raise RuntimeError("invalid-authorization-mode")
    module = _canonical_identity(module_key, "module-key").casefold()
    if module_key != module:
        raise RuntimeError("module-key-not-canonical")
    if agents_path != Path("AGENTS.md"):
        raise RuntimeError("agents-path-not-canonical")
    return module, _canonical_identity(agent_id, "agent-id"), _canonical_identity(run_id, "run-id")


def _validate_registered_writer(
    root: Path, module: str, title: str, agent: str, run: str,
    owned_paths: tuple[str, ...], lease: dict[str, Any],
    writer_identity: dict[str, Any],
) -> str:
    registry = _bound_project_file(root, WRITER_REGISTRY_PATH, "module-writer-registry")
    digest = hashlib.sha256(registry.read_bytes()).hexdigest()
    _require_registered_writer(
        _registered_writer(registry, module), module, title, agent, run, owned_paths, lease,
        writer_identity,
    )
    return digest


def _validate_lease_writer_identity(
    root: Path, lease: dict[str, Any], agent: str, run: str,
) -> dict[str, Any]:
    if not isinstance(lease.get("writer_identity"), dict):
        raise RuntimeError("missing-writer-identity")
    persisted = lease["writer_identity"]
    policy = persisted.get("policy")
    if policy == CODEX_NATIVE_SOL_POLICY:
        branch = {key: value for key, value in persisted.items() if key != "policy"}
        return validate_codex_native_writer_identity(root, branch, agent, run)
    if policy != "local-qwen-writer-v1":
        raise RuntimeError("unsupported-writer-policy")
    branch = {key: value for key, value in persisted.items() if key != "policy"}
    identity = validate_writer_identity(root, branch, agent, run)
    if (identity["provider"] != SUPPORTED_PROVIDER
            or identity["runtime_kind"] != SUPPORTED_RUNTIME
            or identity["endpoint"] != SUPPORTED_ENDPOINT):
        raise RuntimeError("forbidden-writer-provenance")
    if (identity["requested_model"] not in SUPPORTED_MODELS
            or identity["reported_model"] != identity["requested_model"]):
        raise RuntimeError("forbidden-writer-provenance")
    return identity


def binding_is_current(root: Path, binding: AuthorizationBinding) -> bool:
    return (
        _current_sha(root, binding.agents_path) == binding.agents_sha256
        and _current_sha(root, binding.lease_path) == binding.lease_sha256
        and _current_sha(root, binding.registry_path) == binding.registry_sha256
        and _current_sha(root, binding.writer_evidence_path)
        == binding.writer_evidence_sha256
        and _current_sha(root, binding.writer_source_path)
        == binding.writer_source_sha256
    )


def _registered_writer(path: Path, module: str) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError("invalid-module-writer-registry") from error
    if (not isinstance(value, dict) or set(value) != WRITER_REGISTRY_FIELDS
            or value.get("schema_version") != 1
            or value.get("registry_kind") != "local-coordination-module-writer-registry"
            or not isinstance(value.get("active_leases"), list)):
        raise RuntimeError("invalid-module-writer-registry")
    entries = value["active_leases"]
    _validate_writer_entries(entries)
    matches = [entry for entry in entries if entry.get("module_key") == module]
    if len(matches) != 1:
        raise RuntimeError("canonical-writer-not-unique")
    return matches[0]


def _validate_writer_entries(entries: list[object]) -> None:
    seen: dict[str, set[str]] = {
        "module_key": set(), "agent_id": set(), "run_id": set(), "lease_id": set(),
    }
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != WRITER_ENTRY_FIELDS:
            raise RuntimeError("invalid-module-writer-registry")
        if (entry.get("role") != "module-maintainer" or entry.get("lease_status") != "active"
                or not isinstance(entry.get("maintainer_title"), str)
                or not str(entry["maintainer_title"]).strip()
                or not _valid_owned_paths(entry.get("owned_paths"))
                or not isinstance(entry.get("writer_identity"), dict)):
            raise RuntimeError("invalid-module-writer-registry")
        for field in seen:
            identity = _canonical_identity(entry.get(field), field.replace("_", "-"))
            if field == "module_key" and identity != identity.casefold():
                raise RuntimeError("invalid-module-writer-registry")
            if identity in seen[field]:
                raise RuntimeError("duplicate-registry-identity")
            seen[field].add(identity)
    if len(entries) != 1:
        raise RuntimeError("canonical-writer-not-unique")


def _valid_owned_paths(value: object) -> bool:
    return bool(
        isinstance(value, list) and value
        and all(isinstance(path, str) and path and path == Path(path).as_posix()
                and not Path(path).is_absolute() and ".." not in Path(path).parts for path in value)
        and len(set(value)) == len(value)
    )


def _require_registered_writer(
    entry: dict[str, Any], module: str, title: str, agent: str, run: str,
    owned_paths: tuple[str, ...], lease: dict[str, Any],
    writer_identity: dict[str, Any],
) -> None:
    # The registry entry is a persisted identity closed-set (module/agent/run/
    # lease/paths + the original identity *reference* block). The resolved
    # writer_identity returned by validate_writer_identity carries normalized
    # resolved-source bindings (invocation_id/source_path/source_sha256) and
    # must NOT be compared for equality against the registry's identity block.
    # Identity fields are compared explicitly; source-hash re-validation is
    # still enforced by validate_writer_identity before this check.
    if (entry.get("module_key") != module
            or entry.get("maintainer_title") != title
            or entry.get("agent_id") != agent
            or entry.get("run_id") != run
            or entry.get("lease_id") != lease.get("lease_id")
            or entry.get("role") != "module-maintainer"
            or entry.get("owned_paths") != list(owned_paths)
            or entry.get("lease_status") != "active"):
        raise RuntimeError("registered-writer-binding-mismatch")
    registered_identity = entry.get("writer_identity")
    if (not isinstance(registered_identity, dict)
            or registered_identity != lease.get("writer_identity")):
        raise RuntimeError("registered-writer-binding-mismatch")


def _authority_matrix_sha256(agents_text: str) -> str:
    if any(issue.severity == "error" for issue in validate_authority_matrix(agents_text)):
        raise RuntimeError("canonical-authority-matrix-invalid")
    match = re.search(
        r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$", agents_text, re.MULTILINE,
    )
    if match is None:
        raise RuntimeError("canonical-authority-matrix-invalid")
    return match.group(1)


def _canonical_identity(value: object, label: str) -> str:
    if type(value) is not str:
        raise RuntimeError("invalid-writer-identity")
    if not IDENTITY_RE.fullmatch(value):
        raise RuntimeError(f"invalid-{label}")
    return value


def _bound_project_file(root: Path, relative: Path, label: str) -> Path:
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != str(relative):
        raise RuntimeError(
            "invalid-record-write-lease" if label == "lease" else f"unsafe-{label}-path"
        )
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"unsafe-{label}-path")
    try:
        stat = os.stat(current, follow_symlinks=False)
    except FileNotFoundError as error:
        raise RuntimeError(f"missing-{label}") from error
    if not current.is_file() or stat.st_nlink != 1:
        raise RuntimeError(f"unsafe-{label}-path")
    return current


def _target_is_owned(target: Path, owned_paths: tuple[str, ...]) -> bool:
    target_parts = target.parts
    return any(
        target_parts[:len(Path(path).parts)] == Path(path).parts
        for path in owned_paths
    )


def _strict_lease(path: Path) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError("invalid-record-write-lease") from error
    if not isinstance(value, dict) or set(value) != set(LEASE_FIELDS):
        raise RuntimeError("invalid-record-write-lease")
    if not isinstance(value.get("writer_identity"), dict):
        raise RuntimeError("missing-writer-identity")
    return value


def _expected_lease(
    value: dict[str, Any], module: str, title: str, agent: str, run: str,
    target: Path, owned_paths: tuple[str, ...], agents_sha256: str,
    authority_sha256: str,
) -> dict[str, Any]:
    lease_id = value.get("lease_id")
    if type(lease_id) is not str or not IDENTITY_RE.fullmatch(lease_id):
        raise RuntimeError("invalid-record-write-lease")
    if set(value) != set(LEASE_FIELDS):
        raise RuntimeError("invalid-record-write-lease")
    return {
        "schema_version": 1,
        "receipt_kind": "local-coordination-project-record-write-lease",
        "lease_id": lease_id,
        "module_key": module,
        "maintainer_title": title,
        "agent_id": agent,
        "run_id": run,
        "target_path": target.as_posix(),
        "owned_paths": list(owned_paths),
        "agents_path": "AGENTS.md",
        "agents_sha256": agents_sha256,
        "authority_matrix_path": REQUIRED_MACHINE_POLICY["authority_matrix_path"],
        "authority_matrix_sha256": authority_sha256,
        "lease_status": "active",
        "writer_identity": value["writer_identity"],
    }


def _current_sha(root: Path, relative: Path) -> str | None:
    try:
        path = _bound_project_file(root, relative, "authorization-binding")
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except RuntimeError:
        return None
