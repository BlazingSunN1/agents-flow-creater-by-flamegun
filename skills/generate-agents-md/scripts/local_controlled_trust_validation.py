from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from strict_json import loads as strict_json_loads
from local_controlled_data_safety import (
    InMemoryReplayGuard,
    ReplayGuard,
    canonical_json as _canonical_json,
    parse_utc as _parse_utc,
    require as _require,
)
from local_controlled_file_safety import atomic_replace_text, directory_identity, has_exact_path_spelling
from local_controlled_path_safety import (
    FileIdentity,
    LocalControlledTrustError,
    canonical_directory as _canonical_directory,
    is_exact_owned_path as _is_exact_owned_path,
    is_normalized_path as _is_normalized_path,
    is_within as _is_within,
    open_unique_lock as _open_unique_lock,
    read_bound_regular_file as _read_bound_regular_file,
    read_external_regular_file as _read_external_regular_file,
    verify_unique_lock as _verify_unique_lock,
)

TRUST_MODE = "local_controlled_same_user"
SECURITY_CAVEAT = "same_os_user_can_access_private_key_not_host_native_attestation"
DOMAIN = "generate-agents-md/local-controlled-trust/v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
IDENTITY_RE = re.compile(r"[A-Za-z0-9/][A-Za-z0-9/._:-]{1,255}")
ENVELOPE_FIELDS = (
    "schema_version", "trust_mode", "payload_path", "payload_sha256",
    "signature_path", "signature_sha256", "public_key_path",
    "public_key_fingerprint_sha256",
)
SIGNATURE_FIELDS = (
    "algorithm", "canonicalization", "domain", "key_id",
    "payload_canonical_sha256", "signature_base64url",
)
COMMON_RECEIPT_FIELDS = (
    "schema_version", "receipt_type", "trust_mode", "security_caveat",
    "explicit_user_authorization", "authorization_source", "issuer", "key_id",
    "key_fingerprint_sha256", "agent_handle", "assigned_model",
    "assigned_reasoning_effort", "role", "module_key", "stable_title",
    "project_root", "replay_state_path", "owned_paths", "issued_at", "not_before", "expires_at",
    "nonce", "receipt_id", "baseline_sha256", "policy_sha256",
    "candidate_sha256", "authority_matrix_sha256",
)
BOOTSTRAP_FIELDS = COMMON_RECEIPT_FIELDS + (
    "operation_id", "one_time", "post_bootstrap_authority",
)
BINDING_FIELDS = (
    "baseline_sha256", "policy_sha256", "candidate_sha256",
    "authority_matrix_sha256",
)
class FileReplayGuard:
    """Durable same-user replay ledger stored outside the project root."""

    def __init__(self, state_path: Path, project_root: Path) -> None:
        self._root = _canonical_directory(project_root, "project-root-mismatch")
        _require(
            state_path.is_absolute() and _is_normalized_path(str(state_path)),
            "unsafe-replay-state-path",
        )
        self._state_path = state_path
        try:
            self._parent = state_path.parent.resolve(strict=True)
        except OSError as error:
            raise LocalControlledTrustError("unsafe-replay-state-path") from error
        _require(not _is_within(self._parent, self._root), "unsafe-replay-state-path")
        _require(
            self._parent == state_path.parent
            and has_exact_path_spelling(state_path.parent)
            and not state_path.parent.is_symlink(),
            "unsafe-replay-state-path",
        )
        self._parent_identity = self._read_parent_identity()
        self._last_state_identity: FileIdentity | None = None
        try:
            initial_state = os.lstat(self._state_path)
        except FileNotFoundError:
            initial_state = None
        except OSError as error:
            raise LocalControlledTrustError("unsafe-replay-state-path") from error
        if initial_state is not None and stat.S_ISREG(initial_state.st_mode):
            _require(has_exact_path_spelling(self._state_path), "unsafe-replay-state-path")

    def _read_parent_identity(self) -> tuple[int, int]:
        try:
            return directory_identity(self._parent)
        except OSError as error:
            raise LocalControlledTrustError("unsafe-replay-parent-path") from error

    @property
    def state_path(self) -> Path:
        return self._state_path

    def _verify_parent_identity(self) -> None:
        current_identity = self._read_parent_identity()
        _require(current_identity == self._parent_identity, "unsafe-replay-parent-path")

    def consume(self, receipt_id: str, nonce: str, expires_at: datetime) -> bool:
        import fcntl

        lock_path = self._state_path.with_name(self._state_path.name + ".lock")
        self._verify_parent_identity()
        descriptor = _open_unique_lock(lock_path)
        try:
            self._verify_parent_identity()
            with os.fdopen(descriptor, "r+", encoding="utf-8") as lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                except OSError as error:
                    raise LocalControlledTrustError("unsafe-replay-lock-path") from error
                self._verify_parent_identity()
                _verify_unique_lock(lock_file.fileno(), lock_path)
                self._verify_parent_identity()
                consumed = self._read_entries()
                _verify_unique_lock(lock_file.fileno(), lock_path)
                self._verify_state_identity(self._last_state_identity)
                self._verify_parent_identity()
                if (
                    receipt_id in {item["receipt_id"] for item in consumed}
                    or nonce in {item["nonce"] for item in consumed}
                ):
                    _verify_unique_lock(lock_file.fileno(), lock_path)
                    self._verify_state_identity(self._last_state_identity)
                    return False
                consumed.append({
                    "receipt_id": receipt_id,
                    "nonce": nonce,
                    "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                _verify_unique_lock(lock_file.fileno(), lock_path)
                self._verify_state_identity(self._last_state_identity)
                self._replace_state(consumed, self._last_state_identity, lock_file.fileno(), lock_path)
                _verify_unique_lock(lock_file.fileno(), lock_path)
                self._verify_parent_identity()
                return True
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise

    def _read_entries(self) -> list[dict[str, str]]:
        self._verify_parent_identity()
        identity = self._current_state_identity()
        self._last_state_identity = identity
        if identity is None:
            self._verify_parent_identity()
            return []
        payload, opened_identity = _read_bound_regular_file(
            self._state_path, "unsafe-replay-state-path",
        )
        _require(opened_identity == identity, "unsafe-replay-state-path")
        value = _strict_json_bytes(payload, "invalid-replay-state")
        self._verify_state_identity(opened_identity)
        self._last_state_identity = opened_identity
        self._verify_parent_identity()
        _require(isinstance(value, dict) and set(value) == {"schema_version", "consumed"},
                 "invalid-replay-state")
        _require(type(value.get("schema_version")) is int
                 and value.get("schema_version") == 1
                 and isinstance(value.get("consumed"), list),
                 "invalid-replay-state")
        entries = value["consumed"]
        assert isinstance(entries, list)
        receipt_ids: set[str] = set()
        nonces: set[str] = set()
        for item in entries:
            _require(
                isinstance(item, dict)
                and set(item) == {"receipt_id", "nonce", "expires_at"}
                and type(item.get("receipt_id")) is str
                and type(item.get("nonce")) is str
                and type(item.get("expires_at")) is str,
                "invalid-replay-state",
            )
            receipt_id = item["receipt_id"]
            nonce = item["nonce"]
            expires_at = item["expires_at"]
            assert isinstance(receipt_id, str)
            assert isinstance(nonce, str)
            assert isinstance(expires_at, str)
            _require(IDENTITY_RE.fullmatch(receipt_id) is not None, "invalid-replay-state")
            _require(SHA256_RE.fullmatch(nonce) is not None, "invalid-replay-state")
            _parse_utc(expires_at, "invalid-replay-state")
            _require(receipt_id not in receipt_ids and nonce not in nonces,
                     "invalid-replay-state")
            receipt_ids.add(receipt_id)
            nonces.add(nonce)
        return entries

    def _replace_state(
        self, entries: list[dict[str, str]], expected_identity: FileIdentity | None,
        lock_descriptor: int, lock_path: Path,
    ) -> None:
        self._verify_parent_identity()
        payload = json.dumps(
            {"schema_version": 1, "consumed": entries},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ) + "\n"

        def verify_target_before_replace() -> None:
            self._verify_parent_identity()
            _verify_unique_lock(lock_descriptor, lock_path)
            self._verify_state_identity(expected_identity)

        try:
            atomic_replace_text(
                self._state_path,
                payload,
                self._verify_parent_identity, self._parent_identity,
                verify_target_before_replace,
            )
        except OSError as error:
            raise LocalControlledTrustError("replay-state-persistence-failed") from error
        _verify_unique_lock(lock_descriptor, lock_path)
        stored, identity = _read_bound_regular_file(
            self._state_path, "unsafe-replay-state-path",
        )
        _require(stored == payload.encode("utf-8"), "replay-state-persistence-failed")
        self._last_state_identity = identity
        self._verify_state_identity(identity)

    def _current_state_identity(self) -> FileIdentity | None:
        self._verify_parent_identity()
        try:
            value = os.lstat(self._state_path)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise LocalControlledTrustError("unsafe-replay-state-path") from error
        _require(has_exact_path_spelling(self._state_path), "unsafe-replay-state-path")
        _require(
            stat.S_ISREG(value.st_mode) and value.st_nlink == 1,
            "unsafe-replay-state-path",
        )
        return value.st_dev, value.st_ino

    def _verify_state_identity(self, expected: FileIdentity | None) -> None:
        _require(self._current_state_identity() == expected, "unsafe-replay-state-path")


def validate_local_controlled_envelope(
    *, envelope_path: Path, project_root: Path, trusted_public_key_path: Path,
    expected_public_key_fingerprint: str, expected_receipt_type: str,
    expected_owned_paths: Sequence[str], expected_bindings: Mapping[str, str],
    now: datetime, replay_guard: ReplayGuard,
) -> dict[str, object]:
    """Verify and consume same-user integrity evidence without claiming host-native trust."""
    root = _validation_root(project_root, expected_receipt_type)
    public_file, public_bytes, envelope = _read_envelope_material(
        envelope_path, trusted_public_key_path, root,
    )
    fingerprint = _canonical_sha(expected_public_key_fingerprint, "untrusted-public-key")
    _require(envelope.get("public_key_path") == str(public_file), "untrusted-public-key")
    _require(envelope.get("public_key_fingerprint_sha256") == fingerprint,
             "untrusted-public-key")
    public_key = _load_ed25519_public_key(public_bytes)
    raw_fingerprint = hashlib.sha256(_raw_public_key(public_key)).hexdigest()
    _require(raw_fingerprint == fingerprint, "untrusted-public-key")

    payload_file, payload_bytes = _read_external_regular_file(
        _absolute_path(envelope.get("payload_path"), "invalid-local-envelope"), root, "payload",
    )
    signature_file, signature_bytes = _read_external_regular_file(
        _absolute_path(envelope.get("signature_path"), "invalid-local-envelope"), root, "signature",
    )
    _require(hashlib.sha256(payload_bytes).hexdigest() == envelope.get("payload_sha256"),
             "payload-sha256-drift")
    _require(hashlib.sha256(signature_bytes).hexdigest() == envelope.get("signature_sha256"),
             "signature-sha256-drift")
    payload = _strict_receipt_bytes(payload_bytes, expected_receipt_type)
    signature = _strict_object_bytes(
        signature_bytes, SIGNATURE_FIELDS, "invalid-local-signature",
    )
    canonical = _canonical_json(payload)
    _validate_signature_metadata(signature, payload, canonical)
    _verify_signature(public_key, signature, canonical)
    _require(payload.get("replay_state_path") == str(replay_guard.state_path),
             "replay-state-mismatch")
    _validate_local_semantics(
        payload, root=root, expected_receipt_type=expected_receipt_type,
        expected_owned_paths=expected_owned_paths, expected_bindings=expected_bindings,
        expected_fingerprint=fingerprint, now=now,
    )
    receipt_id = str(payload["receipt_id"])
    nonce = str(payload["nonce"])
    expires_at = _parse_utc(str(payload["expires_at"]), "invalid-local-receipt")
    _require(replay_guard.consume(receipt_id, nonce, expires_at), "replayed-receipt")
    return payload


def _read_envelope_material(
    envelope_path: Path, trusted_public_key_path: Path, root: Path,
) -> tuple[Path, bytes, dict[str, object]]:
    _, envelope_bytes = _read_external_regular_file(
        envelope_path, root, "envelope",
    )
    public_file, public_bytes = _read_external_regular_file(
        trusted_public_key_path, root, "public-key",
    )
    envelope = _strict_object_bytes(
        envelope_bytes, ENVELOPE_FIELDS, "invalid-local-envelope",
    )
    _require(type(envelope.get("schema_version")) is int
             and envelope.get("schema_version") == 1, "invalid-local-envelope")
    _require(envelope.get("trust_mode") == TRUST_MODE, "invalid-local-envelope")
    return public_file, public_bytes, envelope


def _validation_root(project_root: Path, receipt_type: str) -> Path:
    root = _canonical_directory(project_root, "project-root-mismatch")
    _require(receipt_type == "system_governance_bootstrap", "invalid-local-receipt")
    return root


def _strict_receipt_bytes(payload: bytes, receipt_type: str) -> dict[str, object]:
    return _strict_object_bytes(payload, BOOTSTRAP_FIELDS, "invalid-local-receipt")


def _strict_object_bytes(payload: bytes, fields: Sequence[str], code: str) -> dict[str, object]:
    value = _strict_json_bytes(payload, code)
    _require(isinstance(value, dict) and set(value) == set(fields), code)
    return value


def _strict_json_bytes(payload: bytes, code: str) -> object:
    try:
        value = strict_json_loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise LocalControlledTrustError(code) from error
    return value


def _validate_local_semantics(
    payload: dict[str, object], *, root: Path, expected_receipt_type: str,
    expected_owned_paths: Sequence[str], expected_bindings: Mapping[str, str],
    expected_fingerprint: str, now: datetime,
) -> None:
    _require(type(payload.get("schema_version")) is int
             and payload.get("schema_version") == 1, "invalid-local-receipt")
    _require(payload.get("receipt_type") == expected_receipt_type, "invalid-local-receipt")
    _require(payload.get("trust_mode") == TRUST_MODE, "invalid-local-receipt")
    _require(payload.get("security_caveat") == SECURITY_CAVEAT, "invalid-local-receipt")
    _require(payload.get("explicit_user_authorization") is True, "invalid-local-receipt")
    _require(payload.get("key_fingerprint_sha256") == expected_fingerprint,
             "untrusted-public-key")
    _validate_identity_assignment(payload)
    _validate_owned_and_bindings(payload, root, expected_owned_paths, expected_bindings)
    _validate_validity_window(payload, now)
    _require(type(payload.get("nonce")) is str
             and SHA256_RE.fullmatch(str(payload["nonce"])), "invalid-local-receipt")
    _validate_bootstrap(payload)


def _validate_identity_assignment(payload: dict[str, object]) -> None:
    for field in (
        "authorization_source", "issuer", "key_id", "agent_handle", "module_key",
        "receipt_id",
    ):
        _require(type(payload.get(field)) is str and IDENTITY_RE.fullmatch(str(payload[field])),
                 "invalid-local-receipt")
    stable_title = payload.get("stable_title")
    _require(
        type(stable_title) is str
        and stable_title == stable_title.strip()
        and 1 <= len(stable_title) <= 256
        and not any(ord(character) < 32 for character in stable_title),
        "invalid-local-receipt",
    )
    _require(payload.get("assigned_model") == "gpt-5.6-sol", "invalid-local-receipt")
    _require(payload.get("assigned_reasoning_effort") == "high", "invalid-local-receipt")
    _require(payload.get("role") in {"implementation", "module-maintainer"},
             "invalid-local-receipt")


def _validate_owned_and_bindings(
    payload: dict[str, object], root: Path, expected_owned_paths: Sequence[str],
    expected_bindings: Mapping[str, str],
) -> None:
    _require(payload.get("project_root") == str(root), "project-root-mismatch")
    owned = payload.get("owned_paths")
    expected_owned = tuple(expected_owned_paths)
    _require(isinstance(owned, list) and tuple(owned) == expected_owned,
             "owned-paths-mismatch")
    _require(len(set(expected_owned)) == len(expected_owned)
             and all(_is_exact_owned_path(item) for item in expected_owned)
             and all(_is_exact_owned_path(item) for item in owned),
             "owned-paths-mismatch")
    _require(set(expected_bindings) == set(BINDING_FIELDS), "candidate-binding-mismatch")
    for field in BINDING_FIELDS:
        expected = _canonical_sha(expected_bindings[field], "candidate-binding-mismatch")
        _require(payload.get(field) == expected, "candidate-binding-mismatch")


def _validate_validity_window(payload: dict[str, object], now: datetime) -> None:
    issued = _parse_utc(str(payload.get("issued_at")), "invalid-local-receipt")
    not_before = _parse_utc(str(payload.get("not_before")), "invalid-local-receipt")
    expires = _parse_utc(str(payload.get("expires_at")), "invalid-local-receipt")
    current = now.astimezone(timezone.utc)
    _require(issued <= not_before < expires, "invalid-local-receipt")
    _require(current >= not_before, "receipt-not-yet-valid")
    _require(current < expires, "receipt-expired")


def _validate_bootstrap(payload: dict[str, object]) -> None:
    _require(payload.get("one_time") is True, "invalid-local-receipt")
    _require(payload.get("post_bootstrap_authority") == "host-native-module-lease-required",
             "invalid-local-receipt")
    _require(type(payload.get("operation_id")) is str
             and IDENTITY_RE.fullmatch(str(payload["operation_id"])),
             "invalid-local-receipt")


def _validate_signature_metadata(
    signature: dict[str, object], payload: dict[str, object], canonical: bytes,
) -> None:
    _require(signature.get("algorithm") == "Ed25519", "invalid-local-signature")
    _require(signature.get("canonicalization") == "sorted-compact-json-v1",
             "invalid-local-signature")
    _require(signature.get("domain") == DOMAIN, "invalid-local-signature")
    _require(signature.get("key_id") == payload.get("key_id"), "invalid-local-signature")
    _require(signature.get("payload_canonical_sha256") == hashlib.sha256(canonical).hexdigest(),
             "invalid-local-signature")


def _verify_signature(public_key: Any, signature: dict[str, object], canonical: bytes) -> None:
    value = signature.get("signature_base64url")
    _require(type(value) is str and value, "invalid-local-signature")
    try:
        encoded = str(value)
        raw = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
        )
        canonical_value = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        _require(len(raw) == 64 and encoded == canonical_value, "invalid-local-signature")
        public_key.verify(raw, DOMAIN.encode("utf-8") + b"\0" + canonical)
    except LocalControlledTrustError:
        raise
    except Exception as error:
        raise LocalControlledTrustError("invalid-local-signature") from error


def _load_ed25519_public_key(payload: bytes) -> Any:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        value = serialization.load_pem_public_key(payload)
        _require(isinstance(value, Ed25519PublicKey), "untrusted-public-key")
        return value
    except LocalControlledTrustError:
        raise
    except Exception as error:
        raise LocalControlledTrustError("ed25519-verifier-unavailable") from error


def _raw_public_key(public_key: Any) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _absolute_path(value: object, code: str) -> Path:
    _require(type(value) is str and Path(str(value)).is_absolute(), code)
    return Path(str(value))


def _canonical_sha(value: object, code: str) -> str:
    _require(type(value) is str and SHA256_RE.fullmatch(str(value)), code)
    return str(value)
