from __future__ import annotations

import json
import unittest
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "assets"


class NativeModelDefaultTests(unittest.TestCase):
    def test_spawn_templates_pin_role_specific_model_and_effort(self) -> None:
        for name, model, effort in (
            ("implementation", "gpt-5.6-sol", "medium"),
            ("system-aggregation", "gpt-5.6-sol", "medium"),
            ("independent-gate", "gpt-6-astra", "high"),
            ("dispatcher", "gpt-6-astra", "high"),
        ):
            with self.subTest(role=name):
                data = json.loads((ASSETS / f"{name}-spawn-receipt.template.json").read_text())
                for prefix in ("requested", "recorded"):
                    self.assertEqual(model, data[f"{prefix}_model"])
                    self.assertEqual(effort, data[f"{prefix}_reasoning_effort"])

    def test_module_and_gate_templates_keep_different_efforts(self) -> None:
        data = json.loads((ASSETS / "multi-agent-evidence.template.json").read_text())
        self.assertEqual("gpt-5.6-sol", data["implementation_agent_model"])
        self.assertEqual("medium", data["implementation_agent_reasoning_effort"])
        for gate in data["gates"]:
            self.assertEqual("gpt-6-astra", gate["agent_model"])
            self.assertEqual("high", gate["agent_reasoning_effort"])


if __name__ == "__main__":
    unittest.main()
