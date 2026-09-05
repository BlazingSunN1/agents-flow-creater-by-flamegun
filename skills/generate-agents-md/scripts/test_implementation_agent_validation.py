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
        self.assertEqual("gpt-6-astra", template["recorded_model"])
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


if __name__ == "__main__":
    unittest.main()
