from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
SCRIPT_ROOT = Path(__file__).resolve().parent


class LocalControlledModuleLeaseContractTests(unittest.TestCase):
    def _json(self, name: str) -> dict[str, object]:
        return json.loads((ASSET_ROOT / name).read_text(encoding="utf-8"))

    def test_bootstrap_v2_contract_is_closed_and_does_not_reinterpret_v1(self) -> None:
        v1 = self._json("system-governance-bootstrap-receipt.schema.json")
        v2 = self._json("system-governance-bootstrap-v2-receipt.schema.json")
        template = self._json("system-governance-bootstrap-v2-receipt.template.json")
        self.assertEqual(1, v1["properties"]["schema_version"]["const"])
        self.assertEqual(2, v2["properties"]["schema_version"]["const"])
        self.assertFalse(v2["additionalProperties"])
        self.assertEqual(
            "local-controlled-module-write-lease-required",
            v2["properties"]["next_authority"]["const"],
        )
        self.assertEqual(
            ["AGENTS.md", "docs/agents/module-agent-governance.md"],
            [item["path"] for item in template["governance_targets"]],
        )
        self.assertEqual(
            set(v2["required"]), set(template),
        )

    def test_module_lease_assets_are_closed_and_use_an_independent_domain(self) -> None:
        lease = self._json("local-controlled-module-write-lease.schema.json")
        template = self._json("local-controlled-module-write-lease.template.json")
        envelope = self._json("local-controlled-module-lease-envelope.schema.json")
        signature = self._json("local-controlled-module-lease-detached-signature.schema.json")
        registry = self._json("local-controlled-module-lease-registry.schema.json")
        for value in (lease, envelope, signature, registry):
            self.assertFalse(value["additionalProperties"])
        self.assertEqual(set(lease["required"]), set(template))
        self.assertEqual(
            "generate-agents-md/local-controlled-module-write-lease/v1",
            signature["properties"]["domain"]["const"],
        )
        self.assertNotEqual(
            "generate-agents-md/local-controlled-trust/v1",
            signature["properties"]["domain"]["const"],
        )
        self.assertEqual(900, lease["properties"]["ttl_seconds"]["maximum"])
        self.assertEqual(60, lease["properties"]["ttl_seconds"]["minimum"])
        self.assertNotIn("revocation", json.dumps(lease))
        pattern = signature["properties"]["signature_base64url"]["pattern"]
        self.assertIsNone(re.fullmatch(pattern, "A"))

    def test_public_cli_and_guarded_apply_entrypoints_exist(self) -> None:
        for name in (
            "validate_local_controlled_module_lease.py",
            "activate_local_controlled_module_lease.py",
            "apply_local_controlled_module_write.py",
            "apply_system_governance_bootstrap_v2.py",
        ):
            with self.subTest(name=name):
                self.assertTrue((SCRIPT_ROOT / name).is_file())

    def test_docs_keep_local_controlled_boundary_explicit(self) -> None:
        root = ASSET_ROOT.parent
        text = "\n".join((
            (root / "SKILL.md").read_text(encoding="utf-8"),
            (root / "references/module-agent-governance.md").read_text(encoding="utf-8"),
            (root / "references/strict-security-governance.md").read_text(encoding="utf-8"),
            (root / "references/extraction-checklist.md").read_text(encoding="utf-8"),
        ))
        for phrase in (
            "local_controlled_module_write_lease",
            "authorization-mode=local-controlled-same-user",
            "PARTIAL",
            "15 分钟",
            "不证明 runtime",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
