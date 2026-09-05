from __future__ import annotations

import json
import unittest
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "assets"


class NativeModelDefaultTests(unittest.TestCase):
    def test_spawn_templates_pin_gpt6_and_role_specific_effort(self) -> None:
        for name, effort in (
            ("implementation", "medium"),
            ("system-aggregation", "medium"),
            ("independent-gate", "high"),
            ("dispatcher", "high"),
        ):
            with self.subTest(role=name):
                data = json.loads((ASSETS / f"{name}-spawn-receipt.template.json").read_text())
                for prefix in ("requested", "recorded"):
                    self.assertEqual("gpt-6-astra", data[f"{prefix}_model"])
                    self.assertEqual(effort, data[f"{prefix}_reasoning_effort"])

    def test_module_and_gate_templates_keep_different_efforts(self) -> None:
        data = json.loads((ASSETS / "multi-agent-evidence.template.json").read_text())
        self.assertEqual("gpt-6-astra", data["implementation_agent_model"])
        self.assertEqual("medium", data["implementation_agent_reasoning_effort"])
        for gate in data["gates"]:
            self.assertEqual("gpt-6-astra", gate["agent_model"])
            self.assertEqual("high", gate["agent_reasoning_effort"])


if __name__ == "__main__":
    unittest.main()
