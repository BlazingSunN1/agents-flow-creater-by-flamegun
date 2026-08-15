from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_skill import build_checks


class SkillValidationTests(unittest.TestCase):
    def test_one_command_gate_contains_all_required_layers(self) -> None:
        checks = dict(build_checks())
        self.assertEqual(
            {"skill-package", "code-structure", "cli-smoke", "unit-regression", "mutation", "swimlane-js-syntax"},
            set(checks),
        )
        self.assertIn("quick_validate.py", " ".join(checks["skill-package"]))
        self.assertIn("run_mutation_checks.py", " ".join(checks["mutation"]))
        self.assertEqual(["node", "--check", "scripts/browser_test_swimlane.mjs"], checks["swimlane-js-syntax"])

    def test_default_loaded_surfaces_do_not_expose_sensitive_configuration_details(self) -> None:
        surfaces = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "agents" / "openai.yaml",
            SKILL_ROOT / "assets" / "AGENTS.template.md",
            SKILL_ROOT / "assets" / "AGENTS.optional-sections.md",
            SKILL_ROOT / "assets" / "generate-agents-md-swimlanes.html",
        ]
        forbidden = (
            "--allow-passwords",
            "password_uri_credentials",
            "stored passwords",
            "URI 内嵌",
            "授权密码",
            "密码授权",
            "Access Token",
            "Client Secret",
            "Authorization",
            "私钥",
            "凭据",
        )
        for surface in surfaces:
            text = surface.read_text(encoding="utf-8")
            for marker in forbidden:
                with self.subTest(surface=surface.name, marker=marker):
                    self.assertNotIn(marker, text)

    def test_general_reference_is_separated_from_explicit_sensitive_policy(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        general = (SKILL_ROOT / "references" / "extraction-checklist.md").read_text(encoding="utf-8")
        policy_path = SKILL_ROOT / "references" / "sensitive-configuration-policy.md"
        self.assertTrue(policy_path.is_file())
        self.assertIn("references/extraction-checklist.md", skill)
        self.assertIn("references/sensitive-configuration-policy.md", skill)
        for marker in ("--allow-passwords", "URI 内嵌", "password, passwd", "密码授权", "Authorized endpoints"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, general)

    def test_sensitive_policy_review_route_is_reachable_without_write_authorization(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("明确要求只读审查该策略或隔离效果", skill)

    def test_heavy_contracts_use_progressive_disclosure(self) -> None:
        skill_path = SKILL_ROOT / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        self.assertLessEqual(len(skill.encode("utf-8")), 12_000)
        self.assertLessEqual(max(map(len, skill.splitlines())), 900)
        for relative in (
            "references/multi-model-review-policy.md",
            "references/evidence-reuse-policy.md",
            "references/browser-validation-policy.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((SKILL_ROOT / relative).is_file())
                self.assertIn(relative, skill)

    def test_reuse_source_context_template_is_routed(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("assets/reuse-source-context.template.md", skill)

    def test_general_checklist_routes_heavy_contracts_without_copying_details(self) -> None:
        checklist = (SKILL_ROOT / "references" / "extraction-checklist.md").read_text(encoding="utf-8")
        for relative in (
            "references/evidence-reuse-policy.md",
            "references/browser-validation-policy.md",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, checklist)
        for detail in ("reuse-evidence.template.json", "browser:control-in-app-browser", "IDAT", "file://"):
            with self.subTest(detail=detail):
                self.assertNotIn(detail, checklist)


if __name__ == "__main__":
    unittest.main()
