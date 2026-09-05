from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_controlled_module_lease_validation import (
    LocalControlledTrustError,
    ModuleLeaseRegistry,
    activate_signed_module_lease,
    apply_signed_module_write,
    validate_module_lease_envelope,
)


NOW = datetime(2026, 9, 3, 8, 5, tzinfo=timezone.utc)
SHA_A, SHA_B, SHA_C, SHA_D = (character * 64 for character in "1234")
DOMAIN = "generate-agents-md/local-controlled-module-write-lease/v1"


class ModuleLeaseFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.external = self.root / "external"
        self.project.mkdir()
        self.external.mkdir()
        (self.project / "docs/requirements").mkdir(parents=True)
        (self.project / "docs/progress").mkdir(parents=True)
        self.target = self.project / "docs/progress/m11.md"
        self.target.write_text("before\n", encoding="utf-8")
        self.replacement = self.external / "replacement.md"
        self.replacement.write_text("after\n", encoding="utf-8")
        self.baseline = self.project / "docs/requirements/baseline.md"
        self.baseline.write_text("baseline\n", encoding="utf-8")
        self.authority = SHA_D
        agents = (
            "authority_matrix_sha256: " + self.authority + "\n"
            "| Module | Scope | Owned project-relative paths | Long-term maintenance Agent title |\n"
            "| --- | --- | --- | --- |\n"
            "| M11 | proof | `docs/progress/m11.md` | M11 local proof |\n"
        )
        self.agents = self.project / "AGENTS.md"
        self.agents.write_text(agents, encoding="utf-8")
        self.registry_path = self.external / "lease-registry.json"
        self.private = Ed25519PrivateKey.generate()
        self.public_path = self.external / "public.pem"
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        self.fingerprint = hashlib.sha256(raw).hexdigest()
        self.payload = self._payload()
        self.envelope = self._write(self.payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _target_record(self) -> dict[str, object]:
        before, after = self.target.read_bytes(), self.replacement.read_bytes()
        return {
            "path": "docs/progress/m11.md",
            "pre_sha256": hashlib.sha256(before).hexdigest(),
            "pre_size": len(before),
            "post_sha256": hashlib.sha256(after).hexdigest(),
            "post_size": len(after),
        }

    def _payload(self) -> dict[str, object]:
        targets = [self._target_record()]
        def candidate(prefix: str) -> str:
            snapshot = [{
                "path": target["path"], "sha256": target[f"{prefix}_sha256"],
                "size": target[f"{prefix}_size"],
            } for target in targets]
            return hashlib.sha256(json.dumps(
                {"targets": snapshot}, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest()
        return {
            "schema_version": 1,
            "receipt_type": "local_controlled_module_write_lease",
            "trust_mode": "local_controlled_same_user",
            "security_caveat": "same_os_user_can_access_private_key_not_host_native_attestation",
            "explicit_user_authorization": True,
            "authorization_mode": "local-controlled-same-user",
            "authorization_source": "user-authorized-m11",
            "issuer": "local-signer",
            "key_id": "local-key-01",
            "key_fingerprint_sha256": self.fingerprint,
            "registry_path": str(self.registry_path),
            "project_root": str(self.project),
            "module_key": "M11",
            "stable_title": "M11 local proof",
            "agent_handle": "/root/m11-writer",
            "run_id": "run-m11-01",
            "assigned_model": "gpt-6-astra",
            "assigned_reasoning_effort": "medium",
            "role": "implementation",
            "authorized_actions": ["write_module_artifacts"],
            "owned_paths": ["docs/progress/m11.md"],
            "targets": targets,
            "baseline_path": "docs/requirements/baseline.md",
            "baseline_sha256": hashlib.sha256(self.baseline.read_bytes()).hexdigest(),
            "policy_sha256": hashlib.sha256(self.agents.read_bytes()).hexdigest(),
            "authority_matrix_sha256": self.authority,
            "base_candidate_sha256": candidate("pre"),
            "post_candidate_sha256": candidate("post"),
            "code_version": "m11-local-01",
            "build_id": "build-m11-01",
            "issued_at": "2026-09-03T08:00:00Z",
            "not_before": "2026-09-03T08:00:00Z",
            "expires_at": "2026-09-03T08:15:00Z",
            "ttl_seconds": 900,
            "nonce": "a" * 64,
            "receipt_id": "receipt-m11-01",
            "lease_id": "lease-m11-01",
        }

    def _write(self, payload: dict[str, object], suffix: str = "") -> Path:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        signature = self.private.sign(DOMAIN.encode() + b"\0" + canonical)
        payload_path = self.external / f"payload{suffix}.json"
        signature_path = self.external / f"signature{suffix}.json"
        envelope_path = self.external / f"envelope{suffix}.json"
        payload_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        signature_path.write_text(json.dumps({
            "algorithm": "Ed25519",
            "canonicalization": "sorted-compact-json-v1",
            "domain": DOMAIN,
            "key_id": payload["key_id"],
            "payload_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "signature_base64url": base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
        }, sort_keys=True), encoding="utf-8")
        envelope_path.write_text(json.dumps({
            "schema_version": 1,
            "trust_mode": "local_controlled_same_user",
            "payload_path": str(payload_path),
            "payload_sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            "signature_path": str(signature_path),
            "signature_sha256": hashlib.sha256(signature_path.read_bytes()).hexdigest(),
            "public_key_path": str(self.public_path),
            "public_key_fingerprint_sha256": self.fingerprint,
        }, sort_keys=True), encoding="utf-8")
        return envelope_path

    def _validate(self, envelope: Path | None = None, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "envelope_path": envelope or self.envelope,
            "project_root": self.project,
            "trusted_public_key_path": self.public_path,
            "expected_public_key_fingerprint": self.fingerprint,
            "expected_registry_path": self.registry_path,
            "expected_module_key": "M11",
            "expected_agent_handle": "/root/m11-writer",
            "expected_run_id": "run-m11-01",
            "expected_code_version": "m11-local-01",
            "expected_build_id": "build-m11-01",
            "now": NOW,
        }
        arguments.update(overrides)
        return validate_module_lease_envelope(**arguments)


class LocalControlledModuleLeaseRuntimeTests(ModuleLeaseFixture):
    def test_valid_lease_validates_and_activates_once(self) -> None:
        validated = self._validate()
        self.assertFalse(self.registry_path.exists())
        activated = activate_signed_module_lease(validated, self.registry_path, NOW)
        self.assertEqual("active", activated["status"])
        registry = ModuleLeaseRegistry(self.registry_path, self.project)
        registry.require_active(validated, NOW)
        with self.assertRaisesRegex(LocalControlledTrustError, "replayed-receipt"):
            activate_signed_module_lease(validated, self.registry_path, NOW)

    def test_candidate_code_and_build_bindings_are_exact(self) -> None:
        for field in ("base_candidate_sha256", "post_candidate_sha256"):
            with self.subTest(field=field):
                payload = dict(self.payload, **{field: "f" * 64})
                with self.assertRaisesRegex(
                    LocalControlledTrustError, "candidate-binding-mismatch",
                ):
                    self._validate(self._write(payload, f"-{field}"))
        with self.assertRaisesRegex(LocalControlledTrustError, "code-version-mismatch"):
            self._validate(expected_code_version="other-code")
        with self.assertRaisesRegex(LocalControlledTrustError, "build-id-mismatch"):
            self._validate(expected_build_id="other-build")

    def test_cross_registry_fails_before_creating_or_touching_other_registry(self) -> None:
        validated = self._validate()
        other = self.external / "other-registry.json"
        with self.assertRaisesRegex(LocalControlledTrustError, "registry-path-mismatch"):
            activate_signed_module_lease(validated, other, NOW)
        self.assertFalse(other.exists())
        self.assertFalse(other.with_name(other.name + ".lock").exists())

    def test_receipt_nonce_and_lease_ids_are_independently_global(self) -> None:
        first = self._validate()
        activate_signed_module_lease(first, self.registry_path, NOW)
        for index, field in enumerate(("receipt_id", "nonce", "lease_id"), start=1):
            mutated = dict(self.payload)
            mutated.update({
                "module_key": f"M{11 + index}",
                "stable_title": f"module-{index}",
                "agent_handle": f"/root/other-{index}",
                "run_id": f"run-other-{index}",
                "receipt_id": f"receipt-other-{index}",
                "nonce": str(index + 1) * 64,
                "lease_id": f"lease-other-{index}",
            })
            mutated[field] = self.payload[field]
            envelope = self._write(mutated, str(index))
            value = self._validate(
                envelope,
                expected_module_key=mutated["module_key"],
                expected_agent_handle=mutated["agent_handle"],
                expected_run_id=mutated["run_id"],
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                LocalControlledTrustError, "replayed-receipt",
            ):
                activate_signed_module_lease(value, self.registry_path, NOW)

    def test_unique_active_and_cross_module_agent_run_reuse_fail(self) -> None:
        first = self._validate()
        activate_signed_module_lease(first, self.registry_path, NOW)
        cases = (
            {"receipt_id": "receipt-double", "nonce": "b" * 64,
             "lease_id": "lease-double", "agent_handle": "/root/second", "run_id": "run-second"},
            {"receipt_id": "receipt-agent", "nonce": "c" * 64, "lease_id": "lease-agent",
             "module_key": "M12", "stable_title": "M12", "run_id": "run-third"},
            {"receipt_id": "receipt-run", "nonce": "d" * 64, "lease_id": "lease-run",
             "module_key": "M13", "stable_title": "M13", "agent_handle": "/root/third"},
        )
        for index, changes in enumerate(cases):
            payload = dict(self.payload, **changes)
            envelope = self._write(payload, f"active-{index}")
            value = self._validate(
                envelope,
                expected_module_key=payload["module_key"],
                expected_agent_handle=payload["agent_handle"],
                expected_run_id=payload["run_id"],
            )
            with self.subTest(index=index), self.assertRaisesRegex(
                LocalControlledTrustError, "active-lease-conflict",
            ):
                activate_signed_module_lease(value, self.registry_path, NOW)

    def test_ttl_role_boolean_and_base64_are_strict(self) -> None:
        for changes in (
            {"ttl_seconds": 901, "expires_at": "2026-09-03T08:15:01Z"},
            {"ttl_seconds": True},
            {"role": "review"},
            {"authorized_actions": ["close"]},
            {"explicit_user_authorization": 1},
        ):
            payload = dict(self.payload, **changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(
                LocalControlledTrustError, "invalid-module-lease",
            ):
                self._validate(self._write(payload, "strict-" + str(len(str(changes)))))
        signature_path = self.external / "signature.json"
        signature = json.loads(signature_path.read_text())
        signature["signature_base64url"] = "A"
        signature_path.write_text(json.dumps(signature))
        envelope = json.loads(self.envelope.read_text())
        envelope["signature_sha256"] = hashlib.sha256(signature_path.read_bytes()).hexdigest()
        self.envelope.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-module-lease-signature"):
            self._validate()

    def test_expired_lease_cannot_apply_and_allows_new_active_lease(self) -> None:
        first = self._validate()
        activate_signed_module_lease(first, self.registry_path, NOW)
        after_expiry = datetime(2026, 9, 3, 8, 16, tzinfo=timezone.utc)
        with self.assertRaisesRegex(LocalControlledTrustError, "lease-expired"):
            ModuleLeaseRegistry(self.registry_path, self.project).require_active(first, after_expiry)

    def test_registry_hash_chain_tamper_fails_closed(self) -> None:
        activate_signed_module_lease(self._validate(), self.registry_path, NOW)
        registry = json.loads(self.registry_path.read_text())
        registry["events"][0]["module_key"] = "M99"
        self.registry_path.write_text(json.dumps(registry))
        with self.assertRaisesRegex(LocalControlledTrustError, "invalid-lease-registry"):
            ModuleLeaseRegistry(self.registry_path, self.project).require_active(
                self.payload, NOW,
            )

    def test_guarded_apply_rechecks_drift_overreach_and_active_lease(self) -> None:
        value = self._validate()
        activate_signed_module_lease(value, self.registry_path, NOW)
        outside = self.project / "outside.md"
        outside.write_text("before\n")
        with self.assertRaisesRegex(LocalControlledTrustError, "target-not-authorized"):
            apply_signed_module_write(
                value, self.registry_path, outside, self.replacement,
                "write_module_artifacts", NOW,
            )
        self.agents.write_text(self.agents.read_text() + "drift\n")
        with self.assertRaisesRegex(LocalControlledTrustError, "policy-drift"):
            apply_signed_module_write(
                value, self.registry_path, self.target, self.replacement,
                "write_module_artifacts", NOW,
            )
        self.assertEqual("before\n", self.target.read_text())

    def test_guarded_apply_detects_target_inode_race(self) -> None:
        value = self._validate()
        activate_signed_module_lease(value, self.registry_path, NOW)
        original = os.lstat
        calls = 0

        def racing_lstat(path: object) -> os.stat_result:
            nonlocal calls
            result = original(path)
            if Path(path) == self.target:
                calls += 1
                if calls == 3:
                    self.target.unlink()
                    self.target.write_text("before\n")
            return result

        with mock.patch("local_controlled_path_safety.os.lstat", side_effect=racing_lstat):
            with self.assertRaises(LocalControlledTrustError):
                apply_signed_module_write(
                    value, self.registry_path, self.target, self.replacement,
                    "write_module_artifacts", NOW,
                )

    def test_registry_failure_after_file_write_reports_partial(self) -> None:
        value = self._validate()
        activate_signed_module_lease(value, self.registry_path, NOW)
        with mock.patch.object(
            ModuleLeaseRegistry, "record_apply",
            side_effect=LocalControlledTrustError("registry-persistence-failed"),
        ):
            result = apply_signed_module_write(
                value, self.registry_path, self.target, self.replacement,
                "write_module_artifacts", NOW,
            )
        self.assertEqual({
            "status": "PARTIAL", "complete": False,
            "error": "registry-persistence-failed",
        }, result)
        self.assertEqual("after\n", self.target.read_text())


if __name__ == "__main__":
    unittest.main()
