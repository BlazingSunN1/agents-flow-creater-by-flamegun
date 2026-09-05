from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents_authority_matrix_validation import (
    ACTIONS,
    ACTORS,
    ALLOWED_POLICIES,
    EXPECTED_AUTHORITY_MATRIX,
)
from local_controlled_trust_validation import (
    FileReplayGuard,
    InMemoryReplayGuard,
    LocalControlledTrustError,
    validate_local_controlled_envelope,
)
from validate_local_controlled_trust import main as local_trust_cli_main


SHA_A = "1" * 64
SHA_B = "2" * 64
SHA_C = "3" * 64
SHA_D = "4" * 64
FROZEN_NOW = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


class LocalControlledTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.external = self.root / "external"
        self.project.mkdir()
        self.external.mkdir()
        (self.external / "skill").mkdir()
        (self.external / "plugin.json").write_text("{}\n", encoding="utf-8")
        self.replay_state = self.external / "cli-ledger.json"
        self.private = Ed25519PrivateKey.generate()
        self.public_path = self.external / "trusted.public.pem"
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.fingerprint = hashlib.sha256(raw).hexdigest()
        self.payload = self._payload()
        self.envelope = self._write_envelope(self.payload)
        self.replay = InMemoryReplayGuard(self.replay_state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "receipt_type": "system_governance_bootstrap",
            "trust_mode": "local_controlled_same_user",
            "security_caveat": "same_os_user_can_access_private_key_not_host_native_attestation",
            "explicit_user_authorization": True,
            "authorization_source": "explicit-user-authorization-test",
            "issuer": "local-test-dispatcher",
            "key_id": "local-test-key-01",
            "key_fingerprint_sha256": self.fingerprint,
            "agent_handle": "/root/test-implementation",
            "assigned_model": "gpt-6-astra",
            "assigned_reasoning_effort": "medium",
            "role": "implementation",
            "module_key": "UPSTREAM-GOVERNANCE-BOOTSTRAP",
            "stable_title": "Test governance bootstrap",
            "project_root": str(self.project),
            "replay_state_path": str(self.replay_state),
            "owned_paths": [str(self.external / "skill"), str(self.external / "plugin.json")],
            "issued_at": "2026-09-02T14:30:00Z",
            "not_before": "2026-09-02T14:30:00Z",
            "expires_at": "2026-09-02T15:30:00Z",
            "nonce": "a" * 64,
            "receipt_id": "receipt-local-test-01",
            "operation_id": "bootstrap-local-test-01",
            "one_time": True,
            "post_bootstrap_authority": "host-native-module-lease-required",
            "baseline_sha256": SHA_A,
            "policy_sha256": SHA_B,
            "candidate_sha256": SHA_C,
            "authority_matrix_sha256": SHA_D,
        }

    def _write_envelope(
        self, payload: dict[str, object], *, private: Ed25519PrivateKey | None = None,
    ) -> Path:
        signer = private or self.private
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        domain = "generate-agents-md/local-controlled-trust/v1"
        signature = signer.sign(domain.encode("utf-8") + b"\0" + canonical)
        payload_path = self.external / "payload.json"
        signature_path = self.external / "signature.json"
        envelope_path = self.external / "envelope.json"
        payload_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        signature_value = {
            "algorithm": "Ed25519",
            "canonicalization": "sorted-compact-json-v1",
            "domain": domain,
            "key_id": payload["key_id"],
            "payload_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "signature_base64url": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
        }
        signature_path.write_text(json.dumps(signature_value, sort_keys=True), encoding="utf-8")
        envelope_value = {
            "schema_version": 1,
            "trust_mode": "local_controlled_same_user",
            "payload_path": str(payload_path),
            "payload_sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            "signature_path": str(signature_path),
            "signature_sha256": hashlib.sha256(signature_path.read_bytes()).hexdigest(),
            "public_key_path": str(self.public_path),
            "public_key_fingerprint_sha256": self.fingerprint,
        }
        envelope_path.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
        return envelope_path

    def _validate(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "envelope_path": self.envelope,
            "project_root": self.project,
            "trusted_public_key_path": self.public_path,
            "expected_public_key_fingerprint": self.fingerprint,
            "expected_receipt_type": "system_governance_bootstrap",
            "expected_owned_paths": tuple(self.payload["owned_paths"]),
            "expected_bindings": {
                "baseline_sha256": SHA_A,
                "policy_sha256": SHA_B,
                "candidate_sha256": SHA_C,
                "authority_matrix_sha256": SHA_D,
            },
            "now": FROZEN_NOW,
            "replay_guard": self.replay,
        }
        arguments.update(overrides)
        return validate_local_controlled_envelope(**arguments)

    def _cli_arguments(self, **overrides: object) -> list[str]:
        values: dict[str, object] = {
            "envelope": self.envelope,
            "project_root": self.project,
            "public_key": self.public_path,
            "receipt_type": "system_governance_bootstrap",
            "replay_state": self.external / "cli-ledger.json",
        }
        values.update(overrides)
        return [
            str(values["envelope"]),
            "--project-root", str(values["project_root"]),
            "--trusted-public-key", str(values["public_key"]),
            "--public-key-fingerprint", self.fingerprint,
            "--receipt-type", str(values["receipt_type"]),
            "--owned-path", str(self.external / "skill"),
            "--owned-path", str(self.external / "plugin.json"),
            "--baseline-sha256", SHA_A,
            "--policy-sha256", SHA_B,
            "--candidate-sha256", SHA_C,
            "--authority-matrix-sha256", SHA_D,
            "--replay-state", str(values["replay_state"]),
        ]

    def _run_cli(self, arguments: list[str]) -> tuple[int, dict[str, object], str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = local_trust_cli_main(arguments)
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def _case_alias(self, path: Path) -> Path:
        parts = list(path.parts)
        for index, component in enumerate(parts[1:], start=1):
            alias_component = component.swapcase()
            if alias_component == component:
                continue
            alias = Path(parts[0], *parts[1:index], alias_component, *parts[index + 1:])
            if alias.exists() and str(alias) != str(path):
                return alias
        self.skipTest("filesystem does not expose a case-insensitive path alias")

    def _leaf_case_alias(self, path: Path) -> Path:
        alias = path.with_name(path.name.swapcase())
        if alias.exists() and str(alias) != str(path):
            return alias
        self.skipTest("filesystem does not expose a case-insensitive leaf alias")

    def test_valid_explicit_local_bootstrap_is_accepted_once(self) -> None:
        value = self._validate()
        self.assertEqual("local_controlled_same_user", value["trust_mode"])
        with self.assertRaisesRegex(LocalControlledTrustError, "replayed-receipt"):
            self._validate()

    def test_unknown_or_project_replaced_public_key_is_rejected(self) -> None:
        other_path = self.project / "replacement.public.pem"
        other_path.write_bytes(self.public_path.read_bytes())
        envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
        envelope["public_key_path"] = str(other_path)
        self.envelope.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(
            LocalControlledTrustError, "(?:untrusted-public-key|unsafe-public-key-path)",
        ):
            self._validate(trusted_public_key_path=other_path)

    def test_tampered_payload_is_rejected(self) -> None:
        payload_path = Path(json.loads(self.envelope.read_text())["payload_path"])
        payload_path.write_text(payload_path.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(LocalControlledTrustError, "payload-sha256-drift"):
            self._validate()

    def test_invalid_detached_signature_is_rejected(self) -> None:
        envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
        signature_path = Path(envelope["signature_path"])
        signature = json.loads(signature_path.read_text(encoding="utf-8"))
        signature["signature_base64url"] = base64.urlsafe_b64encode(
            b"x" * 64,
        ).rstrip(b"=").decode("ascii")
        signature_path.write_text(json.dumps(signature, sort_keys=True), encoding="utf-8")
        envelope["signature_sha256"] = hashlib.sha256(signature_path.read_bytes()).hexdigest()
        self.envelope.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-signature"):
            self._validate()

    def test_noncanonical_detached_signature_encoding_is_rejected(self) -> None:
        envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
        signature_path = Path(envelope["signature_path"])
        signature = json.loads(signature_path.read_text(encoding="utf-8"))
        signature["signature_base64url"] += "=="
        signature_path.write_text(json.dumps(signature, sort_keys=True), encoding="utf-8")
        envelope["signature_sha256"] = hashlib.sha256(signature_path.read_bytes()).hexdigest()
        self.envelope.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-signature"):
            self._validate()

    def test_expired_or_not_yet_valid_receipt_is_rejected(self) -> None:
        with self.assertRaisesRegex(LocalControlledTrustError, "receipt-expired"):
            self._validate(now=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc))
        with self.assertRaisesRegex(LocalControlledTrustError, "receipt-not-yet-valid"):
            self._validate(now=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc))

    def test_missing_explicit_authorization_or_caveat_is_rejected(self) -> None:
        for field, value in (
            ("explicit_user_authorization", False),
            ("security_caveat", "host-attested-unforgeable"),
        ):
            with self.subTest(field=field):
                mutated = dict(self.payload, **{field: value})
                envelope = self._write_envelope(mutated)
                with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-receipt"):
                    self._validate(envelope_path=envelope, replay_guard=InMemoryReplayGuard(self.replay_state))

    def test_path_scope_and_candidate_bindings_are_exact(self) -> None:
        with self.assertRaisesRegex(LocalControlledTrustError, "owned-paths-mismatch"):
            self._validate(expected_owned_paths=(str(self.external),))
        with self.assertRaisesRegex(LocalControlledTrustError, "candidate-binding-mismatch"):
            self._validate(
                replay_guard=InMemoryReplayGuard(self.replay_state),
                expected_bindings={
                    "baseline_sha256": SHA_A,
                    "policy_sha256": SHA_B,
                    "candidate_sha256": "9" * 64,
                    "authority_matrix_sha256": SHA_D,
                },
            )

    def test_owned_paths_reject_signed_and_expected_aliases(self) -> None:
        aliases = self.external / "aliases"
        aliases.mkdir()
        (aliases / "skill-leaf").symlink_to(self.external / "skill", target_is_directory=True)
        real_parent = self.external / "real-parent"
        real_parent.mkdir()
        (real_parent / "child").mkdir()
        (aliases / "parent").symlink_to(real_parent, target_is_directory=True)
        cases = (
            str(aliases / "skill-leaf"),
            str(aliases / "parent" / "child"),
            str(self.external / "skill" / ".." / "skill"),
        )
        for index, alias in enumerate(cases):
            with self.subTest(alias=alias):
                mutated = dict(self.payload)
                mutated["owned_paths"] = [alias, str(self.external / "plugin.json")]
                mutated["nonce"] = f"{index + 1:064x}"
                mutated["receipt_id"] = f"receipt-alias-test-{index}"
                envelope = self._write_envelope(mutated)
                with self.assertRaisesRegex(LocalControlledTrustError, "owned-paths-mismatch"):
                    self._validate(
                        envelope_path=envelope,
                        expected_owned_paths=tuple(mutated["owned_paths"]),
                        replay_guard=InMemoryReplayGuard(self.replay_state),
                    )
        hardlink = aliases / "plugin-hardlink.json"
        os.link(self.external / "plugin.json", hardlink)
        mutated = dict(self.payload)
        mutated["owned_paths"] = [str(hardlink), str(self.external / "skill")]
        mutated["nonce"] = "f" * 64
        mutated["receipt_id"] = "receipt-hardlink-test"
        envelope = self._write_envelope(mutated)
        with self.assertRaisesRegex(LocalControlledTrustError, "owned-paths-mismatch"):
            self._validate(
                envelope_path=envelope,
                expected_owned_paths=tuple(mutated["owned_paths"]),
                replay_guard=InMemoryReplayGuard(self.replay_state),
            )

    def test_durable_replay_guard_rejects_reuse_across_instances(self) -> None:
        state = self.external / "replay-state.json"
        envelope = self._write_envelope(dict(self.payload, replay_state_path=str(state)))
        self._validate(
            envelope_path=envelope, replay_guard=FileReplayGuard(state, self.project),
        )
        with self.assertRaisesRegex(LocalControlledTrustError, "replayed-receipt"):
            self._validate(
                envelope_path=envelope, replay_guard=FileReplayGuard(state, self.project),
            )

    def test_signed_replay_state_path_prevents_cross_ledger_reuse(self) -> None:
        signed_state = self.external / "cli-ledger.json"
        self._validate(replay_guard=FileReplayGuard(signed_state, self.project))

        missing_state = self.external / "alternate-missing-ledger.json"
        with self.assertRaisesRegex(LocalControlledTrustError, "replay-state-mismatch"):
            self._validate(replay_guard=FileReplayGuard(missing_state, self.project))
        self.assertFalse(missing_state.exists())
        self.assertFalse(missing_state.with_name(missing_state.name + ".lock").exists())

        existing_state = self.external / "alternate-existing-ledger.json"
        original = b'{"schema_version":1,"consumed":[]}\n'
        existing_state.write_bytes(original)
        with self.assertRaisesRegex(LocalControlledTrustError, "replay-state-mismatch"):
            self._validate(replay_guard=FileReplayGuard(existing_state, self.project))
        self.assertEqual(original, existing_state.read_bytes())
        self.assertFalse(existing_state.with_name(existing_state.name + ".lock").exists())

    def test_replay_state_fsyncs_parent_directory_after_atomic_replace(self) -> None:
        state = self.external / "durable-ledger.json"
        synced_directory: list[bool] = []
        real_fsync = os.fsync

        def observed_fsync(descriptor: int) -> None:
            synced_directory.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
            real_fsync(descriptor)

        with mock.patch(
            "local_controlled_file_safety.os.fsync", side_effect=observed_fsync,
        ):
            FileReplayGuard(state, self.project).consume(
                "receipt-durable-parent", "9" * 64, FROZEN_NOW,
            )
        self.assertEqual([False, True], synced_directory)

    def test_replay_lock_rejects_symlink_directory_and_hardlink(self) -> None:
        for kind in ("symlink", "directory", "hardlink"):
            with self.subTest(kind=kind):
                state = self.external / f"{kind}-ledger.json"
                lock = state.with_name(state.name + ".lock")
                if kind == "symlink":
                    target = self.external / "lock-target"
                    target.write_text("", encoding="utf-8")
                    lock.symlink_to(target)
                elif kind == "directory":
                    lock.mkdir()
                else:
                    target = self.external / "lock-hardlink-target"
                    target.write_text("", encoding="utf-8")
                    os.link(target, lock)
                with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-lock-path"):
                    FileReplayGuard(state, self.project).consume(
                        f"receipt-{kind}", "e" * 64, FROZEN_NOW,
                    )

    def test_replay_lock_inode_swap_after_open_is_rejected(self) -> None:
        state = self.external / "raced-ledger.json"
        lock = state.with_name(state.name + ".lock")
        alternate = self.external / "alternate-lock"
        alternate.write_text("", encoding="utf-8")
        real_lstat = os.lstat
        calls = 0

        def raced_lstat(path: object) -> os.stat_result:
            nonlocal calls
            if Path(path) == lock:
                calls += 1
                return real_lstat(lock if calls == 1 else alternate)
            return real_lstat(path)

        with mock.patch("local_controlled_path_safety.os.lstat", side_effect=raced_lstat):
            with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-lock-path"):
                FileReplayGuard(state, self.project).consume(
                    "receipt-raced-lock", "f" * 64, FROZEN_NOW,
                )
        self.assertTrue(lock.is_file())

    def test_replay_lock_inode_swap_after_ledger_read_is_rejected(self) -> None:
        state = self.external / "post-read-lock-race-ledger.json"
        lock = state.with_name(state.name + ".lock")
        displaced = self.external / "displaced-post-read-lock"
        guard = FileReplayGuard(state, self.project)
        original_read = guard._read_entries

        def raced_read() -> list[dict[str, str]]:
            entries = original_read()
            lock.rename(displaced)
            lock.write_text("", encoding="utf-8")
            return entries

        with mock.patch.object(guard, "_read_entries", side_effect=raced_read):
            with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-lock-path"):
                guard.consume("receipt-post-read-lock-race", "8" * 64, FROZEN_NOW)

    def test_replay_ledger_inode_swap_after_read_is_rejected(self) -> None:
        state = self.external / "post-read-ledger-race.json"
        state.write_text(json.dumps({"schema_version": 1, "consumed": []}))
        displaced = self.external / "displaced-post-read-ledger.json"
        guard = FileReplayGuard(state, self.project)
        original_read = guard._read_entries

        def raced_read() -> list[dict[str, str]]:
            entries = original_read()
            state.rename(displaced)
            state.write_text(json.dumps({"schema_version": 1, "consumed": []}))
            return entries

        with mock.patch.object(guard, "_read_entries", side_effect=raced_read):
            with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-state-path"):
                guard.consume("receipt-post-read-ledger-race", "7" * 64, FROZEN_NOW)

    def test_replay_ledger_swap_between_path_check_and_read_cannot_clear_history(self) -> None:
        state = self.external / "pre-read-ledger-race.json"
        consumed = {
            "receipt_id": "receipt-pre-read-ledger-race",
            "nonce": "6" * 64,
            "expires_at": "2026-09-02T15:30:00Z",
        }
        state.write_text(json.dumps({"schema_version": 1, "consumed": [consumed]}))
        replacement = self.external / "cleared-ledger-replacement.json"
        replacement.write_text(json.dumps({"schema_version": 1, "consumed": []}))
        real_open = os.open
        raced = False

        def raced_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal raced
            if Path(path) == state and not raced:
                raced = True
                os.replace(replacement, state)
            return real_open(path, flags, *args, **kwargs)

        guard = FileReplayGuard(state, self.project)
        with mock.patch("local_controlled_path_safety.os.open", side_effect=raced_open):
            with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-state-path"):
                guard.consume(consumed["receipt_id"], consumed["nonce"], FROZEN_NOW)

    def test_broken_symlink_replay_ledger_is_rejected_without_consumption(self) -> None:
        state = self.external / "broken-ledger.json"
        state.symlink_to(self.external / "missing-ledger-target.json")
        guard = FileReplayGuard(state, self.project)
        with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-state-path"):
            guard.consume("receipt-broken-ledger", "5" * 64, FROZEN_NOW)

    def test_replay_guard_rejects_parent_directory_replacement(self) -> None:
        parent = self.external / "ledger-parent"
        original = self.external / "ledger-parent-original"
        parent.mkdir()
        state = parent / "ledger.json"
        guard = FileReplayGuard(state, self.project)
        parent.rename(original)
        parent.mkdir()
        try:
            with self.assertRaisesRegex(
                LocalControlledTrustError, "unsafe-replay-parent-path",
            ):
                guard.consume("receipt-parent-swap", "a" * 64, FROZEN_NOW)
        finally:
            for child in parent.iterdir():
                child.unlink()
            parent.rmdir()
            original.rename(parent)

    def test_replay_parent_fsync_fd_must_match_frozen_parent_identity(self) -> None:
        parent = self.external / "fsync-parent"
        displaced = self.external / "fsync-parent-original"
        parent.mkdir()
        state = parent / "ledger.json"
        guard = FileReplayGuard(state, self.project)
        real_open = os.open
        raced = False

        def raced_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal raced
            if Path(path) == parent and flags & os.O_DIRECTORY and not raced:
                raced = True
                parent.rename(displaced)
                parent.mkdir()
                descriptor = real_open(path, flags, *args, **kwargs)
                parent.rmdir()
                displaced.rename(parent)
                return descriptor
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("local_controlled_file_safety.os.open", side_effect=raced_open):
            with self.assertRaisesRegex(
                LocalControlledTrustError, "replay-state-persistence-failed",
            ):
                guard.consume("receipt-fsync-parent-race", "4" * 64, FROZEN_NOW)
        self.assertTrue(raced)

    def test_missing_external_artifacts_return_stable_cli_json(self) -> None:
        cases: list[tuple[str, str, dict[str, object]]] = [
            ("envelope", "unsafe-envelope-path", {
                "envelope": self.external / "missing-envelope.json",
            }),
            ("public-key", "unsafe-public-key-path", {
                "public_key": self.external / "missing-public.pem",
            }),
        ]
        for label, field, code in (
            ("payload", "payload_path", "unsafe-payload-path"),
            ("signature", "signature_path", "unsafe-signature-path"),
        ):
            envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
            envelope[field] = str(self.external / f"missing-{label}.json")
            path = self.external / f"{label}-missing-envelope.json"
            path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
            cases.append((label, code, {"envelope": path}))
        for label, expected, overrides in cases:
            with self.subTest(label=label):
                exit_code, payload, stderr = self._run_cli(self._cli_arguments(**overrides))
                self.assertEqual(1, exit_code)
                self.assertEqual({"valid": False, "error": expected}, payload)
                self.assertEqual("", stderr)

        vanishing = self.external / "vanishing-envelope.json"
        vanishing.write_bytes(self.envelope.read_bytes())
        original_resolve = Path.resolve

        def remove_before_resolve(path: Path, *args: object, **kwargs: object) -> Path:
            if path == vanishing and vanishing.exists():
                vanishing.unlink()
            return original_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", new=remove_before_resolve):
            exit_code, payload, stderr = self._run_cli(
                self._cli_arguments(envelope=vanishing),
            )
        self.assertEqual(1, exit_code)
        self.assertEqual({"valid": False, "error": "unsafe-envelope-path"}, payload)
        self.assertEqual("", stderr)

    def test_schema_versions_reject_boolean_aliases(self) -> None:
        payload = dict(self.payload, schema_version=True)
        envelope = self._write_envelope(payload)
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-receipt"):
            self._validate(envelope_path=envelope, replay_guard=InMemoryReplayGuard(self.replay_state))

        self._write_envelope(self.payload)
        envelope_value = json.loads(self.envelope.read_text(encoding="utf-8"))
        envelope_value["schema_version"] = True
        self.envelope.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-envelope"):
            self._validate(replay_guard=InMemoryReplayGuard(self.replay_state))

        state = self.external / "boolean-schema-ledger.json"
        state.write_text(json.dumps({"schema_version": True, "consumed": []}))
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-replay-state"):
            FileReplayGuard(state, self.project).consume(
                "receipt-boolean-schema", "d" * 64, FROZEN_NOW,
            )

    def test_owned_path_rejects_case_insensitive_spelling_alias(self) -> None:
        exact = self.external / "OwnedCasePath"
        exact.mkdir()
        alias = self.external / "ownedcasepath"
        if not alias.exists():
            self.skipTest("filesystem is case-sensitive")
        mutated = dict(self.payload)
        mutated["owned_paths"] = [str(alias), str(self.external / "plugin.json")]
        envelope = self._write_envelope(mutated)
        with self.assertRaisesRegex(LocalControlledTrustError, "owned-paths-mismatch"):
            self._validate(
                envelope_path=envelope,
                expected_owned_paths=tuple(mutated["owned_paths"]),
                    replay_guard=InMemoryReplayGuard(self.replay_state),
                )

    def test_project_root_rejects_case_insensitive_spelling_alias(self) -> None:
        alias = self._case_alias(self.project)
        mutated = dict(self.payload, project_root=str(alias))
        envelope = self._write_envelope(mutated)
        with self.assertRaisesRegex(LocalControlledTrustError, "project-root-mismatch"):
            self._validate(
                envelope_path=envelope,
                project_root=alias,
                replay_guard=InMemoryReplayGuard(self.replay_state),
            )

    def test_external_artifacts_and_replay_reject_case_insensitive_spelling_aliases(self) -> None:
        for label in ("envelope", "public-key", "payload", "signature"):
            with self.subTest(label=label):
                envelope = self._write_envelope(self.payload)
                envelope_value = json.loads(envelope.read_text(encoding="utf-8"))
                if label == "envelope":
                    alias = self._leaf_case_alias(envelope)
                    arguments = {"envelope_path": alias}
                elif label == "public-key":
                    alias = self._leaf_case_alias(self.public_path)
                    envelope_value["public_key_path"] = str(alias)
                    envelope.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
                    arguments = {"trusted_public_key_path": alias}
                else:
                    field = f"{label}_path"
                    exact = Path(str(envelope_value[field]))
                    alias = self._leaf_case_alias(exact)
                    envelope_value[field] = str(alias)
                    envelope.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
                    arguments = {}
                with self.assertRaisesRegex(
                    LocalControlledTrustError, f"unsafe-{label}-path",
                ):
                    self._validate(replay_guard=InMemoryReplayGuard(self.replay_state), **arguments)

        replay_state = self.external / "case-replay-ledger.json"
        replay_state.write_text(json.dumps({"schema_version": 1, "consumed": []}))
        replay_alias = self._leaf_case_alias(replay_state)
        with self.assertRaisesRegex(LocalControlledTrustError, "unsafe-replay-state-path"):
            FileReplayGuard(replay_alias, self.project)

    def test_cli_rejects_unsupported_receipt_type_with_json_error(self) -> None:
        exit_code, payload, stderr = self._run_cli(self._cli_arguments(
            receipt_type="module_write_lease",
        ))
        self.assertEqual(1, exit_code)
        self.assertEqual({"valid": False, "error": "invalid-receipt-type"}, payload)
        self.assertEqual("", stderr)

    def test_cli_missing_required_arguments_use_stable_json_error(self) -> None:
        exit_code, payload, stderr = self._run_cli([])
        self.assertEqual(1, exit_code)
        self.assertEqual({"valid": False, "error": "invalid-cli-arguments"}, payload)
        self.assertEqual("", stderr)

    def test_symlink_loop_runtime_errors_return_stable_cli_json(self) -> None:
        project_loop = self.external / "project-loop"
        project_loop.symlink_to(project_loop.name)
        exit_code, payload, stderr = self._run_cli(
            self._cli_arguments(project_root=project_loop),
        )
        self.assertEqual(1, exit_code)
        self.assertEqual({"valid": False, "error": "project-root-mismatch"}, payload)
        self.assertEqual("", stderr)

        for label in ("envelope", "public-key", "payload", "signature"):
            with self.subTest(label=label):
                loop = self.external / f"{label}-loop"
                loop.symlink_to(loop.name)
                envelope = self._write_envelope(self.payload)
                envelope_value = json.loads(envelope.read_text(encoding="utf-8"))
                if label == "envelope":
                    arguments = self._cli_arguments(envelope=loop)
                elif label == "public-key":
                    envelope_value["public_key_path"] = str(loop)
                    envelope.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
                    arguments = self._cli_arguments(public_key=loop)
                else:
                    envelope_value[f"{label}_path"] = str(loop)
                    envelope.write_text(json.dumps(envelope_value, sort_keys=True), encoding="utf-8")
                    arguments = self._cli_arguments(envelope=envelope)
                exit_code, payload, stderr = self._run_cli(arguments)
                self.assertEqual(1, exit_code)
                self.assertEqual({"valid": False, "error": f"unsafe-{label}-path"}, payload)
                self.assertEqual("", stderr)

        with mock.patch(
            "validate_local_controlled_trust.validate_local_controlled_envelope",
            side_effect=RuntimeError("path loop contains sensitive location"),
        ):
            exit_code, payload, stderr = self._run_cli(self._cli_arguments())
        self.assertEqual(1, exit_code)
        self.assertEqual({"valid": False, "error": "local-trust-io-error"}, payload)
        self.assertEqual("", stderr)

    def test_replay_guard_rejects_invalid_ledger_entries(self) -> None:
        state = self.external / "replay-state.json"
        invalid_entries = (
            [{"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
              "expires_at": "2026-09-02T15:30:00Z", "unexpected": True}],
            [{"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
              "expires_at": "not-a-time"}],
            [{"receipt_id": "", "nonce": "b" * 64,
              "expires_at": "2026-09-02T15:30:00Z"}],
            [{"receipt_id": "bad identity", "nonce": "b" * 64,
              "expires_at": "2026-09-02T15:30:00Z"}],
            [{"receipt_id": "receipt-ledger-01", "nonce": "",
              "expires_at": "2026-09-02T15:30:00Z"}],
            [
                {"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
                {"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
            ],
            [
                {"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
                {"receipt_id": "receipt-ledger-01", "nonce": "c" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
            ],
            [
                {"receipt_id": "receipt-ledger-01", "nonce": "b" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
                {"receipt_id": "receipt-ledger-02", "nonce": "b" * 64,
                 "expires_at": "2026-09-02T15:30:00Z"},
            ],
        )
        for entries in invalid_entries:
            with self.subTest(entries=entries):
                state.write_text(json.dumps({"schema_version": 1, "consumed": entries}))
                with self.assertRaisesRegex(LocalControlledTrustError, "invalid-replay-state"):
                    FileReplayGuard(state, self.project).consume(
                        "receipt-ledger-new", "d" * 64, FROZEN_NOW,
                    )

    def test_receipt_id_and_nonce_are_independently_single_use(self) -> None:
        for guard in (InMemoryReplayGuard(self.replay_state), FileReplayGuard(
            self.external / "global-identity-ledger.json", self.project,
        )):
            with self.subTest(guard=type(guard).__name__):
                self.assertTrue(guard.consume("receipt-one", "a" * 64, FROZEN_NOW))
                self.assertFalse(guard.consume("receipt-one", "b" * 64, FROZEN_NOW))
                self.assertFalse(guard.consume("receipt-two", "a" * 64, FROZEN_NOW))

    def test_same_user_mode_rejects_ordinary_module_write_lease(self) -> None:
        bootstrap_shaped_lease = dict(self.payload, receipt_type="module_write_lease")
        envelope = self._write_envelope(bootstrap_shaped_lease)
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-receipt"):
            self._validate(
                envelope_path=envelope,
                expected_receipt_type="module_write_lease",
                replay_guard=InMemoryReplayGuard(self.replay_state),
            )

        lease = dict(self.payload)
        for field in ("operation_id", "one_time", "post_bootstrap_authority"):
            lease.pop(field)
        lease.update({
            "receipt_type": "module_write_lease",
            "lease_id": "lease-local-test-01",
            "lease_epoch": 1,
            "lease_status": "active",
            "target_path": str(self.external / "skill"),
            "unique_active_lease": True,
            "revocation_id": "revocation-local-test-01",
        })
        envelope = self._write_envelope(lease)
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-receipt"):
            self._validate(
                envelope_path=envelope,
                expected_receipt_type="module_write_lease",
                replay_guard=InMemoryReplayGuard(self.replay_state),
            )

    def test_bootstrap_cannot_self_report_follow_on_lease_authority(self) -> None:
        mutated = dict(
            self.payload,
            post_bootstrap_authority="module-write-lease-required",
        )
        envelope = self._write_envelope(mutated)
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-local-receipt"):
            self._validate(
                envelope_path=envelope,
                replay_guard=InMemoryReplayGuard(self.replay_state),
            )

    def test_schemas_are_closed_and_bind_the_same_user_caveat(self) -> None:
        asset_root = Path(__file__).resolve().parent.parent / "assets"
        for name in (
            "local-controlled-trust-envelope.schema.json",
            "local-controlled-detached-signature.schema.json",
            "system-governance-bootstrap-receipt.schema.json",
        ):
            with self.subTest(name=name):
                value = json.loads((asset_root / name).read_text(encoding="utf-8"))
                self.assertFalse(value.get("additionalProperties", True))
                if "schema_version" in value.get("properties", {}):
                    self.assertEqual("integer", value["properties"]["schema_version"]["type"])
        bootstrap = json.loads((
            asset_root / "system-governance-bootstrap-receipt.schema.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            "same_os_user_can_access_private_key_not_host_native_attestation",
            bootstrap["properties"]["security_caveat"]["const"],
        )
        lease = json.loads((
            asset_root / "local-controlled-module-write-lease.schema.json"
        ).read_text(encoding="utf-8"))
        self.assertFalse(lease.get("additionalProperties", True))
        self.assertEqual(
            "same_os_user_can_access_private_key_not_host_native_attestation",
            lease["properties"]["security_caveat"]["const"],
        )
        self.assertTrue((asset_root / "local-controlled-module-write-lease.template.json").is_file())

    def test_bootstrap_template_and_schema_use_absolute_owned_paths(self) -> None:
        asset_root = Path(__file__).resolve().parent.parent / "assets"
        template = json.loads((
            asset_root / "system-governance-bootstrap-receipt.template.json"
        ).read_text(encoding="utf-8"))
        schema = json.loads((
            asset_root / "system-governance-bootstrap-receipt.schema.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            ["{{EXACT_CANONICAL_ABSOLUTE_OWNED_PATH}}"],
            template["owned_paths"],
        )
        self.assertEqual("^/", schema["properties"]["owned_paths"]["items"]["pattern"])
        self.assertEqual(
            "{{EXACT_CANONICAL_ABSOLUTE_REPLAY_STATE_PATH}}",
            template["replay_state_path"],
        )
        self.assertIn("replay_state_path", schema["required"])
        self.assertEqual("^/", schema["properties"]["replay_state_path"]["pattern"])
        signature_schema = json.loads((
            asset_root / "local-controlled-detached-signature.schema.json"
        ).read_text(encoding="utf-8"))
        signature_pattern = signature_schema["properties"]["signature_base64url"]["pattern"]
        canonical = base64.urlsafe_b64encode(b"x" * 64).rstrip(b"=").decode("ascii")
        self.assertIsNotNone(re.fullmatch(signature_pattern, canonical))
        for invalid in ("A", canonical[:-1], canonical + "A", canonical + "=", "+" + canonical[1:]):
            with self.subTest(invalid=invalid):
                self.assertIsNone(re.fullmatch(signature_pattern, invalid))


class SystemGovernanceAuthorityMatrixTests(unittest.TestCase):
    def test_bootstrap_actor_is_deny_by_default_with_one_narrow_capability(self) -> None:
        self.assertIn("system-governance-bootstrap", ACTORS)
        self.assertIn("bootstrap_system_governance", ACTIONS)
        self.assertEqual(
            {"bootstrap_system_governance": "external-explicit-only"},
            ALLOWED_POLICIES["system-governance-bootstrap"],
        )
        allowed = [
            row for row in EXPECTED_AUTHORITY_MATRIX["rows"]
            if row["policy"] != "deny" and row["actor"] == "system-governance-bootstrap"
        ]
        self.assertEqual(1, len(allowed))
        self.assertEqual("system-governance", allowed[0]["object"])
        self.assertEqual("exact-external-authorized-targets", allowed[0]["scope"])
        self.assertEqual("pending-stable-module-registration", allowed[0]["module_binding"])
        self.assertEqual(
            "local-coordination-or-host-attested-or-explicit-local-controlled-bootstrap-receipt",
            allowed[0]["run_binding"],
        )
        self.assertEqual(len(ACTORS) * len(ACTIONS), len(EXPECTED_AUTHORITY_MATRIX["rows"]))

    def test_skill_and_checklist_keep_default_strict_and_local_mode_explicit(self) -> None:
        root = Path(__file__).resolve().parent.parent
        text = "\n".join((
            (root / "SKILL.md").read_text(encoding="utf-8"),
            (root / "references/module-agent-governance.md").read_text(encoding="utf-8"),
            (root / "references/strict-security-governance.md").read_text(encoding="utf-8"),
            (root / "references/extraction-checklist.md").read_text(encoding="utf-8"),
            (root / "assets/AGENTS.template.md").read_text(encoding="utf-8"),
            (root.parent / "strict-delivery-security/SKILL.md").read_text(encoding="utf-8"),
        ))
        for required in (
            "local_controlled_same_user",
            "same_os_user_can_access_private_key_not_host_native_attestation",
            "system-governance-bootstrap",
            "assigned_model",
            "项目内公钥或调用方替换公钥",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
