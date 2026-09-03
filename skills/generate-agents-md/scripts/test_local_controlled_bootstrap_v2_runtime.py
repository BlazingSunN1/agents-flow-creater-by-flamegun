from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_controlled_bootstrap_v2 import (
    LocalControlledTrustError,
    apply_bootstrap_v2,
    validate_bootstrap_v2_envelope,
)
from local_controlled_trust_validation import FileReplayGuard


NOW = datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)
DOMAIN = "generate-agents-md/system-governance-bootstrap/v2"


class BootstrapV2RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.external = self.root / "external"
        (self.project / "docs/agents").mkdir(parents=True)
        self.external.mkdir()
        self.agents = self.project / "AGENTS.md"
        self.governance = self.project / "docs/agents/module-agent-governance.md"
        self.pre_authority = "1" * 64
        self.post_authority = "2" * 64
        self.agents.write_text(self._agents(self.pre_authority, False), encoding="utf-8")
        self.governance.write_text("# governance\n\nM01 only\n", encoding="utf-8")
        self.agents_replacement = self.external / "AGENTS.next.md"
        self.governance_replacement = self.external / "governance.next.md"
        self.agents_replacement.write_text(
            self._agents(self.post_authority, True), encoding="utf-8",
        )
        self.governance_replacement.write_text(
            "# governance\n\nM11 本机受控运行时证明与写租约维护\n",
            encoding="utf-8",
        )
        self.replay = self.external / "bootstrap-replay.json"
        self.private = Ed25519PrivateKey.generate()
        self.public = self.external / "public.pem"
        self.public.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        self.fingerprint = hashlib.sha256(raw).hexdigest()
        self.baseline_sha = "3" * 64
        self.payload = self._payload()
        self.envelope = self._write_envelope(self.payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _agents(self, authority: str, include_m11: bool) -> str:
        rows = "| M01 | preflight | `src/m01.py` | M01 owner |\n"
        if include_m11:
            rows += (
                "| M11 | local lease | `docs/progress/m11.md`, "
                "`docs/context/m11.md` | M11 本机受控运行时证明与写租约维护 |\n"
            )
        return (
            f"authority_matrix_sha256: {authority}\n"
            "| Module | Scope | Owned project-relative paths | Long-term maintenance Agent title |\n"
            "| --- | --- | --- | --- |\n" + rows
        )

    def _target(self, path: Path, replacement: Path) -> dict[str, object]:
        before, after = path.read_bytes(), replacement.read_bytes()
        return {
            "path": str(path.relative_to(self.project)),
            "pre_sha256": hashlib.sha256(before).hexdigest(),
            "pre_size": len(before),
            "post_sha256": hashlib.sha256(after).hexdigest(),
            "post_size": len(after),
        }

    def _payload(self) -> dict[str, object]:
        targets = [
            self._target(self.agents, self.agents_replacement),
            self._target(self.governance, self.governance_replacement),
        ]
        candidate = hashlib.sha256(json.dumps(
            {"governance_targets": targets}, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        ).encode()).hexdigest()
        return {
            "schema_version": 2,
            "receipt_type": "system_governance_bootstrap_v2",
            "trust_mode": "local_controlled_same_user",
            "security_caveat": "same_os_user_can_access_private_key_not_host_native_attestation",
            "explicit_user_authorization": True,
            "authorization_source": "user-message-20260903",
            "issuer": "local-signer-01", "key_id": "key-01",
            "key_fingerprint_sha256": self.fingerprint,
            "agent_handle": "implementation-agent-01",
            "assigned_model": "gpt-5.6-sol", "assigned_reasoning_effort": "high",
            "role": "implementation", "project_root": str(self.project),
            "replay_state_path": str(self.replay),
            "module_registration": {
                "module_key": "M11",
                "stable_title": "M11 本机受控运行时证明与写租约维护",
                "owned_paths": ["docs/progress/m11.md", "docs/context/m11.md"],
            },
            "governance_targets": targets,
            "issued_at": "2026-09-03T08:59:00Z",
            "not_before": "2026-09-03T08:59:00Z",
            "expires_at": "2026-09-03T09:14:00Z",
            "nonce": "4" * 64, "receipt_id": "bootstrap-v2-receipt-01",
            "operation_id": "bootstrap-v2-operation-01", "one_time": True,
            "baseline_sha256": self.baseline_sha,
            "pre_policy_sha256": hashlib.sha256(self.agents.read_bytes()).hexdigest(),
            "post_policy_sha256": hashlib.sha256(
                self.agents_replacement.read_bytes(),
            ).hexdigest(),
            "pre_authority_matrix_sha256": self.pre_authority,
            "post_authority_matrix_sha256": self.post_authority,
            "bootstrap_candidate_sha256": candidate,
            "next_authority": "local-controlled-module-write-lease-required",
        }

    def _write_envelope(self, payload: dict[str, object]) -> Path:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()
        payload_path = self.external / "bootstrap-v2-payload.json"
        signature_path = self.external / "bootstrap-v2-signature.json"
        envelope_path = self.external / "bootstrap-v2-envelope.json"
        payload_path.write_bytes(canonical)
        signature = self.private.sign(DOMAIN.encode() + b"\0" + canonical)
        signature_doc = {
            "algorithm": "Ed25519", "canonicalization": "sorted-compact-json-v1",
            "domain": DOMAIN, "key_id": payload["key_id"],
            "payload_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "signature_base64url": base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
        }
        signature_bytes = json.dumps(
            signature_doc, sort_keys=True, separators=(",", ":"),
        ).encode()
        signature_path.write_bytes(signature_bytes)
        envelope = {
            "schema_version": 1, "trust_mode": "local_controlled_same_user",
            "payload_path": str(payload_path),
            "payload_sha256": hashlib.sha256(canonical).hexdigest(),
            "signature_path": str(signature_path),
            "signature_sha256": hashlib.sha256(signature_bytes).hexdigest(),
            "public_key_path": str(self.public),
            "public_key_fingerprint_sha256": self.fingerprint,
        }
        envelope_path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        return envelope_path

    def _validate(self, envelope: Path | None = None) -> dict[str, object]:
        return validate_bootstrap_v2_envelope(
            envelope_path=envelope or self.envelope, project_root=self.project,
            trusted_public_key_path=self.public,
            expected_public_key_fingerprint=self.fingerprint,
            expected_agent_handle="implementation-agent-01",
            expected_baseline_sha256=self.baseline_sha,
            now=NOW, replay_guard=FileReplayGuard(self.replay, self.project),
        )

    def test_valid_bootstrap_updates_only_governance_targets_and_not_owned_leaf(self) -> None:
        payload = self._validate()
        result = apply_bootstrap_v2(payload, {
            "AGENTS.md": self.agents_replacement,
            "docs/agents/module-agent-governance.md": self.governance_replacement,
        })
        self.assertEqual({"status": "APPLIED", "complete": True}, result)
        self.assertEqual(self.agents_replacement.read_bytes(), self.agents.read_bytes())
        self.assertEqual(self.governance_replacement.read_bytes(), self.governance.read_bytes())
        self.assertFalse((self.project / "docs/progress/m11.md").exists())
        self.assertFalse((self.project / "docs/context/m11.md").exists())

    def test_overlap_symlink_and_missing_target_fail_before_replay(self) -> None:
        mutations = []
        overlap = json.loads(json.dumps(self.payload))
        overlap["module_registration"]["owned_paths"] = ["src/m01.py"]
        mutations.append(("overlap", overlap))
        wrong_targets = json.loads(json.dumps(self.payload))
        wrong_targets["governance_targets"][1]["path"] = "docs/agents/missing.md"
        mutations.append(("targets", wrong_targets))
        for label, value in mutations:
            with self.subTest(label=label):
                envelope = self._write_envelope(value)
                with self.assertRaises(LocalControlledTrustError):
                    self._validate(envelope)
                self.assertFalse(self.replay.exists())

    def test_post_policy_authority_registration_and_candidate_are_bound(self) -> None:
        for field in (
            "post_policy_sha256", "post_authority_matrix_sha256",
            "bootstrap_candidate_sha256",
        ):
            with self.subTest(field=field):
                payload = dict(self.payload, **{field: "f" * 64})
                envelope = self._write_envelope(payload)
                if field == "bootstrap_candidate_sha256":
                    with self.assertRaisesRegex(LocalControlledTrustError, "candidate"):
                        self._validate(envelope)
                else:
                    validated = self._validate(envelope)
                    with self.assertRaises(LocalControlledTrustError):
                        apply_bootstrap_v2(validated, {
                            "AGENTS.md": self.agents_replacement,
                            "docs/agents/module-agent-governance.md": self.governance_replacement,
                        })
                if self.replay.exists():
                    self.replay.unlink()
                lock = self.replay.with_name(self.replay.name + ".lock")
                if lock.exists():
                    lock.unlink()

    def test_second_target_failure_reports_partial(self) -> None:
        payload = self._validate()
        module = __import__("local_controlled_bootstrap_v2")
        original = module._replace_one
        calls = 0

        def fail_second(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise LocalControlledTrustError("target-persistence-failed")
            original(*args, **kwargs)

        with mock.patch("local_controlled_bootstrap_v2._replace_one", side_effect=fail_second):
            result = apply_bootstrap_v2(payload, {
                "AGENTS.md": self.agents_replacement,
                "docs/agents/module-agent-governance.md": self.governance_replacement,
            })
        self.assertEqual({
            "status": "PARTIAL", "complete": False,
            "error": "target-persistence-failed", "applied_targets": 1,
        }, result)


if __name__ == "__main__":
    unittest.main()
