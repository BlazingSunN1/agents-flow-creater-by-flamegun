from __future__ import annotations

import hashlib
import inspect
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from implementation_agent_validation import validate_implementation_agent
from test_validate_delivery_bundle import DeliveryBundleValidatorTests
from validate_context_manifest import _parse_metadata
from test_writer_authorization_support import write_historical_qwen_write_proof


class ImplementationAgentPublicBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = DeliveryBundleValidatorTests()
        self.fixture.setUp()
        self.data = json.loads(self.fixture.multi_agent.read_text(encoding="utf-8"))
        self.context, _ = _parse_metadata(self.fixture.context.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_public_api_rejects_host_verifier_injection(self) -> None:
        self.assertNotIn("host_attestation_verifier", inspect.signature(validate_implementation_agent).parameters)
        with self.assertRaises(TypeError):
            validate_implementation_agent(
                self.data, self.context, self.fixture.root,
                host_attestation_verifier=lambda *_: True,
            )

    def test_public_api_accepts_structurally_bound_local_coordination_receipt(self) -> None:
        codes = {
            issue.code
            for issue in validate_implementation_agent(self.data, self.context, self.fixture.root)
        }
        self.assertNotIn("implementation-receipt-not-validated", codes)
        self.data["implementation_agent_reasoning_effort"] = "high"
        codes = {
            issue.code
            for issue in validate_implementation_agent(self.data, self.context, self.fixture.root)
        }
        self.assertIn("invalid-implementation-agent-effort", codes)

    def test_local_receipt_uses_neutral_recorded_claims(self) -> None:
        template = json.loads(
            (Path(__file__).resolve().parents[1] / "assets" / "implementation-spawn-receipt.template.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual("gpt-5.6-sol", template["recorded_model"])
        self.assertEqual("medium", template["recorded_reasoning_effort"])
        self.assertNotIn("machine_verified_model", template)
        self.assertNotIn("machine_verified_reasoning_effort", template)

        receipt = self.fixture.root / str(self.data["implementation_spawn_receipt"])
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["recorded_model"] = "gpt-5.6-terra"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        self.data["implementation_spawn_receipt_sha256"] = hashlib.sha256(
            receipt.read_bytes()
        ).hexdigest()
        issues = validate_implementation_agent(self.data, self.context, self.fixture.root)
        message = next(
            issue.message for issue in issues
            if issue.code == "invalid-implementation-spawn-receipt"
        )
        self.assertIn("封闭 receipt", message)
        self.assertIn("声明身份", message)
        self.assertNotIn("可信身份", message)

    def test_writable_implementation_schema_v1_cannot_bypass_source_and_proof(self) -> None:
        self.data["schema_version"] = 1
        issues = validate_implementation_agent(self.data, self.context, self.fixture.root)
        self.assertIn(
            "invalid-implementation-runtime-binding",
            {issue.code for issue in issues},
        )

    def test_explicit_qwen_q8_xhigh_policy_closes_implementation_receipt(self) -> None:
        proof = write_historical_qwen_write_proof(
            self.fixture.root, module_key="module",
            maintainer_title=str(self.data["implementation_agent_title"]),
            owned_paths=list(self.data["owned_paths"]),
            agent_id=str(self.data["implementation_agent_id"]),
            run_id=str(self.data["implementation_run_id"]),
            lease_id="lease-impl-qwen-history",
            target_path=str(self.data["implementation_write_proof"]["target_path"]),
            baseline_sha256=str(self.data["baseline_sha256"]),
            code_version=str(self.data["code_version"]),
            build_id=str(self.data["build_id"]),
            candidate_sha256=str(self.data["candidate_sha256"]),
        )
        self.data.update({
            "implementation_agent_provider": "ollama_local",
            "implementation_agent_model": "qwen3.8:27b-q8_0",
            "implementation_agent_reasoning_effort": "xhigh",
            "implementation_write_proof": proof,
        })
        receipt = self.fixture.root / str(self.data["implementation_spawn_receipt"])
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload.update({
            "provider": "ollama_local", "requested_model": "qwen3.8:27b-q8_0",
            "recorded_model": "qwen3.8:27b-q8_0",
            "requested_reasoning_effort": "xhigh", "recorded_reasoning_effort": "xhigh",
            "historical_write_proof": proof,
        })
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        self.data["implementation_spawn_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        codes = {issue.code for issue in validate_implementation_agent(
            self.data, self.context, self.fixture.root,
        )}
        self.assertFalse({
            "invalid-implementation-agent", "invalid-implementation-agent-effort",
            "implementation-write-proof-invalid", "invalid-implementation-spawn-receipt",
        } & codes)

    def test_implicit_qwen_declaration_with_sol_proof_is_rejected(self) -> None:
        self.data.update({
            "implementation_agent_provider": "ollama_local",
            "implementation_agent_model": "qwen3.8:27b-q8_0",
            "implementation_agent_reasoning_effort": "xhigh",
        })
        codes = {issue.code for issue in validate_implementation_agent(
            self.data, self.context, self.fixture.root,
        )}
        self.assertIn("invalid-implementation-agent", codes)


if __name__ == "__main__":
    unittest.main()
