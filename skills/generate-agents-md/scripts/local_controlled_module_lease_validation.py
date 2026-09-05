from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from local_controlled_data_safety import canonical_json, parse_utc, require
from local_controlled_file_safety import has_exact_path_spelling
from local_controlled_path_safety import (
    LocalControlledTrustError,
    canonical_directory,
    is_normalized_path,
    is_within,
    read_external_regular_file,
)
from strict_json import loads as strict_json_loads


TRUST_MODE = "local_controlled_same_user"
SECURITY_CAVEAT = "same_os_user_can_access_private_key_not_host_native_attestation"
DOMAIN = "generate-agents-md/local-controlled-module-write-lease/v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
IDENTITY_RE = re.compile(r"[A-Za-z0-9/][A-Za-z0-9/._:-]{1,255}")
ALLOWED_ACTIONS = {"write", "design", "implement", "write_module_artifacts"}
ENVELOPE_FIELDS = (
    "schema_version", "trust_mode", "payload_path", "payload_sha256",
    "signature_path", "signature_sha256", "public_key_path",
    "public_key_fingerprint_sha256",
)
SIGNATURE_FIELDS = (
    "algorithm", "canonicalization", "domain", "key_id",
    "payload_canonical_sha256", "signature_base64url",
)
LEASE_FIELDS = (
    "schema_version", "receipt_type", "trust_mode", "security_caveat",
    "explicit_user_authorization", "authorization_mode", "authorization_source",
    "issuer", "key_id", "key_fingerprint_sha256", "registry_path", "project_root",
    "module_key", "stable_title", "agent_handle", "run_id", "assigned_model",
    "assigned_reasoning_effort", "role", "authorized_actions", "owned_paths",
    "targets", "baseline_path", "baseline_sha256", "policy_sha256",
    "authority_matrix_sha256", "base_candidate_sha256", "post_candidate_sha256",
    "code_version", "build_id", "issued_at", "not_before", "expires_at",
    "ttl_seconds", "nonce", "receipt_id", "lease_id",
)
TARGET_FIELDS = ("path", "pre_sha256", "pre_size", "post_sha256", "post_size")


def validate_module_lease_envelope(
    *, envelope_path: Path, project_root: Path, trusted_public_key_path: Path,
    expected_public_key_fingerprint: str, expected_registry_path: Path,
    expected_module_key: str, expected_agent_handle: str, expected_run_id: str,
    expected_code_version: str, expected_build_id: str,
    now: datetime,
) -> dict[str, object]:
    root = canonical_directory(project_root, "project-root-mismatch")
    registry = canonical_external_state_path(expected_registry_path, root, "registry")
    envelope, public_key = _read_envelope(
        envelope_path, trusted_public_key_path, root,
        expected_public_key_fingerprint,
    )
    payload_bytes = _read_bound_artifact(envelope, "payload", root)
    signature_bytes = _read_bound_artifact(envelope, "signature", root)
    payload = _strict_object(payload_bytes, LEASE_FIELDS, "invalid-module-lease")
    signature = _strict_object(
        signature_bytes, SIGNATURE_FIELDS, "invalid-module-lease-signature",
    )
    canonical = canonical_json(payload)
    _validate_signature(signature, payload, canonical, public_key)
    _validate_lease_semantics(payload, root, registry, now)
    _validate_expected_identity(
        payload, expected_module_key, expected_agent_handle, expected_run_id,
        expected_code_version, expected_build_id,
    )
    return payload


def canonical_external_state_path(path: Path, root: Path, label: str) -> Path:
    code = f"unsafe-{label}-path"
    require(path.is_absolute() and is_normalized_path(str(path)), code)
    parent = canonical_directory(path.parent, code)
    require(not is_within(parent, root), code)
    try:
        value = os.lstat(path)
    except FileNotFoundError:
        return path
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    require(
        has_exact_path_spelling(path)
        and stat.S_ISREG(value.st_mode)
        and value.st_nlink == 1,
        code,
    )
    try:
        require(path.resolve(strict=True) == path, code)
    except (OSError, RuntimeError) as error:
        raise LocalControlledTrustError(code) from error
    return path


def canonical_relative_path(value: object, code: str) -> str:
    require(type(value) is str and value not in {"", "."}, code)
    path = Path(str(value))
    require(
        not path.is_absolute() and ".." not in path.parts
        and str(path) == value and "\x00" not in str(value),
        code,
    )
    return str(value)


def validate_project_relative_candidate(root: Path, value: str) -> Path:
    relative = canonical_relative_path(value, "invalid-module-lease")
    candidate = root / relative
    current = root
    for component in Path(relative).parts:
        next_path = current / component
        try:
            item = os.lstat(next_path)
        except FileNotFoundError:
            require(has_exact_path_spelling(current), "invalid-module-lease")
            return candidate
        except OSError as error:
            raise LocalControlledTrustError("invalid-module-lease") from error
        require(not stat.S_ISLNK(item.st_mode), "invalid-module-lease")
        current = next_path
    require(has_exact_path_spelling(candidate), "invalid-module-lease")
    try:
        require(candidate.resolve(strict=True) == candidate, "invalid-module-lease")
    except (OSError, RuntimeError) as error:
        raise LocalControlledTrustError("invalid-module-lease") from error
    return candidate


def _read_envelope(
    envelope_path: Path, public_path: Path, root: Path, expected_fingerprint: str,
) -> tuple[dict[str, object], Ed25519PublicKey]:
    _, envelope_bytes = read_external_regular_file(envelope_path, root, "module-lease-envelope")
    public_file, public_bytes = read_external_regular_file(public_path, root, "public-key")
    envelope = _strict_object(envelope_bytes, ENVELOPE_FIELDS, "invalid-module-lease-envelope")
    require(type(envelope.get("schema_version")) is int
            and envelope.get("schema_version") == 1, "invalid-module-lease-envelope")
    require(envelope.get("trust_mode") == TRUST_MODE, "invalid-module-lease-envelope")
    fingerprint = _sha(expected_fingerprint, "untrusted-public-key")
    require(envelope.get("public_key_path") == str(public_file), "untrusted-public-key")
    require(envelope.get("public_key_fingerprint_sha256") == fingerprint,
            "untrusted-public-key")
    key = _load_public_key(public_bytes)
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    require(hashlib.sha256(raw).hexdigest() == fingerprint, "untrusted-public-key")
    return envelope, key


def _read_bound_artifact(
    envelope: dict[str, object], name: str, root: Path,
) -> bytes:
    path_value = envelope.get(f"{name}_path")
    require(type(path_value) is str and Path(str(path_value)).is_absolute(),
            "invalid-module-lease-envelope")
    _, payload = read_external_regular_file(Path(str(path_value)), root, f"module-lease-{name}")
    require(hashlib.sha256(payload).hexdigest() == envelope.get(f"{name}_sha256"),
            f"{name}-sha256-drift")
    return payload


def _strict_object(payload: bytes, fields: Sequence[str], code: str) -> dict[str, object]:
    try:
        value = strict_json_loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise LocalControlledTrustError(code) from error
    require(isinstance(value, dict) and set(value) == set(fields), code)
    return value


def _validate_signature(
    signature: dict[str, object], payload: dict[str, object], canonical: bytes,
    public_key: Ed25519PublicKey,
) -> None:
    require(signature.get("algorithm") == "Ed25519", "invalid-module-lease-signature")
    require(signature.get("canonicalization") == "sorted-compact-json-v1",
            "invalid-module-lease-signature")
    require(signature.get("domain") == DOMAIN, "invalid-module-lease-signature")
    require(signature.get("key_id") == payload.get("key_id"),
            "invalid-module-lease-signature")
    require(signature.get("payload_canonical_sha256") == hashlib.sha256(canonical).hexdigest(),
            "invalid-module-lease-signature")
    _verify_ed25519(signature.get("signature_base64url"), public_key, canonical)


def _verify_ed25519(value: object, public_key: Ed25519PublicKey, canonical: bytes) -> None:
    require(type(value) is str and value, "invalid-module-lease-signature")
    try:
        encoded = str(value)
        raw = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
        )
        normalized = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        require(len(raw) == 64 and encoded == normalized, "invalid-module-lease-signature")
        public_key.verify(raw, DOMAIN.encode("utf-8") + b"\0" + canonical)
    except LocalControlledTrustError:
        raise
    except Exception as error:
        raise LocalControlledTrustError("invalid-module-lease-signature") from error


def _validate_lease_semantics(
    payload: dict[str, object], root: Path, registry: Path, now: datetime,
) -> None:
    require(type(payload.get("schema_version")) is int
            and payload.get("schema_version") == 1, "invalid-module-lease")
    fixed = {
        "receipt_type": "local_controlled_module_write_lease",
        "trust_mode": TRUST_MODE, "security_caveat": SECURITY_CAVEAT,
        "authorization_mode": "local-controlled-same-user",
        "assigned_model": "gpt-6-astra", "assigned_reasoning_effort": "medium",
    }
    require(all(payload.get(key) == value for key, value in fixed.items()),
            "invalid-module-lease")
    require(payload.get("explicit_user_authorization") is True, "invalid-module-lease")
    require(payload.get("project_root") == str(root), "project-root-mismatch")
    require(payload.get("registry_path") == str(registry), "registry-path-mismatch")
    require(payload.get("role") in {"implementation", "module-maintainer"},
            "invalid-module-lease")
    _validate_ids_and_hashes(payload)
    _validate_actions_paths_targets(payload, root)
    _validate_window(payload, now)


def _validate_ids_and_hashes(payload: dict[str, object]) -> None:
    for field in (
        "authorization_source", "issuer", "key_id", "module_key", "agent_handle",
        "run_id", "code_version", "build_id", "receipt_id", "lease_id",
    ):
        require(type(payload.get(field)) is str
                and IDENTITY_RE.fullmatch(str(payload[field])), "invalid-module-lease")
    title = payload.get("stable_title")
    require(type(title) is str and title == str(title).strip()
            and 1 <= len(str(title)) <= 256, "invalid-module-lease")
    for field in (
        "key_fingerprint_sha256", "baseline_sha256", "policy_sha256",
        "authority_matrix_sha256", "base_candidate_sha256", "post_candidate_sha256",
        "nonce",
    ):
        _sha(payload.get(field), "invalid-module-lease")


def _validate_actions_paths_targets(payload: dict[str, object], root: Path) -> None:
    actions = payload.get("authorized_actions")
    require(isinstance(actions, list) and actions
            and len(actions) == len(set(actions))
            and all(type(item) is str and item in ALLOWED_ACTIONS for item in actions),
            "invalid-module-lease")
    owned = payload.get("owned_paths")
    require(isinstance(owned, list) and owned and len(owned) == len(set(owned)),
            "invalid-module-lease")
    owned_values = [canonical_relative_path(item, "invalid-module-lease") for item in owned]
    for item in owned_values:
        validate_project_relative_candidate(root, item)
    targets = payload.get("targets")
    require(isinstance(targets, list) and targets, "invalid-module-lease")
    paths: set[str] = set()
    for target in targets:
        _validate_target(target, root, owned_values, paths)
    require(
        payload.get("base_candidate_sha256") == _target_candidate(targets, "pre")
        and payload.get("post_candidate_sha256") == _target_candidate(targets, "post"),
        "candidate-binding-mismatch",
    )
    canonical_relative_path(payload.get("baseline_path"), "invalid-module-lease")


def _target_candidate(targets: list[object], prefix: str) -> str:
    snapshot = []
    for target in targets:
        assert isinstance(target, dict)
        snapshot.append({
            "path": target["path"],
            "sha256": target[f"{prefix}_sha256"],
            "size": target[f"{prefix}_size"],
        })
    return hashlib.sha256(canonical_json({"targets": snapshot})).hexdigest()


def _validate_target(
    target: object, root: Path, owned: list[str], paths: set[str],
) -> None:
    require(isinstance(target, dict) and set(target) == set(TARGET_FIELDS),
            "invalid-module-lease")
    path = canonical_relative_path(target.get("path"), "invalid-module-lease")
    require(path not in paths and any(
        path == item or Path(path).is_relative_to(Path(item)) for item in owned
    ), "invalid-module-lease")
    paths.add(path)
    candidate = validate_project_relative_candidate(root, path)
    require(candidate.is_file() and not candidate.is_symlink(), "invalid-module-lease")
    for field in ("pre_sha256", "post_sha256"):
        _sha(target.get(field), "invalid-module-lease")
    for field in ("pre_size", "post_size"):
        require(type(target.get(field)) is int and int(target[field]) >= 0,
                "invalid-module-lease")


def _validate_window(payload: dict[str, object], now: datetime) -> None:
    issued = parse_utc(str(payload.get("issued_at")), "invalid-module-lease")
    start = parse_utc(str(payload.get("not_before")), "invalid-module-lease")
    expires = parse_utc(str(payload.get("expires_at")), "invalid-module-lease")
    ttl = payload.get("ttl_seconds")
    require(type(ttl) is int and 60 <= int(ttl) <= 900, "invalid-module-lease")
    require(issued <= start < expires
            and int((expires - start).total_seconds()) == ttl, "invalid-module-lease")
    current = now.astimezone(timezone.utc)
    require(current >= start, "lease-not-yet-valid")
    require(current < expires, "lease-expired")


def _validate_expected_identity(
    payload: dict[str, object], module: str, agent: str, run: str,
    code_version: str, build_id: str,
) -> None:
    require(payload.get("module_key") == module, "module-binding-mismatch")
    require(payload.get("agent_handle") == agent, "agent-binding-mismatch")
    require(payload.get("run_id") == run, "run-binding-mismatch")
    require(payload.get("code_version") == code_version, "code-version-mismatch")
    require(payload.get("build_id") == build_id, "build-id-mismatch")


def _load_public_key(payload: bytes) -> Ed25519PublicKey:
    try:
        value = serialization.load_pem_public_key(payload)
    except Exception as error:
        raise LocalControlledTrustError("ed25519-verifier-unavailable") from error
    require(isinstance(value, Ed25519PublicKey), "untrusted-public-key")
    return value


def _sha(value: object, code: str) -> str:
    require(type(value) is str and SHA256_RE.fullmatch(str(value)), code)
    return str(value)


def activate_signed_module_lease(
    payload: dict[str, object], registry_path: Path, now: datetime,
) -> dict[str, object]:
    require(payload.get("registry_path") == str(registry_path), "registry-path-mismatch")
    return ModuleLeaseRegistry(registry_path, Path(str(payload["project_root"]))).activate(payload, now)


def apply_signed_module_write(
    payload: dict[str, object], registry_path: Path, target_path: Path,
    replacement_path: Path, action: str, now: datetime,
) -> dict[str, object]:
    require(payload.get("registry_path") == str(registry_path), "registry-path-mismatch")
    from local_controlled_guarded_write import apply_module_write

    return apply_module_write(payload, registry_path, target_path, replacement_path, action, now)


from local_controlled_module_lease_registry import ModuleLeaseRegistry
