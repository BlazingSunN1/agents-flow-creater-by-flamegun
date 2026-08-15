from __future__ import annotations

import re
import unittest
from pathlib import Path


HTML = (Path(__file__).resolve().parent.parent / "assets/generate-agents-md-swimlanes.html").read_text(encoding="utf-8")
BROWSER_TEST = (Path(__file__).resolve().parent / "browser_test_swimlane.mjs").read_text(encoding="utf-8")


class SwimlaneHtmlContractTests(unittest.TestCase):
    def test_every_module_has_navigation_drilldown_and_back_link(self) -> None:
        for module_id in ("module-m01", "module-m02", "module-m03", "module-m04"):
            self.assertGreaterEqual(HTML.count(f'data-open-module="{module_id}"'), 2)
            self.assertIn(f'<details id="{module_id}"', HTML)
        self.assertEqual(4, HTML.count('class="back-link"'))

    def test_click_script_enforces_single_open_module_and_back_closure(self) -> None:
        self.assertIn("detail.open = detail.id === moduleId", HTML)
        self.assertIn('showOnlyModule(target instanceof HTMLDetailsElement ? target.id : "")', HTML)
        self.assertIn('addEventListener("hashchange", syncModuleToHash)', HTML)

    def test_lane_headers_and_connectors_exist_for_overview_and_modules(self) -> None:
        self.assertGreaterEqual(HTML.count('class="lane-head"'), 19)
        self.assertGreaterEqual(HTML.count('class="flow"'), 7)
        self.assertGreaterEqual(HTML.count('class="module-flow"'), 30)

    def test_page_is_self_contained_and_uses_required_palette_and_weight(self) -> None:
        self.assertIsNone(re.search(r'<(?:script|link|img)[^>]+(?:src|href)="https?://', HTML))
        self.assertIn("--coral:", HTML)
        self.assertIn("--mustard:", HTML)
        self.assertIn("font-weight: 800", HTML)

    def test_replayable_browser_test_uses_playwright_click_keyboard_and_visibility_assertions(self) -> None:
        self.assertIn("tab.playwright.locator", BROWSER_TEST)
        self.assertIn('.click()', BROWSER_TEST)
        self.assertIn('.press("Enter")', BROWSER_TEST)
        self.assertIn("openCount !== 1", BROWSER_TEST)
        self.assertIn("tab.dev.logs", BROWSER_TEST)

    def test_replayable_browser_test_rejects_file_scheme(self) -> None:
        self.assertIn("new URL(url)", BROWSER_TEST)
        self.assertIn('["http:", "https:"]', BROWSER_TEST)
        self.assertIn("credentials", BROWSER_TEST)
        self.assertIn("unsupported browser URL", BROWSER_TEST)

    def test_external_review_lane_has_bounded_incomplete_and_hash_gate(self) -> None:
        self.assertIn("最多 6 轮", HTML)
        self.assertIn("incomplete", HTML)
        self.assertIn("同候选哈希门禁", HTML)
        self.assertIn("DeepSeek V4 外部子 Agent", HTML)
        self.assertIn("Thinking Max + JSON Output", HTML)
        self.assertIn("finish_reason=stop", HTML)
        self.assertIn("maxRoundStop", BROWSER_TEST)


if __name__ == "__main__":
    unittest.main()
