from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from local_controlled_data_safety import ReplayGuard, canonical_json, parse_utc, require
from local_controlled_file_safety import atomic_replace_text, directory_identity
from local_controlled_module_lease_validation import validate_project_relative_candidate
from local_controlled_path_safety import (
    FileIdentity,
    LocalControlledTrustError,
    canonical_directory,
    is_within,
    read_bound_regular_file,
    read_external_regular_file,
)
from strict_json import loads as strict_json_loads


DOMAIN = "generate-agents-md/system-governance-bootstrap/v2"
TRUST_MODE = "local_controlled_same_user"
SECURITY_CAVEAT = "same_os_user_can_access_private_key_not_host_native_attestation"
TARGET_PATHS = ("AGENTS.md", "docs/agents/module-agent-governance.md")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
IDENTITY_RE = re.compile(r"[A-Za-z0-9/][A-Za-z0-9/._:-]{1,255}")
AUTHORITY_RE = re.compile(r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$", re.MULTILINE)
ENVELOPE_FIELDS = (
    "schema_version", "trust_mode", "payload_path", "payload_sha256",
    "signature_path", "signature_sha256", "public_key_path",
    "public_key_fingerprint_sha256",
)
SIGNATURE_FIELDS = (
    "algorithm", "canonicalization", "domain", "key_id",
    "payload_canonical_sha256", "signature_base64url",
)
PAYLOAD_FIELDS = (
    "schema_version", "receipt_type", "trust_mode", "security_caveat",
    "explicit_user_authorization", "authorization_source", "issuer", "key_id",
    "key_fingerprint_sha256", "agent_handle", "assigned_model",
    "assigned_reasoning_effort", "role", "project_root", "replay_state_path",
    "module_registration", "governance_targets", "issued_at", "not_before",
    "expires_at", "nonce", "receipt_id", "operation_id", "one_time",
    "baseline_sha256", "pre_policy_sha256", "post_policy_sha256",
    "pre_authority_matrix_sha256", "post_authority_matrix_sha256",
    "bootstrap_candidate_sha256", "next_authority",
)
TARGET_FIELDS = ("path", "pre_sha256", "pre_size", "post_sha256", "post_size")
MODULE_FIELDS = ("module_key", "stable_title", "owned_paths")


def validate_bootstrap_v2_envelope(
    *, envelope_path: Path, project_root: Path, trusted_public_key_path: Path,
    expected_public_key_fingerprint: str, expected_agent_handle: str,
    expected_baseline_sha256: str, now: datetime, replay_guard: ReplayGuard,
) -> dict[str, object]:
    root = canonical_directory(project_root, "project-root-mismatch")
    public_file, public_bytes = read_external_regular_file(
        trusted_public_key_path, root, "public-key",
    )
    _, envelope_bytes = read_external_regular_file(envelope_path, root, "envelope")
    envelope = _strict_object(envelope_bytes, ENVELOPE_FIELDS, "invalid-local-envelope")
    require(type(envelope.get("schema_version")) is int
            and envelope.get("schema_version") == 1
            and envelope.get("trust_mode") == TRUST_MODE, "invalid-local-envelope")
    fingerprint = _sha(expected_public_key_fingerprint, "untrusted-public-key")
    require(envelope.get("public_key_path") == str(public_file)
            and envelope.get("public_key_fingerprint_sha256") == fingerprint,
            "untrusted-public-key")
    public_key = _load_key(public_bytes)
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    require(hashlib.sha256(raw).hexdigest() == fingerprint, "untrusted-public-key")
    payload_bytes = _read_artifact(envelope, "payload", root)
    signature_bytes = _read_artifact(envelope, "signature", root)
    payload = _strict_object(payload_bytes, PAYLOAD_FIELDS, "invalid-bootstrap-v2")
    signature = _strict_object(
        signature_bytes, SIGNATURE_FIELDS, "invalid-bootstrap-v2-signature",
    )
    canonical = canonical_json(payload)
    _validate_signature(signature, payload, canonical, public_key)
    _validate_semantics(
        payload, root, fingerprint, expected_agent_handle,
        expected_baseline_sha256, now, replay_guard,
    )
    expires = parse_utc(str(payload["expires_at"]), "invalid-bootstrap-v2")
    require(replay_guard.consume(
        str(payload["receipt_id"]), str(payload["nonce"]), expires,
    ), "replayed-receipt")
    return payload


def apply_bootstrap_v2(
    payload: dict[str, object], replacements: Mapping[str, Path],
) -> dict[str, object]:
    require(set(replacements) == set(TARGET_PATHS), "invalid-bootstrap-replacements")
    root = canonical_directory(Path(str(payload["project_root"])), "project-root-mismatch")
    targets = _target_map(payload)
    prepared: dict[str, tuple[str, bytes]] = {}
    frozen: dict[str, tuple[FileIdentity, tuple[int, int]]] = {}
    for relative in TARGET_PATHS:
        target_path = root / relative
        current, identity = read_bound_regular_file(target_path, "unsafe-governance-target")
        _verify_bytes(current, targets[relative], "pre")
        _, replacement = read_external_regular_file(
            replacements[relative], root, "governance-replacement",
        )
        _verify_bytes(replacement, targets[relative], "post")
        try:
            prepared[relative] = replacement.decode("utf-8"), replacement
        except UnicodeError as error:
            raise LocalControlledTrustError("invalid-governance-replacement") from error
        frozen[relative] = identity, directory_identity(target_path.parent)
    _validate_post_agents(payload, prepared["AGENTS.md"][1])
    applied = 0
    for relative in TARGET_PATHS:
        target_path = root / relative
        identity, parent_identity = frozen[relative]
        try:
            _verify_transition_state(root, targets, applied)
            _replace_one(
                target_path, prepared[relative][0], identity, parent_identity,
            )
            stored, _ = read_bound_regular_file(target_path, "unsafe-governance-target")
            _verify_bytes(stored, targets[relative], "post")
            applied += 1
        except LocalControlledTrustError as error:
            if applied:
                return {
                    "status": "PARTIAL", "complete": False,
                    "error": str(error), "applied_targets": applied,
                }
            raise
        except OSError as error:
            if applied:
                return {
                    "status": "PARTIAL", "complete": False,
                    "error": "target-persistence-failed", "applied_targets": applied,
                }
            raise LocalControlledTrustError("target-persistence-failed") from error
    _verify_transition_state(root, targets, len(TARGET_PATHS))
    return {"status": "APPLIED", "complete": True}


def _validate_semantics(
    payload: dict[str, object], root: Path, fingerprint: str,
    expected_agent: str, expected_baseline: str, now: datetime,
    replay_guard: ReplayGuard,
) -> None:
    fixed = {
        "schema_version": 2, "receipt_type": "system_governance_bootstrap_v2",
        "trust_mode": TRUST_MODE, "security_caveat": SECURITY_CAVEAT,
        "assigned_model": "gpt-6-astra", "assigned_reasoning_effort": "medium",
        "next_authority": "local-controlled-module-write-lease-required",
    }
    require(all(payload.get(key) == value for key, value in fixed.items()),
            "invalid-bootstrap-v2")
    require(payload.get("explicit_user_authorization") is True
            and payload.get("one_time") is True
            and payload.get("role") in {"implementation", "module-maintainer"},
            "invalid-bootstrap-v2")
    require(payload.get("project_root") == str(root), "project-root-mismatch")
    require(payload.get("replay_state_path") == str(replay_guard.state_path),
            "replay-state-mismatch")
    require(payload.get("key_fingerprint_sha256") == fingerprint, "untrusted-public-key")
    require(payload.get("agent_handle") == expected_agent, "agent-binding-mismatch")
    require(payload.get("baseline_sha256") == _sha(expected_baseline, "baseline-drift"),
            "baseline-drift")
    for field in (
        "authorization_source", "issuer", "key_id", "agent_handle",
        "receipt_id", "operation_id",
    ):
        require(type(payload.get(field)) is str
                and IDENTITY_RE.fullmatch(str(payload[field])), "invalid-bootstrap-v2")
    for field in (
        "key_fingerprint_sha256", "nonce", "baseline_sha256",
        "pre_policy_sha256", "post_policy_sha256",
        "pre_authority_matrix_sha256", "post_authority_matrix_sha256",
        "bootstrap_candidate_sha256",
    ):
        _sha(payload.get(field), "invalid-bootstrap-v2")
    _validate_window(payload, now)
    targets = _validate_targets(payload, root)
    agents_bytes, _ = read_bound_regular_file(root / "AGENTS.md", "unsafe-governance-target")
    require(hashlib.sha256(agents_bytes).hexdigest() == payload.get("pre_policy_sha256"),
            "pre-policy-drift")
    require(_authority_hash(agents_bytes) == payload.get("pre_authority_matrix_sha256"),
            "pre-authority-drift")
    candidate = hashlib.sha256(canonical_json({"governance_targets": list(targets.values())})).hexdigest()
    require(candidate == payload.get("bootstrap_candidate_sha256"), "candidate-drift")
    registration = payload.get("module_registration")
    require(isinstance(registration, dict) and set(registration) == set(MODULE_FIELDS),
            "invalid-bootstrap-v2")
    _validate_registration(registration, root, agents_bytes)


def _validate_targets(
    payload: dict[str, object], root: Path,
) -> dict[str, dict[str, object]]:
    values = payload.get("governance_targets")
    require(isinstance(values, list) and len(values) == 2, "invalid-bootstrap-v2")
    result: dict[str, dict[str, object]] = {}
    for value in values:
        require(isinstance(value, dict) and set(value) == set(TARGET_FIELDS),
                "invalid-bootstrap-v2")
        relative = value.get("path")
        require(type(relative) is str and relative in TARGET_PATHS
                and relative not in result, "invalid-bootstrap-v2")
        for field in ("pre_sha256", "post_sha256"):
            _sha(value.get(field), "invalid-bootstrap-v2")
        for field in ("pre_size", "post_size"):
            require(type(value.get(field)) is int and int(value[field]) > 0,
                    "invalid-bootstrap-v2")
        path = root / relative
        current, _ = read_bound_regular_file(path, "unsafe-governance-target")
        _verify_bytes(current, value, "pre")
        result[relative] = value
    require(set(result) == set(TARGET_PATHS), "invalid-bootstrap-v2")
    return result


def _validate_registration(
    registration: dict[str, object], root: Path, agents_bytes: bytes,
) -> None:
    require(registration.get("module_key") == "M11", "invalid-module-registration")
    title = registration.get("stable_title")
    require(type(title) is str and title == str(title).strip() and title,
            "invalid-module-registration")
    owned = registration.get("owned_paths")
    require(isinstance(owned, list) and owned and len(owned) == len(set(owned)),
            "invalid-module-registration")
    existing = _owned_paths(agents_bytes.decode("utf-8"))
    for item in owned:
        require(type(item) is str, "invalid-module-registration")
        validate_project_relative_candidate(root, item)
        require(all(not _paths_overlap(item, other) for other in existing),
                "owned-path-overlap")
    for index, left in enumerate(owned):
        require(all(not _paths_overlap(left, right) for right in owned[index + 1:]),
                "owned-path-overlap")


def _validate_post_agents(payload: dict[str, object], agents: bytes) -> None:
    require(hashlib.sha256(agents).hexdigest() == payload.get("post_policy_sha256"),
            "post-policy-drift")
    require(_authority_hash(agents) == payload.get("post_authority_matrix_sha256"),
            "post-authority-drift")
    registration = payload["module_registration"]
    assert isinstance(registration, dict)
    rows = _module_rows(agents.decode("utf-8"))
    matches = [row for row in rows if row[0] == registration["module_key"]]
    require(len(matches) == 1, "module-registration-drift")
    _, owned, title = matches[0]
    require(owned == registration["owned_paths"] and title == registration["stable_title"],
            "module-registration-drift")


def _validate_window(payload: dict[str, object], now: datetime) -> None:
    issued = parse_utc(str(payload.get("issued_at")), "invalid-bootstrap-v2")
    start = parse_utc(str(payload.get("not_before")), "invalid-bootstrap-v2")
    expires = parse_utc(str(payload.get("expires_at")), "invalid-bootstrap-v2")
    require(issued <= start < expires
            and (expires - start).total_seconds() <= 900,
            "invalid-bootstrap-v2")
    current = now.astimezone(timezone.utc)
    require(start <= current < expires, "bootstrap-v2-expired")


def _read_artifact(envelope: dict[str, object], name: str, root: Path) -> bytes:
    value = envelope.get(f"{name}_path")
    require(type(value) is str and Path(str(value)).is_absolute(), "invalid-local-envelope")
    _, payload = read_external_regular_file(Path(str(value)), root, name)
    require(hashlib.sha256(payload).hexdigest() == envelope.get(f"{name}_sha256"),
            f"{name}-sha256-drift")
    return payload


def _validate_signature(
    signature: dict[str, object], payload: dict[str, object], canonical: bytes,
    key: Ed25519PublicKey,
) -> None:
    require(signature.get("algorithm") == "Ed25519"
            and signature.get("canonicalization") == "sorted-compact-json-v1"
            and signature.get("domain") == DOMAIN
            and signature.get("key_id") == payload.get("key_id")
            and signature.get("payload_canonical_sha256") == hashlib.sha256(canonical).hexdigest(),
            "invalid-bootstrap-v2-signature")
    value = signature.get("signature_base64url")
    require(type(value) is str, "invalid-bootstrap-v2-signature")
    try:
        raw = base64.b64decode(str(value) + "=" * (-len(str(value)) % 4),
                               altchars=b"-_", validate=True)
        normalized = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        require(len(raw) == 64 and value == normalized, "invalid-bootstrap-v2-signature")
        key.verify(raw, DOMAIN.encode() + b"\0" + canonical)
    except LocalControlledTrustError:
        raise
    except Exception as error:
        raise LocalControlledTrustError("invalid-bootstrap-v2-signature") from error


def _load_key(payload: bytes) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(payload)
    except Exception as error:
        raise LocalControlledTrustError("ed25519-verifier-unavailable") from error
    require(isinstance(key, Ed25519PublicKey), "untrusted-public-key")
    return key


def _strict_object(payload: bytes, fields: Sequence[str], code: str) -> dict[str, object]:
    try:
        value = strict_json_loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise LocalControlledTrustError(code) from error
    require(isinstance(value, dict) and set(value) == set(fields), code)
    return value


def _target_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    values = payload["governance_targets"]
    assert isinstance(values, list)
    return {str(value["path"]): value for value in values if isinstance(value, dict)}


def _verify_bytes(payload: bytes, target: dict[str, object], prefix: str) -> None:
    require(len(payload) == target.get(f"{prefix}_size")
            and hashlib.sha256(payload).hexdigest() == target.get(f"{prefix}_sha256"),
            f"target-{prefix}-hash-drift")


def _replace_one(
    path: Path, replacement: str, expected: FileIdentity,
    parent_identity: tuple[int, int],
) -> None:
    def verify_parent() -> None:
        require(directory_identity(path.parent) == parent_identity,
                "unsafe-governance-target-parent")

    def verify_before() -> None:
        verify_parent()
        _, identity = read_bound_regular_file(path, "unsafe-governance-target")
        require(identity == expected, "unsafe-governance-target")

    try:
        atomic_replace_text(path, replacement, verify_parent, parent_identity, verify_before)
    except LocalControlledTrustError:
        raise
    except OSError as error:
        raise LocalControlledTrustError("target-persistence-failed") from error


def _verify_transition_state(
    root: Path, targets: dict[str, dict[str, object]], applied: int,
) -> None:
    for index, relative in enumerate(TARGET_PATHS):
        payload, _ = read_bound_regular_file(root / relative, "unsafe-governance-target")
        _verify_bytes(payload, targets[relative], "post" if index < applied else "pre")


def _authority_hash(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise LocalControlledTrustError("invalid-governance-target") from error
    matches = AUTHORITY_RE.findall(text)
    require(len(matches) == 1, "authority-matrix-drift")
    return matches[0]


def _module_rows(text: str) -> list[tuple[str, list[str], str]]:
    rows: list[tuple[str, list[str], str]] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not re.fullmatch(r"M[0-9]{2}", cells[0]):
            continue
        owned = re.findall(r"`([^`]+)`", cells[2])
        require(owned, "invalid-module-ownership")
        rows.append((cells[0], owned, cells[3]))
    return rows


def _owned_paths(agents: str) -> list[str]:
    return [path for _, paths, _ in _module_rows(agents) for path in paths]


def _paths_overlap(left: str, right: str) -> bool:
    left_path, right_path = Path(left), Path(right)
    return left_path == right_path or left_path in right_path.parents or right_path in left_path.parents


def _sha(value: object, code: str) -> str:
    require(type(value) is str and SHA256_RE.fullmatch(str(value)), code)
    return str(value)


__all__ = [
    "LocalControlledTrustError", "apply_bootstrap_v2",
    "validate_bootstrap_v2_envelope",
]
