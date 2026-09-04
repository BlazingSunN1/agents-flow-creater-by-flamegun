from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_skill import (
    AFFECTED_ASSET_TESTS,
    CheckResult,
    _full_result_validity,
    _run_freeze_candidate,
    _run_full_once,
    build_checks,
    build_parser,
    candidate_sha256,
    effective_mode,
    full_execution_action,
    run_check,
)
from full_validation_receipt import (
    FULL_RECEIPT_SCHEMA_VERSION,
    VerifiedReceipt,
    write_full_receipt,
)


def _passing_full_results() -> list[CheckResult]:
    return [CheckResult(name, command, 0, 0.1, "")
            for name, command in build_checks(mode="full")]


def _passing_receipt(fingerprint: str, *, distributed: bool = False) -> dict[str, object]:
    checks = [{"name": item.name, "returncode": 0} for item in _passing_full_results()]
    if distributed:
        checks.append({"name": "plugin-distribution", "returncode": 0})
    return {
        "schema_version": FULL_RECEIPT_SCHEMA_VERSION,
        "skill_root": str(SKILL_ROOT.resolve()),
        "candidate_sha256": fingerprint,
        "frozen_at": "2026-09-04T00:00:00+00:00",
        "full_status": "pass",
        "distribution_status": "pass" if distributed else "not_requested",
        "checks": checks,
    }


def _write_frozen_proof(path: Path, fingerprint: str | None = None) -> None:
    write_full_receipt(path, {
        "schema_version": FULL_RECEIPT_SCHEMA_VERSION,
        "skill_root": str(SKILL_ROOT.resolve()),
        "candidate_sha256": fingerprint or candidate_sha256(SKILL_ROOT),
        "frozen_at": "2026-09-04T00:00:00+00:00",
        "full_status": "frozen",
        "distribution_status": "not_requested",
        "checks": [],
    })


class SkillValidationTests(unittest.TestCase):
    def test_one_command_gate_contains_all_required_layers(self) -> None:
        checks = dict(build_checks(mode="full"))
        self.assertEqual(
            {"skill-package", "code-structure", "cli-smoke", "unit-regression", "mutation", "swimlane-js-syntax"},
            set(checks),
        )
        self.assertIn("quick_validate.py", " ".join(checks["skill-package"]))
        self.assertIn("run_mutation_checks.py", " ".join(checks["mutation"]))
        self.assertEqual(["node", "--check", "scripts/browser_test_swimlane.mjs"], checks["swimlane-js-syntax"])

    def test_quick_gate_skips_long_layers_and_is_default(self) -> None:
        full = dict(build_checks(mode="full"))
        quick = dict(build_checks(mode="quick"))
        self.assertEqual(quick, dict(build_checks()))
        self.assertEqual(
            {"skill-package", "code-structure", "cli-smoke", "swimlane-js-syntax"},
            set(quick),
        )
        self.assertNotIn("unit-regression", quick)
        self.assertNotIn("mutation", quick)

        parser = build_parser()
        self.assertEqual("quick", parser.parse_args([]).mode)
        self.assertEqual("quick", parser.parse_args(["--quick"]).mode)
        self.assertEqual("freeze", parser.parse_args(["--freeze-candidate"]).mode)
        self.assertEqual("full", parser.parse_args(["--full"]).mode)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--quick", "--full"])

    def test_each_check_has_a_bounded_timeout(self) -> None:
        result = run_check(
            "timeout-probe",
            [sys.executable, "-c", "import time; time.sleep(1)"],
            SKILL_ROOT,
            timeout_seconds=0.05,
        )
        self.assertEqual(124, result.returncode)
        self.assertIn("timed out", result.output_tail)

        parser = build_parser()
        self.assertEqual(600.0, parser.parse_args([]).check_timeout_seconds)
        self.assertEqual(
            30.0,
            parser.parse_args(["--check-timeout-seconds", "30"]).check_timeout_seconds,
        )

    def test_affected_gate_selects_targeted_tests_and_shared_contract_escalates(self) -> None:
        checks = dict(build_checks(
            mode="affected",
            changed_files=("scripts/validate_frontend_evidence.py",),
        ))
        self.assertIn("affected-test:test_validate_frontend_evidence", checks)
        self.assertNotIn("unit-regression", checks)
        self.assertNotIn("mutation", checks)

        shared = dict(build_checks(
            mode="affected", changed_files=("scripts/validate_delivery_contract.py",),
        ))
        self.assertIn("unit-regression", shared)
        self.assertIn("mutation", shared)

        parser = build_parser()
        parsed = parser.parse_args([
            "--affected", "--changed-file", "scripts/validate_delivery_contract.py",
        ])
        self.assertEqual("affected", parsed.mode)
        self.assertEqual(["scripts/validate_delivery_contract.py"], parsed.changed_files)

    def test_unknown_affected_mapping_escalates_to_full(self) -> None:
        for changed in (
            ("scripts/new_shared_validator_without_test.py",),
            ("docs/delivery-contract-notes.md",),
            ("docs/unrelated.html",),
            ("scripts/unrelated.mjs",),
            (".../scripts/validate_frontend_evidence.py",),
        ):
            with self.subTest(changed=changed):
                checks = dict(build_checks(mode="affected", changed_files=changed))
                self.assertEqual("full", effective_mode(SKILL_ROOT, "affected", changed))
                self.assertIn("unit-regression", checks)
                self.assertIn("mutation", checks)

    def test_any_unknown_path_escalates_regardless_of_input_order(self) -> None:
        for changed in (
            ("SKILL.md", "scripts/new_shared_validator_without_test.py"),
            ("scripts/new_shared_validator_without_test.py", "SKILL.md"),
        ):
            with self.subTest(changed=changed):
                self.assertEqual("full", effective_mode(SKILL_ROOT, "affected", changed))

    def test_skill_and_references_use_affected_checks_while_shared_code_escalates(self) -> None:
        for changed in (("SKILL.md",), ("references/delivery-orchestration.md",)):
            with self.subTest(changed=changed):
                self.assertEqual("affected", effective_mode(SKILL_ROOT, "affected", changed))
                checks = dict(build_checks(mode="affected", changed_files=changed))
                self.assertNotIn("unit-regression", checks)
                self.assertNotIn("mutation", checks)

        for changed in (
            ("scripts/delivery_gate_planner.py",),
            ("scripts/validate_delivery_contract.py",),
            ("scripts/validate_skill.py",),
            ("scripts/validate_project_commands.py",),
            ("assets/delivery-contract.template.json",),
            ("assets/project-commands.template.json",),
        ):
            with self.subTest(changed=changed):
                self.assertEqual("full", effective_mode(SKILL_ROOT, "affected", changed))

    def test_semantic_assets_select_their_own_regression_suites(self) -> None:
        expectations = {
            "assets/AGENTS.template.md": {
                "affected-test:test_validate_agents_md",
                "affected-test:test_validate_skill",
            },
            "assets/requirement-questions.template.json": {
                "affected-test:test_validate_requirement_questions",
                "affected-test:test_validate_delivery_bundle",
            },
            "assets/requirement-traceability.template.md": {
                "affected-test:test_validate_traceability",
                "affected-test:test_validate_delivery_bundle",
                "affected-test:test_validate_skill",
            },
            "assets/generate-agents-md-swimlanes.html": {
                "affected-test:test_swimlane_html",
            },
            "scripts/browser_test_swimlane.mjs": {
                "affected-test:test_swimlane_html",
            },
        }
        for changed_file, expected in expectations.items():
            with self.subTest(changed_file=changed_file):
                checks = set(dict(build_checks(
                    mode="affected", changed_files=(changed_file,),
                )))
                self.assertTrue(expected.issubset(checks))
                self.assertNotIn("unit-regression", checks)

    def test_affected_python_change_includes_importing_consumer_tests(self) -> None:
        checks = set(dict(build_checks(
            mode="affected", changed_files=("scripts/validate_context_manifest.py",),
        )))
        self.assertTrue({
            "affected-test:test_validate_context_manifest",
            "affected-test:test_validate_delivery_bundle",
            "affected-test:test_validate_system_delivery_bundle",
            "affected-test:test_validate_swimlane_evidence",
            "affected-test:test_validate_multi_agent_evidence",
            "affected-test:test_implementation_agent_validation",
        }.issubset(checks))

        helper_checks = set(dict(build_checks(
            mode="affected", changed_files=("scripts/delivery_contract_bundle_validation.py",),
        )))
        self.assertTrue({
            "affected-test:test_golden_workflows",
            "affected-test:test_implementation_agent_validation",
            "affected-test:test_validate_delivery_bundle",
            "affected-test:test_validate_swimlane_evidence",
            "affected-test:test_validate_system_delivery_bundle",
        }.issubset(helper_checks))

    def test_affected_test_helpers_include_consumers_and_use_unittest_loader(self) -> None:
        helper_expectations = {
            "scripts/test_execution_run_support.py": {
                "affected-test:test_validate_context_manifest",
                "affected-test:test_validate_delivery_bundle",
            },
            "scripts/test_http_server.py": {
                "affected-test:test_validate_delivery_bundle",
                "affected-test:test_validate_frontend_evidence",
            },
            "scripts/test_image_support.py": {
                "affected-test:test_validate_delivery_bundle",
                "affected-test:test_validate_frontend_evidence",
            },
        }
        for changed_file, expected in helper_expectations.items():
            with self.subTest(changed_file=changed_file):
                checks = dict(build_checks(mode="affected", changed_files=(changed_file,)))
                self.assertTrue(expected.issubset(checks))

        no_main = dict(build_checks(
            mode="affected", changed_files=("scripts/test_trace_workset_binding.py",),
        ))
        command = no_main["affected-test:test_trace_workset_binding"]
        self.assertEqual(
            [sys.executable, "-m", "unittest", "-q", "scripts.test_trace_workset_binding"],
            command,
        )

    def test_semantic_asset_mapping_includes_literal_test_consumers(self) -> None:
        for asset in AFFECTED_ASSET_TESTS:
            checks = set(dict(build_checks(mode="affected", changed_files=(asset,))))
            filename = Path(asset).name
            for test_path in (SKILL_ROOT / "scripts").glob("test_*.py"):
                if filename in test_path.read_text(encoding="utf-8"):
                    with self.subTest(asset=asset, consumer=test_path.name):
                        self.assertIn(f"affected-test:{test_path.stem}", checks)

    def test_mutation_registry_changes_escalate_to_full(self) -> None:
        for changed in (
            ("scripts/run_mutation_checks.py",),
            ("scripts/mutation_cases_records.py",),
        ):
            with self.subTest(changed=changed):
                self.assertEqual("full", effective_mode(SKILL_ROOT, "affected", changed))

    def test_distribution_gate_is_explicit_and_full_only(self) -> None:
        self.assertNotIn("plugin-distribution", dict(build_checks(mode="full")))
        checks = dict(build_checks(
            mode="full", distribution=True, require_direct_skills=True,
        ))
        self.assertIn("plugin-distribution", checks)
        command = checks["plugin-distribution"]
        self.assertIn("validate_plugin_distribution.py", " ".join(command))
        self.assertIn("--require-source-provenance", command)
        self.assertIn("--require-direct-skills", command)
        with self.assertRaises(ValueError):
            build_checks(mode="quick", distribution=True)
        with self.assertRaises(ValueError):
            build_checks(mode="full", require_direct_skills=True)

        parser = build_parser()
        args = parser.parse_args(["--full", "--distribution", "--require-direct-skills"])
        self.assertTrue(args.distribution)
        self.assertTrue(args.require_direct_skills)

    def test_candidate_fingerprint_changes_only_with_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "SKILL.md"
            source.write_text("first", encoding="utf-8")
            initial = candidate_sha256(root)
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "ignored.pyc").write_bytes(b"runtime")
            self.assertEqual(initial, candidate_sha256(root))
            source.write_text("second", encoding="utf-8")
            self.assertNotEqual(initial, candidate_sha256(root))

    def test_full_receipt_prevents_duplicate_full_and_mutation(self) -> None:
        template = (SKILL_ROOT / "assets" / "AGENTS.template.md").read_text(encoding="utf-8")
        self.assertIn("full + mutation at most once per frozen release candidate", template)
        fingerprint = "a" * 64
        self.assertEqual(
            "blocked",
            full_execution_action(None, fingerprint, distribution=False),
        )
        self.assertEqual(
            "blocked",
            full_execution_action(
                {"candidate_sha256": fingerprint, "full_status": "fail"},
                fingerprint,
                distribution=False,
            ),
        )
        passed = VerifiedReceipt(_passing_receipt(fingerprint))
        self.assertEqual(
            "reuse-full",
            full_execution_action(passed, fingerprint, distribution=False),
        )
        self.assertEqual(
            "distribution-only",
            full_execution_action(passed, fingerprint, distribution=True),
        )
        distributed = VerifiedReceipt(_passing_receipt(fingerprint, distributed=True))
        self.assertEqual(
            "reuse-full",
            full_execution_action(distributed, fingerprint, distribution=True),
        )
        self.assertEqual(
            "blocked",
            full_execution_action(passed, "b" * 64, distribution=False),
        )

    def test_full_runner_executes_checks_once_then_reuses_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = build_parser().parse_args([
                "--full", "--full-receipt", str(Path(temporary) / "receipt.json"),
            ])
            _write_frozen_proof(Path(temporary) / "receipt.json")
            passed = _passing_full_results()
            with patch("validate_skill._execute_checks", return_value=passed) as execute:
                first_results, first_valid, first_receipt = _run_full_once(args)
                second_results, second_valid, second_receipt = _run_full_once(args)
            self.assertEqual(passed, first_results)
            self.assertTrue(first_valid)
            self.assertEqual("run-full", first_receipt["action"])
            self.assertEqual([], second_results)
            self.assertTrue(second_valid)
            self.assertEqual("reuse-full", second_receipt["action"])
            self.assertEqual(1, execute.call_count)

    def test_distribution_reuses_full_and_runs_only_distribution_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            base_args = build_parser().parse_args([
                "--full", "--full-receipt", str(receipt_path),
            ])
            _write_frozen_proof(receipt_path)
            passed = _passing_full_results()
            with patch("validate_skill._execute_checks", return_value=passed):
                _run_full_once(base_args)
            distribution_args = build_parser().parse_args([
                "--full", "--distribution", "--full-receipt", str(receipt_path),
            ])
            distribution_passed = [CheckResult(
                "plugin-distribution", ["distribution"], 0, 0.1, "",
            )]
            with patch("validate_skill._execute_checks", return_value=distribution_passed) as execute:
                _, valid, receipt = _run_full_once(distribution_args)
            self.assertTrue(valid)
            self.assertEqual("distribution-only", receipt["action"])
            selected = execute.call_args.args[1]
            self.assertEqual(["plugin-distribution"], [name for name, _ in selected])

    def test_full_receipt_is_locked_across_concurrent_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = build_parser().parse_args([
                "--full", "--full-receipt", str(Path(temporary) / "receipt.json"),
            ])
            _write_frozen_proof(Path(temporary) / "receipt.json")
            calls: list[int] = []

            def execute_once(*_args: object) -> list[CheckResult]:
                calls.append(1)
                time.sleep(0.05)
                return _passing_full_results()

            with patch("validate_skill._execute_checks", side_effect=execute_once):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _: _run_full_once(args), range(2)))
            self.assertEqual(1, len(calls))
            self.assertEqual(["reuse-full", "run-full"], sorted(item[2]["action"] for item in results))
            self.assertTrue(all(item[1] for item in results))

    def test_freeze_candidate_runs_quick_then_emits_current_signed_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            args = build_parser().parse_args([
                "--freeze-candidate", "--full-receipt", str(receipt_path),
            ])
            quick_results = [CheckResult(name, command, 0, 0.1, "")
                             for name, command in build_checks(mode="quick")]
            with patch("validate_skill._execute_checks", return_value=quick_results):
                results, valid, metadata = _run_freeze_candidate(args)
            self.assertEqual(quick_results, results)
            self.assertTrue(valid)
            self.assertEqual("freeze-candidate", metadata["action"])
            self.assertEqual(
                "run-full",
                full_execution_action(
                    __import__("full_validation_receipt").read_full_receipt(receipt_path),
                    candidate_sha256(SKILL_ROOT),
                    distribution=False,
                ),
            )

            failed = _passing_receipt(candidate_sha256(SKILL_ROOT))
            failed["full_status"], failed["checks"] = "fail", []
            write_full_receipt(receipt_path, failed)
            with patch("validate_skill._execute_checks") as execute:
                _, valid, metadata = _run_freeze_candidate(args)
            self.assertFalse(valid)
            self.assertEqual("blocked", metadata["action"])
            execute.assert_not_called()

    def test_receipt_hashing_is_locked_and_validation_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            args = build_parser().parse_args(["--full", "--full-receipt", str(receipt_path)])
            events: list[str] = []

            class ObservedLock:
                def __enter__(self) -> None:
                    events.append("lock")

                def __exit__(self, *_args: object) -> None:
                    return None

            with patch("validate_skill.exclusive_receipt_lock", return_value=ObservedLock()), \
                    patch("validate_skill.candidate_sha256",
                          side_effect=lambda _root: events.append("hash") or "a" * 64):
                _run_full_once(args)
            self.assertEqual(["lock", "hash"], events[:2])

            _write_frozen_proof(receipt_path, "a" * 64)
            with patch("validate_skill.candidate_sha256", side_effect=["a" * 64, "b" * 64]), \
                    patch("validate_skill._execute_checks", return_value=_passing_full_results()):
                _, valid, metadata = _run_full_once(args)
            self.assertFalse(valid)
            self.assertEqual("blocked", metadata["action"])
            stored = __import__("full_validation_receipt").read_full_receipt(receipt_path)
            self.assertEqual("fail", stored.payload["full_status"])

            receipt_path.unlink()
            freeze = build_parser().parse_args([
                "--freeze-candidate", "--full-receipt", str(receipt_path),
            ])
            quick = [CheckResult(name, command, 0, 0.1, "")
                     for name, command in build_checks(mode="quick")]
            with patch("validate_skill.candidate_sha256", side_effect=["a" * 64, "b" * 64]), \
                    patch("validate_skill._execute_checks", return_value=quick):
                _, valid, metadata = _run_freeze_candidate(freeze)
            self.assertFalse(valid)
            self.assertEqual("blocked", metadata["action"])
            self.assertFalse(receipt_path.exists())

    def test_full_and_unknown_affected_escalation_require_current_freeze_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            for argv in (
                ["--full", "--full-receipt", str(receipt_path)],
                ["--affected", "--changed-file", "unknown/new.py",
                 "--full-receipt", str(receipt_path)],
            ):
                with self.subTest(argv=argv):
                    args = build_parser().parse_args(argv)
                    with patch("validate_skill._execute_checks") as execute:
                        _, valid, metadata = _run_full_once(args)
                    self.assertFalse(valid)
                    self.assertEqual("blocked", metadata["action"])
                    self.assertIn("freeze", metadata["reason"])
                    execute.assert_not_called()

            _write_frozen_proof(receipt_path, "b" * 64)
            args = build_parser().parse_args([
                "--full", "--full-receipt", str(receipt_path),
            ])
            with patch("validate_skill._execute_checks") as execute:
                _, valid, metadata = _run_full_once(args)
            self.assertFalse(valid)
            self.assertIn("stale", metadata["reason"])
            execute.assert_not_called()

    def test_malformed_and_forged_full_receipts_fail_closed(self) -> None:
        fingerprint = "a" * 64
        self.assertEqual("blocked", full_execution_action(
            {"candidate_sha256": fingerprint, "full_status": "pass"},
            fingerprint, distribution=False,
        ))
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            receipt_path.write_text("{broken", encoding="utf-8")
            args = build_parser().parse_args([
                "--full", "--full-receipt", str(receipt_path),
            ])
            with patch("validate_skill._execute_checks") as execute:
                _, valid, receipt = _run_full_once(args)
            self.assertFalse(valid)
            self.assertEqual("blocked", receipt["action"])
            execute.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            receipt_path.write_text(
                json.dumps(_passing_receipt(candidate_sha256(SKILL_ROOT))),
                encoding="utf-8",
            )
            args = build_parser().parse_args([
                "--full", "--full-receipt", str(receipt_path),
            ])
            with patch("validate_skill._execute_checks") as execute:
                _, valid, receipt = _run_full_once(args)
            self.assertFalse(valid)
            self.assertEqual("blocked", receipt["action"])
            execute.assert_not_called()

    def test_full_receipt_inside_candidate_root_is_rejected(self) -> None:
        receipt_path = SKILL_ROOT / ".forbidden-full-receipt.json"
        self.assertFalse(receipt_path.exists())
        args = build_parser().parse_args([
            "--full", "--full-receipt", str(receipt_path),
        ])
        with patch("validate_skill._execute_checks") as execute:
            _, valid, receipt = _run_full_once(args)
        self.assertFalse(valid)
        self.assertEqual("blocked", receipt["action"])
        self.assertIn("outside", receipt["reason"])
        self.assertFalse(receipt_path.exists())
        execute.assert_not_called()

    def test_distribution_failure_does_not_invalidate_passed_full_layers(self) -> None:
        results = [
            CheckResult("mutation", ["mutation"], 0, 0.1, ""),
            CheckResult("plugin-distribution", ["distribution"], 1, 0.1, "failed"),
        ]
        self.assertEqual((True, False, False), _full_result_validity(results, True))

    def test_cross_module_aggregate_cli_is_in_smoke_gate(self) -> None:
        from validate_cli_smoke import CLI_SCRIPTS
        self.assertIn("validate_native_review_loop.py", CLI_SCRIPTS)
        self.assertIn("validate_system_delivery_bundle.py", CLI_SCRIPTS)

    def test_shared_mutation_registry_is_nontrivial_and_unique(self) -> None:
        from run_mutation_checks import MUTANTS
        self.assertGreaterEqual(len(MUTANTS), 450)
        self.assertEqual(len(MUTANTS), len({item.name for item in MUTANTS}))

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

        policy = policy_path.read_text(encoding="utf-8")
        for marker in (
            "校验器自动识别",
            "Access boundary`（必填）",
            "Authorized endpoints`（仅 URI",
            "参数本身不能授权",
        ):
            with self.subTest(policy_marker=marker):
                self.assertIn(marker, policy)

    def test_sensitive_policy_review_route_is_reachable_without_write_authorization(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("明确要求只读审查该策略或隔离效果", skill)

    def test_heavy_contracts_use_progressive_disclosure(self) -> None:
        skill_path = SKILL_ROOT / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        root_template = (SKILL_ROOT / "assets" / "AGENTS.template.md").read_text(encoding="utf-8")
        # SKILL.md is loaded on every invocation; keep meaningful headroom.
        self.assertLessEqual(len(skill.encode("utf-8")), 10_000)
        # Generated AGENTS.md becomes project context, so retain growth headroom.
        template_bytes = len(root_template.encode("utf-8"))
        self.assertGreaterEqual(template_bytes, 29_000)
        self.assertLessEqual(template_bytes, 30_500)
        # Captured before this requested compression pass; keep the reduction bounded.
        compression_delta = 31_995 - template_bytes
        self.assertGreaterEqual(compression_delta, 1_500)
        self.assertLessEqual(compression_delta, 2_500)
        self.assertLessEqual(max(map(len, skill.splitlines())), 900)
        for relative in (
            "references/multi-model-review-policy.md",
            "references/evidence-reuse-policy.md",
            "references/browser-validation-policy.md",
            "references/extraction-delivery.md",
            "references/extraction-interfaces.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((SKILL_ROOT / relative).is_file())
                self.assertIn(relative, skill)
        strict_skill = SKILL_ROOT.parent / "strict-delivery-security" / "SKILL.md"
        self.assertTrue(strict_skill.is_file())
        self.assertIn("$strict-delivery-security", skill)
        self.assertNotIn("references/strict-security-governance.md", skill)

    def test_default_context_is_limited_to_four_delivery_surfaces(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        template = (SKILL_ROOT / "assets" / "AGENTS.template.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, template))
        for marker in (
            "生效 `AGENTS.md`",
            "进度索引",
            "当前 run",
            "相关追踪行",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, combined)
        self.assertIn("默认只加载", combined)

    def test_final_aggregate_validators_are_closure_only(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("仅在闭环候选或完成阶段实时执行", skill)
        self.assertNotIn("是实时最终聚合", skill)

    def test_strict_security_details_are_conditionally_routed(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        governance = (SKILL_ROOT / "references" / "module-agent-governance.md").read_text(encoding="utf-8")
        strict_path = SKILL_ROOT / "references" / "strict-security-governance.md"
        optional_skill = (SKILL_ROOT.parent / "strict-delivery-security" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(strict_path.is_file())
        self.assertIn("$strict-delivery-security", skill)
        self.assertIn("默认 `delivery-first-local-coordination` 不加载", skill)
        self.assertIn("references/strict-security-governance.md", governance)
        self.assertIn("../generate-agents-md/references/strict-security-governance.md", optional_skill)
        self.assertIn("普通项目交付不得自动启用", optional_skill)
        self.assertNotIn("## 5. 可选严格安全：一次性 system-governance bootstrap", governance)

        strict = strict_path.read_text(encoding="utf-8")
        self.assertIn("一次性 system-governance bootstrap", strict)
        self.assertIn("显式本机受控普通模块写租约", strict)
        self.assertIn("local-controlled-same-user", strict)

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

    def test_stable_delivery_complexity_requires_factual_risk_mapping(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        template = (SKILL_ROOT / "assets" / "AGENTS.template.md").read_text(encoding="utf-8")
        extraction = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SKILL_ROOT / "references").glob("extraction-*.md"))
        )
        combined = "\n".join((skill, template, extraction))
        for required in (
            "稳定交付是流程设计的唯一目的",
            "Stable delivery is the only purpose of process complexity",
            "已核实风险/失败模式",
            "factual evidence",
            "removal condition",
            "无映射就不得新增或启动",
            "Dispatcher reuses the registered module maintenance Agent",
            "Dispatcher 复用已登记模块维护 Agent",
        ):
            with self.subTest(required=required):
                self.assertIn(required, combined)

    def test_swimlane_writes_are_semantic_batched_and_not_per_edit(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        template = (SKILL_ROOT / "assets" / "AGENTS.template.md").read_text(encoding="utf-8")
        extraction = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SKILL_ROOT / "references").glob("extraction-*.md"))
        )
        combined = "\n".join((skill, template, extraction))
        for required in (
            "flow_impact",
            "`none`, `changed`, or `uncertain`",
            "稳定候选",
            "stabilized candidate",
            "首次依赖该图的下游步骤",
            "first downstream consumer",
            "不改写图文件",
            "do not rewrite the diagram file",
            "不得为保险起见重画",
            "must not redraw just in case",
        ):
            with self.subTest(required=required):
                self.assertIn(required, combined)

        self.assertNotIn("阶段中间仅当修改改变", skill)
        self.assertNotIn("阶段完成时统一同步", extraction)

    def test_module_writer_authority_is_role_neutral_and_lease_bound(self) -> None:
        governance = (
            SKILL_ROOT / "references" / "module-agent-governance.md"
        ).read_text(encoding="utf-8")
        surfaces = (
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "assets" / "AGENTS.template.md",
            SKILL_ROOT / "references" / "module-agent-governance.md",
            SKILL_ROOT / "references" / "multi-model-review-policy.md",
            SKILL_ROOT.parent.parent / "README.md",
            SKILL_ROOT.parent.parent / ".codex-plugin" / "plugin.json",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in surfaces)
        self.assertNotIn("active parent GPT remains the sole workspace writer", combined)
        self.assertNotIn("父 GPT 裁决并作为唯一写者", combined)
        self.assertNotIn("父维护 Agent 只裁决/写入/路由", combined)
        self.assertNotIn("必须由主 Agent 写入", combined)
        self.assertIn("主、父、子层级不授予固有写权", combined)
        self.assertIn("Main, parent, and child placement grants no inherent write authority", combined)
        self.assertIn("唯一活动模块写租约", combined)
        self.assertIn("unique active module write lease", combined)
        self.assertIn("Dispatcher 角色始终只读", combined)
        self.assertIn("The Dispatcher role is always read-only", combined)
        self.assertIn("不得复用 Dispatcher 的 Agent ID 或 run ID", combined)
        self.assertIn("must not reuse the Dispatcher Agent ID or run ID", combined)
        self.assertIn("同一 OS 用户 shell/直接文件写入", combined)
        self.assertIn("filesystem-level isolation", combined)
        self.assertIn(
            "独立门禁通过只允许当前租约持有的模块维护 Agent 记录已经通过的结果",
            governance,
        )
        self.assertIn(
            "永不授权其自行 review、black-box、acceptance、adjudicate、close、complete 或 accept",
            governance,
        )
        self.assertNotIn(
            "正向证明独立审查/验收已经通过、完成或成功的先决条件才能豁免",
            governance,
        )

    def test_compact_authority_matrix_uses_expanded_v1_hash_identity(self) -> None:
        governance = (
            SKILL_ROOT / "references" / "module-agent-governance.md"
        ).read_text(encoding="utf-8")
        checklist = (
            SKILL_ROOT / "references" / "extraction-checklist.md"
        ).read_text(encoding="utf-8")
        for surface in (governance, checklist):
            self.assertIn("expanded-authority-matrix-v1", surface)
            self.assertIn("展开", surface)
            self.assertIn("canonical SHA-256", surface)
        self.assertIn("不得把紧凑 v2 JSON 的原始哈希误当成权限身份", governance)
        self.assertIn("未知合同", governance)

    def test_task_write_boundary_is_documented_and_executable(self) -> None:
        boundary = (
            SKILL_ROOT / "references" / "task-write-boundary.md"
        ).read_text(encoding="utf-8")
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        checklist = (
            SKILL_ROOT / "references" / "extraction-checklist.md"
        ).read_text(encoding="utf-8")
        smoke = (
            SKILL_ROOT / "scripts" / "validate_cli_smoke.py"
        ).read_text(encoding="utf-8")
        for surface in (boundary, checklist):
            self.assertIn("validate_task_write_scope.py", surface)
        self.assertIn("scripts/flowctl.py scope", skill)
        for required in (
            "当前用户请求",
            "精确维护源码根",
            "缓存和直装副本",
            "不能提供 OS 级隔离",
        ):
            with self.subTest(required=required):
                self.assertIn(required, boundary)
        self.assertIn('"validate_task_write_scope.py"', smoke)

    def test_traceability_template_never_turns_unanswered_risk_into_a_blocker(self) -> None:
        traceability = (
            SKILL_ROOT / "assets" / "requirement-traceability.template.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("continues unless the risk is", traceability)
        for required in (
            "Every `NOT_PROVIDED` item remains `delivery_disposition=NON_BLOCKING_P2`",
            "legal",
            "security",
            "irreversible-destruction",
            "missing-required-permission",
            "change only the safe action",
            "remaining safe scope continues",
        ):
            with self.subTest(required=required):
                self.assertIn(required, traceability)


if __name__ == "__main__":
    unittest.main()
