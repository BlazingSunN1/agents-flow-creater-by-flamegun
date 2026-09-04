from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


HTML = (Path(__file__).resolve().parent.parent / "assets/generate-agents-md-swimlanes.html").read_text(encoding="utf-8")
SCRIPT_ROOT = Path(__file__).resolve().parent
BROWSER_TEST = (SCRIPT_ROOT / "browser_test_swimlane.mjs").read_text(encoding="utf-8")
NATIVE_SKILL_ROOT = SCRIPT_ROOT.parent.parent / "native-gpt-review-loop"
NATIVE_SKILL = (NATIVE_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
NATIVE_AGENT_CONFIG = (NATIVE_SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
AGENTS_TEMPLATE = (SCRIPT_ROOT.parent / "assets/AGENTS.template.md").read_text(encoding="utf-8")
sys.path.insert(0, str(SCRIPT_ROOT))


class SwimlaneHtmlContractTests(unittest.TestCase):
    def test_every_module_has_navigation_drilldown_and_back_link(self) -> None:
        for module_id in ("module-m00", "module-m01", "module-m02", "module-m03", "module-m04"):
            self.assertGreaterEqual(HTML.count(f'data-open-module="{module_id}"'), 2)
            self.assertIn(f'<details id="{module_id}"', HTML)
        self.assertEqual(5, HTML.count('class="back-link"'))

    def test_click_script_enforces_single_open_module_and_back_closure(self) -> None:
        self.assertIn("detail.open = detail.id === moduleId", HTML)
        self.assertIn('document.querySelectorAll(".back-link").forEach', HTML)
        self.assertIn("const closeLinkedModule = (event) => {", HTML)
        self.assertIn('link.addEventListener("click", closeLinkedModule)', HTML)
        self.assertIn('location.hash = "system-overview"', HTML)
        self.assertIn('showOnlyModule(target instanceof HTMLDetailsElement ? target.id : "")', HTML)
        self.assertIn('addEventListener("hashchange", syncModuleToHash)', HTML)

    def test_lane_headers_and_connectors_exist_for_overview_and_modules(self) -> None:
        self.assertGreaterEqual(HTML.count('class="lane-head"'), 19)
        self.assertGreaterEqual(HTML.count('class="flow"'), 7)
        self.assertGreaterEqual(HTML.count('class="module-flow"'), 30)

    def test_current_write_and_release_boundaries_are_visible(self) -> None:
        self.assertIn("写前校验模块写域", HTML)
        self.assertIn("干净 Git 提交", HTML)

    def test_page_is_self_contained_and_uses_required_palette_and_weight(self) -> None:
        self.assertIsNone(re.search(r'<(?:script|link|img)[^>]+(?:src|href)="https?://', HTML))
        self.assertIn('<link rel="icon" href="data:,">', HTML)
        self.assertIn("--coral:", HTML)
        self.assertIn("--mustard:", HTML)
        self.assertIn("font-weight: 800", HTML)

    def test_replayable_browser_test_uses_playwright_click_keyboard_and_visibility_assertions(self) -> None:
        self.assertIn("tab.playwright.locator", BROWSER_TEST)
        self.assertIn("独立写系统清单", BROWSER_TEST)
        self.assertIn("Dispatcher 只读重验", BROWSER_TEST)
        self.assertIn('.click()', BROWSER_TEST)
        self.assertIn('.press("Enter")', BROWSER_TEST)
        self.assertIn('for (const key of ["Enter", " "])', BROWSER_TEST)
        self.assertIn("keyboard back closure failed", BROWSER_TEST)
        self.assertIn('state.hash !== "#system-overview"', BROWSER_TEST)
        self.assertIn("openCount !== 1", BROWSER_TEST)
        self.assertIn("tab.dev.logs", BROWSER_TEST)

    def test_replayable_browser_test_rejects_file_scheme(self) -> None:
        self.assertIn("new URL(url)", BROWSER_TEST)
        self.assertIn('["http:", "https:"]', BROWSER_TEST)
        self.assertIn("credentials", BROWSER_TEST)
        self.assertIn("unsupported browser URL", BROWSER_TEST)

    def test_native_sol_review_lane_has_bounded_incomplete_and_hash_gate(self) -> None:
        self.assertIn("最多 6 轮", HTML)
        self.assertIn("incomplete", HTML)
        self.assertIn("同候选哈希门禁", HTML)
        self.assertIn("Kimi/DeepSeek 外部调用保持暂停", HTML)
        self.assertIn("Sol 方案作者（只读）", HTML)
        self.assertIn("Sol 黑盒审查（只读）", HTML)
        self.assertIn("model=gpt-5.6-sol", HTML)
        self.assertIn("父/主/子层级不授予写权", HTML)
        self.assertIn("唯一活动模块协调租约", HTML)
        self.assertIn("默认本地协调，严格模式才追加宿主证明", HTML)
        self.assertIn("仅登记的当前实现/维护 Agent 可写", HTML)
        self.assertIn("协调裁决 Agent/run 始终只读、永不持 writer lease", HTML)
        self.assertIn("Agent ID 与 run ID 必须同时不同于协调裁决者", HTML)
        self.assertIn("同一身份不得靠切换角色或 run 自审自写", HTML)
        self.assertIn("Dispatcher 也始终只读", HTML)
        self.assertIn("写者不得自审/黑盒/验收", HTML)
        self.assertNotIn("父维护 Agent 只裁决并写本模块", HTML)
        self.assertNotIn("只有已获派的模块维护 Agent 才作为父 GPT 裁决并对该模块唯一写入", HTML)
        self.assertIn("no parent, main, or child Agent has inherent write authority", NATIVE_SKILL)
        self.assertIn("current canonical module implementation or maintenance Agent", NATIVE_SKILL)
        self.assertIn("unique active module coordination lease", NATIVE_SKILL)
        self.assertIn("strict-security mode additionally host-attests", NATIVE_SKILL)
        self.assertIn("does not prove actual host runtime identity", NATIVE_SKILL)
        self.assertIn("public validator accepts an exact closed local receipt", NATIVE_SKILL)
        self.assertIn("strict-security mode additionally requires the trusted host verifier", NATIVE_SKILL)
        self.assertNotIn("project-authored receipts remain untrusted until the host verifier accepts them", NATIVE_SKILL)
        self.assertIn("Dispatcher and coordinator/adjudicator identities and runs are always read-only", NATIVE_SKILL)
        self.assertIn("same identity cannot switch roles to adjudicate and then write", NATIVE_SKILL)
        self.assertIn("must not review, black-box test, accept, or close its own delivery", NATIVE_SKILL)
        self.assertIn(
            "may only record the already-passed result of applicable independent gates",
            NATIVE_SKILL,
        )
        self.assertIn("must not independently adjudicate or close the module delivery", NATIVE_SKILL)
        self.assertNotIn("active parent GPT remains the final adjudicator and may write", NATIVE_SKILL)
        self.assertNotIn("Keep the active parent GPT as sole workspace writer", NATIVE_AGENT_CONFIG)
        self.assertIn("Hierarchy never grants write authority", NATIVE_AGENT_CONFIG)
        self.assertIn("a different independent read-only Agent validates the same code/build identity", AGENTS_TEMPLATE)
        self.assertIn("Use distinct Codex-native `gpt-5.6-sol` Agent/runs", AGENTS_TEMPLATE)
        self.assertIn("Drift, identity reuse or failed evidence blocks completion", AGENTS_TEMPLATE)
        self.assertNotIn("The parent GPT independently adjudicates both roles", AGENTS_TEMPLATE)
        template_ref = "../generate-agents-md/assets/native-review-loop-evidence.template.json"
        validator_ref = "../generate-agents-md/scripts/validate_native_review_loop.py"
        self.assertIn(template_ref, NATIVE_SKILL)
        self.assertIn(validator_ref, NATIVE_SKILL)
        self.assertTrue((NATIVE_SKILL_ROOT / template_ref).resolve().is_file())
        self.assertTrue((NATIVE_SKILL_ROOT / validator_ref).resolve().is_file())
        self.assertIn("maxRoundStop", BROWSER_TEST)
        self.assertIn("roleNeutralWriterLease", BROWSER_TEST)
        self.assertIn('m02Text.includes("协调裁决者始终只读且不持 writer lease")', BROWSER_TEST)
        self.assertIn('m02Text.includes("Agent ID 与 run ID 均不同")', BROWSER_TEST)
        self.assertIn('m02Text.includes("canonical 实现/维护 Agent")', BROWSER_TEST)
        self.assertIn('m02Text.includes("唯一活动模块协调租约")', BROWSER_TEST)
        self.assertIn('m02Text.includes("默认本地协调，严格模式才追加宿主证明")', BROWSER_TEST)
        self.assertIn('m02Text.includes("同一身份不得通过切换角色或 run 自审自写")', BROWSER_TEST)
        self.assertIn('m02Text.includes("Dispatcher 也始终只读")', BROWSER_TEST)
        self.assertIn('m02Text.includes("写者不得自审/黑盒/验收/裁决/关闭")', BROWSER_TEST)
        self.assertNotIn('includes("Dispatcher run 始终只读")', BROWSER_TEST)
        self.assertNotIn('includes("不同 implementation run/角色")', BROWSER_TEST)
        self.assertIn("写者不得自审/黑盒/验收/裁决/关闭", HTML)
        m02 = HTML.split('<details id="module-m02"', 1)[1].split("</details>", 1)[0]
        for phrase in (
            "协调裁决者始终只读且不持 writer lease",
            "Agent ID 与 run ID 均不同",
            "canonical 实现/维护 Agent",
            "唯一活动模块协调租约",
            "默认本地协调，严格模式才追加宿主证明",
            "同一身份不得通过切换角色或 run 自审自写",
            "Dispatcher 也始终只读",
            "写者不得自审/黑盒/验收/裁决/关闭",
        ):
            self.assertIn(phrase, m02)

    def test_major_module_maintenance_lane_has_independent_acceptance_and_aggregate_gate(self) -> None:
        self.assertIn("M00 模块路由与闭环维护", HTML)
        self.assertIn("模块维护 Agent（单写者）", HTML)
        self.assertIn("独立验收 Agent（只读）", HTML)
        self.assertIn("所有受影响模块", HTML)
        self.assertIn("moduleClosure", BROWSER_TEST)
        self.assertIn('id="m00-system-delivery"', HTML)
        self.assertIn('id="m00-module-return"', HTML)
        self.assertIn("standardDecisionBranches", BROWSER_TEST)

    def test_overview_routes_m04_through_system_aggregate_before_delivery(self) -> None:
        self.assertIn('id="overview-system-aggregate"', HTML)
        self.assertIn('id="overview-to-system-aggregate"', HTML)
        self.assertIn('id="overview-system-aggregate-to-delivery"', HTML)
        self.assertIn("overviewSystemAggregate", BROWSER_TEST)

    def test_m04_requires_closed_output_result_before_pass_decision(self) -> None:
        m04 = HTML.split('<details id="module-m04"', 1)[1].split("</details>", 1)[0]
        self.assertIn('id="m04-output-result"', m04)
        self.assertIn('id="m04-output-result-to-decision"', m04)
        self.assertIn("codex-native-output-result", m04)
        self.assertIn("严格模式追加宿主证明", m04)
        self.assertIn("gateOutputAttestation", BROWSER_TEST)
        self.assertIn("semanticSwimlaneBatching", BROWSER_TEST)

    def test_swimlane_frequency_uses_semantic_batching(self) -> None:
        for phrase in (
            "flow_impact=none|changed|uncertain",
            "有适用泳道且无变化时保留图内容和哈希",
            "稳定候选",
            "首次下游依赖或阶段交接前至多写图一次",
            "阶段结束只对适用泳道校验新鲜度",
            "系统总览只随系统或跨模块边界变化",
            "先判定 swimlane_applicable",
            "无适用泳道时无图无门禁",
            "稳定候选批量写图",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, HTML)
        for phrase in (
            'id="m03-review-trigger"',
            'id="m03-trigger-review"',
            'id="m03-trigger-continue"',
            'id="m03-review-pass-decision"',
            "闭环候选或人工",
            "继续实现，仅累计增量",
            "结论失效后重审",
        ):
            with self.subTest(review_trigger=phrase):
                self.assertIn(phrase, HTML)
        self.assertNotIn("每次代码模块修改后仍自动审查", HTML)

    def test_m03_visualizes_read_only_planning_receipt_binding_and_precise_triggers(self) -> None:
        m03 = HTML.split('<details id="module-m03"', 1)[1].split("</details>", 1)[0]
        for phrase in (
            "门禁规划器只读输出",
            "唯一租约写者 CAS 合并",
            "每个可执行门禁 receipt 绑定当前输入指纹",
            "最终聚合校验只在闭环或完成阶段接收同一交付契约",
            "实时执行且无自引用 receipt",
            "移动 Web 运行浏览器移动门禁",
            "原生移动运行 native_mobile_tests",
            "跨端变更同时运行两套门禁",
            "逐项绑定实际工件",
            "人工触发由独立审查者执行",
            "只要求当前阶段已经到达的业务 receipt 与审查 receipt",
            "不提前触发最终聚合",
            "有适用泳道且无流程变化才运行 swimlane_freshness",
            "普通用户可见文本不自动启动 UI/UX 原型 Agent",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, m03)
        self.assertIn("deterministicGateIntegrity", BROWSER_TEST)
        self.assertIn("最终聚合校验只在闭环或完成阶段接收同一交付契约", BROWSER_TEST)
        self.assertIn("不提前触发最终聚合", BROWSER_TEST)
        self.assertNotIn("最终聚合校验必须接收同一交付契约", BROWSER_TEST)

    def test_m03_visualizes_result_first_freeze_then_harden_sequence(self) -> None:
        m03 = HTML.split('<details id="module-m03"', 1)[1].split("</details>", 1)[0]
        for marker in (
            'id="m03-minimum-result"',
            'id="m03-affected-checks"',
            'id="m03-freeze-result"',
            'id="m03-harden-after-freeze"',
            'id="m03-regression-preservation"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, m03)
        expected_edges = (
            ('m03-minimum-result', 'm03-affected-checks'),
            ('m03-affected-checks', 'm03-freeze-result'),
            ('m03-freeze-result', 'm03-harden-after-freeze'),
            ('m03-harden-after-freeze', 'm03-mapped-verification'),
            ('m03-mapped-verification', 'm03-regression-preservation'),
        )
        for source, target in expected_edges:
            with self.subTest(source=source, target=target):
                self.assertIn(f'data-from="{source}" data-to="{target}"', m03)
        for phrase in (
            "真实入口跑通最小业务流程",
            "冻结代码版本、Build ID、验收命令、可观测结果和证据 SHA-256",
            "冻结后才启动非必要门禁",
            "发生回归时先恢复最小业务闭环",
            "治理完整或门禁通过不能替代业务成果",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, m03)
        self.assertIn("resultFirstHardening", BROWSER_TEST)

    def test_validation_summary_tracks_invariants_without_frozen_counts(self) -> None:
        from run_mutation_checks import MUTANTS

        self.assertGreaterEqual(unittest.defaultTestLoader.discover(
            str(SCRIPT_ROOT), pattern="test_*.py",
        ).countTestCases(), 800)
        self.assertGreaterEqual(len(MUTANTS), 450)
        self.assertNotIn("820 项", HTML)
        self.assertNotIn("496 个", HTML)
        self.assertIn("数量不写入规范", HTML)
        self.assertNotIn("700 项", HTML)
        self.assertNotIn("698 项", HTML)
        self.assertNotIn("696 项", HTML)
        self.assertIn(
            "独立通过只授权记录结果，不授权 writer 自审/黑盒/验收/裁决/关闭/完成/接受",
            HTML,
        )
        self.assertNotIn("独立审查条件的正向完成/通过/成功证明", HTML)
        self.assertNotIn("同主语合法条件不误报", HTML)
        self.assertNotIn("392 个", HTML)
        self.assertNotIn("691 项", HTML)
        self.assertNotIn("390 个", HTML)
        self.assertNotIn("660 项", HTML)

    def test_validation_tiers_and_strict_security_route_are_visible(self) -> None:
        self.assertIn("validate_skill.py --quick", HTML)
        self.assertIn("--affected", HTML)
        self.assertIn("validate_skill.py --full", HTML)
        self.assertIn("未知映射自动升级", HTML)
        self.assertIn("最多3轮/同错2次", HTML)
        self.assertIn("快速检查不能作为闭环、发布或安装验收", HTML)
        self.assertIn("严格安全正文按触发条件独立加载", HTML)
        self.assertIn('overviewText.includes("validate_skill.py --quick")', BROWSER_TEST)
        self.assertIn('overviewText.includes("validate_skill.py --full")', BROWSER_TEST)
        self.assertNotIn("376 个", HTML)


if __name__ == "__main__":
    unittest.main()
