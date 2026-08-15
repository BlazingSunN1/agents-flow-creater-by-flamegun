from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_traceability import validate_traceability


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets" / "requirement-traceability.template.md"


def issue_codes(path: Path, root: Path) -> set[str]:
    return {issue.code for issue in validate_traceability(path, project_root=root)}


class TraceabilityValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in (
            "requirements/baseline.md",
            "flows/system.html",
            "features/list.md",
            "ui/prototype.html",
            "tests/unit.md",
            "tests/acceptance.md",
            "src/module.py",
            "evidence/black-box.md",
            "evidence/ui-input.md",
            "evidence/ui-output.md",
            "evidence/at-input.md",
            "evidence/at-output.md",
            "evidence/bb-input.md",
            "evidence/bb-output.md",
            "evidence/finding.md",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative, encoding="utf-8")
        self.matrix = self.root / "traceability.md"
        self.matrix.write_text(self._valid_matrix(), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_cli_help_is_executable(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "validate_traceability.py"), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_real_nul_byte_fails_closed(self) -> None:
        self.matrix.write_bytes(self.matrix.read_bytes() + b"\x00")
        self.assertIn("nul-byte", issue_codes(self.matrix, self.root))

    def test_table_separator_cannot_hide_pending_requirement(self) -> None:
        text = self.matrix.read_text(encoding="utf-8").replace(
            "|---|---|---|---|---|---|---|---|---|",
            "| [REQ-999](requirements/baseline.md) | N/A: hidden | N/A: hidden | N/A: hidden | N/A: hidden | N/A: hidden | N/A: hidden | N/A: hidden | pending |",
            1,
        )
        self.matrix.write_text(text, encoding="utf-8")
        self.assertIn("invalid-table-separator", issue_codes(self.matrix, self.root))

    def test_non_table_content_before_rows_fails_closed(self) -> None:
        marker = "|---|---|---|---|---|---|---|---|---|\n"
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8").replace(marker, marker + "hidden pending requirement\n", 1),
            encoding="utf-8",
        )
        self.assertIn("unexpected-table-content", issue_codes(self.matrix, self.root))

    def _valid_matrix(self) -> str:
        digest = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        return f"""# Delivery Traceability Matrix

- Baseline artifact: requirements/baseline.md
- Baseline version: req-v1
- Baseline SHA-256: {digest}
- Code version: code-v1
- Build ID: build-1
- Acceptance environment: local-release
- Verified at: 2026-08-14T10:00:00+08:00
- Risk level: standard
- Risk reason: user-visible interaction
- Change surfaces: ui,user-visible
- Implementation run ID: impl-run-1

## Traceability

| Requirement | Flow | Feature | UI/UX | Unit tests | Acceptance cases | Code module | Black-box result | Status |
|---|---|---|---|---|---|---|---|---|
| [REQ-001](requirements/baseline.md) | [FLOW-001](flows/system.html) | [FEAT-001](features/list.md) | [UI-001](ui/prototype.html) | [UT-001](tests/unit.md) | [AT-001](tests/acceptance.md) | [MOD-001](src/module.py) | [BB-001](evidence/black-box.md) | completed |

## Independent Gate Evidence

| Gate | Applicability | Agent run ID | Input baseline version | Input baseline SHA-256 | Code version | Build ID | Input manifest | Output evidence | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| UI_UX | required | ui-run-1 | req-v1 | {digest} | N/A | N/A | [CTX-UI-001](evidence/ui-input.md) | [EVD-UI-001](evidence/ui-output.md) | pass |
| ACCEPTANCE_CASES | required | at-run-1 | req-v1 | {digest} | N/A | N/A | [CTX-AT-001](evidence/at-input.md) | [EVD-AT-001](evidence/at-output.md) | pass |
| BLACK_BOX | required | bb-run-1 | req-v1 | {digest} | code-v1 | build-1 | [CTX-BB-001](evidence/bb-input.md) | [EVD-BB-001](evidence/bb-output.md) | pass |

## Open Findings

- None
"""

    def rewrite(self, old: str, new: str) -> None:
        self.matrix.write_text(self.matrix.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_public_template_structure_passes(self) -> None:
        self.assertEqual([], validate_traceability(PUBLIC_TEMPLATE, project_root=SKILL_ROOT, template=True))

    def test_distinct_role_paths_cannot_copy_identical_artifact_content(self) -> None:
        payload = (self.root / "requirements/baseline.md").read_bytes()
        for relative in (
            "flows/system.html", "features/list.md", "ui/prototype.html", "tests/unit.md",
            "tests/acceptance.md", "src/module.py", "evidence/black-box.md",
        ):
            (self.root / relative).write_bytes(payload)
        self.assertIn("reused-trace-artifact-role", issue_codes(self.matrix, self.root))

    def test_trace_role_content_copy_cannot_hide_with_whitespace_changes(self) -> None:
        payload = (self.root / "requirements/baseline.md").read_text(encoding="utf-8").rstrip()
        for index, relative in enumerate((
            "flows/system.html", "features/list.md", "ui/prototype.html", "tests/unit.md",
            "tests/acceptance.md", "src/module.py", "evidence/black-box.md",
        ), start=1):
            (self.root / relative).write_text(payload + " " * index + "\n", encoding="utf-8")
        self.assertIn("reused-trace-artifact-role", issue_codes(self.matrix, self.root))

    def test_trace_role_content_copy_cannot_hide_with_zero_width_format_chars(self) -> None:
        payload = (self.root / "requirements/baseline.md").read_text(encoding="utf-8").rstrip()
        for index, relative in enumerate((
            "flows/system.html", "features/list.md", "ui/prototype.html", "tests/unit.md",
            "tests/acceptance.md", "src/module.py", "evidence/black-box.md",
        ), start=1):
            (self.root / relative).write_text(payload + "\u200b" * index, encoding="utf-8")
        self.assertIn("reused-trace-artifact-role", issue_codes(self.matrix, self.root))

    def test_trace_content_identity_preserves_internal_whitespace_semantics(self) -> None:
        (self.root / "flows/system.html").write_text('{"value":"a  b"}', encoding="utf-8")
        (self.root / "features/list.md").write_text('{"value":"a b"}', encoding="utf-8")
        self.assertNotIn("reused-trace-artifact-role", issue_codes(self.matrix, self.root))

    def test_template_mode_rejects_wrong_role_id_and_status(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("[REQ-001]", "[BAD-001]", 1).replace("| pending |", "| bogus-status |", 1)
        self.matrix.write_text(text, encoding="utf-8")
        codes = {item.code for item in validate_traceability(self.matrix, project_root=self.root, template=True)}
        self.assertTrue({"wrong-id-prefix", "invalid-trace-status"} <= codes)

    def test_template_mode_rejects_optional_or_failed_required_gate(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("| ACCEPTANCE_CASES | required |", "| ACCEPTANCE_CASES | optional |")
        text = text.replace("| pending |", "| fail |", 2)
        self.matrix.write_text(text, encoding="utf-8")
        codes = {item.code for item in validate_traceability(self.matrix, project_root=self.root, template=True)}
        self.assertTrue({"invalid-gate-applicability", "invalid-gate-verdict"} <= codes)

    def test_closed_trace_passes(self) -> None:
        self.assertEqual(set(), issue_codes(self.matrix, self.root))

    def test_requirement_id_cannot_be_split_across_multiple_rows(self) -> None:
        text = self.matrix.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| [REQ-001]"))
        duplicate = row.replace("FLOW-001", "FLOW-002").replace("FEAT-001", "FEAT-002")
        text = text.replace(row, row + "\n" + duplicate)
        self.matrix.write_text(text, encoding="utf-8")
        self.assertIn("duplicate-requirement-row", issue_codes(self.matrix, self.root))

    def test_requirement_cell_links_must_be_unique(self) -> None:
        self.rewrite(
            "[REQ-001](requirements/baseline.md)",
            "[REQ-001](requirements/baseline.md), [REQ-001](requirements/baseline.md)",
        )
        self.assertIn("duplicate-requirement-link", issue_codes(self.matrix, self.root))

    def test_template_requires_black_box_gate(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("| BLACK_BOX |")) + "\n"
        self.matrix.write_text(text, encoding="utf-8")
        codes = {item.code for item in validate_traceability(self.matrix, project_root=self.root, template=True)}
        self.assertIn("missing-independent-gate", codes)

    def test_baseline_drift_fails(self) -> None:
        (self.root / "requirements/baseline.md").write_text("changed", encoding="utf-8")
        self.assertIn("stale-baseline-hash", issue_codes(self.matrix, self.root))

    def test_risk_underclassification_fails(self) -> None:
        self.rewrite("Risk level: standard", "Risk level: small")
        self.assertIn("risk-underclassified", issue_codes(self.matrix, self.root))

    def test_self_certification_and_agent_reuse_fail(self) -> None:
        self.rewrite("ui-run-1", "impl-run-1")
        self.rewrite("at-run-1", "bb-run-1")
        codes = issue_codes(self.matrix, self.root)
        self.assertIn("self-certified-gate", codes)
        self.assertIn("reused-independent-agent", codes)

    def test_stale_black_box_build_fails(self) -> None:
        self.rewrite("| code-v1 | build-1 | [CTX-BB", "| code-v0 | build-0 | [CTX-BB")
        codes = issue_codes(self.matrix, self.root)
        self.assertTrue({"stale-black-box-code-version", "stale-black-box-build"} <= codes)

    def test_completed_requires_passed_gates_and_no_open_findings(self) -> None:
        self.rewrite("| pass |\n\n## Open Findings", "| fail |\n\n## Open Findings")
        self.rewrite(
            "- None",
            "| Finding | Class | Status | Route | Evidence |\n"
            "|---|---|---|---|---|\n"
            "| bug | implementation_defect | open | implementation | [EVD-FIND-001](evidence/finding.md) |",
        )
        codes = issue_codes(self.matrix, self.root)
        self.assertTrue({"gate-not-passed", "open-findings"} <= codes)

    def test_wrong_finding_route_fails(self) -> None:
        self.rewrite(
            "- None",
            "| Finding | Class | Status | Route | Evidence |\n"
            "|---|---|---|---|---|\n"
            "| bug | implementation_defect | resolved | requirement-baseline | [EVD-FIND-001](evidence/finding.md) |",
        )
        self.assertIn("wrong-finding-route", issue_codes(self.matrix, self.root))

    def test_directory_baseline_and_duplicate_metadata_fail(self) -> None:
        self.rewrite("Baseline artifact: requirements/baseline.md", "Baseline artifact: .")
        self.matrix.write_text(self.matrix.read_text(encoding="utf-8") + "\n- Risk level: small\n", encoding="utf-8")
        codes = issue_codes(self.matrix, self.root)
        self.assertTrue({"nonfile-baseline-artifact", "duplicate-metadata"} <= codes)

    def test_missing_and_unsafe_artifacts_fail(self) -> None:
        self.rewrite("features/list.md", "../outside.md")
        self.rewrite("tests/unit.md", "tests/missing.md")
        codes = issue_codes(self.matrix, self.root)
        self.assertIn("unsafe-trace-artifact-path", codes)
        self.assertIn("missing-trace-artifact", codes)

    def test_ui_na_is_rejected_for_user_visible_change(self) -> None:
        self.rewrite("[UI-001](ui/prototype.html)", "N/A: no prototype")
        self.assertIn("ui-gate-required", issue_codes(self.matrix, self.root))

    def test_unknown_surface_fails_and_cannot_keep_standard_risk(self) -> None:
        self.rewrite("Change surfaces: ui,user-visible", "Change surfaces: ui,typo-surface")
        codes = issue_codes(self.matrix, self.root)
        self.assertTrue({"unknown-change-surface", "risk-underclassified"} <= codes)

    def test_empty_trace_table_fails(self) -> None:
        row = "| [REQ-001](requirements/baseline.md) | [FLOW-001](flows/system.html) | [FEAT-001](features/list.md) | [UI-001](ui/prototype.html) | [UT-001](tests/unit.md) | [AT-001](tests/acceptance.md) | [MOD-001](src/module.py) | [BB-001](evidence/black-box.md) | completed |\n"
        self.rewrite(row, "")
        self.assertIn("empty-trace-table", issue_codes(self.matrix, self.root))

    def test_completion_rejects_pending_trace(self) -> None:
        self.rewrite("| completed |", "| pending |")
        self.assertIn("trace-not-completed", issue_codes(self.matrix, self.root))

    def test_implementation_stage_rejects_started_black_box(self) -> None:
        self.rewrite("| completed |", "| pending |")
        self.rewrite("| bb-run-1 | req-v1", "| bb-run-1 | req-v1")
        self.rewrite("[EVD-BB-001](evidence/bb-output.md) | pass |", "[EVD-BB-001](evidence/bb-output.md) | pending |")
        codes = {issue.code for issue in validate_traceability(self.matrix, project_root=self.root, stage="implementation")}
        self.assertIn("implementation-black-box-started", codes)

    def test_implementation_stage_accepts_honest_black_box_not_started(self) -> None:
        self.rewrite("| completed |", "| pending |")
        self.rewrite(
            "| BLACK_BOX | required | bb-run-1 | req-v1 |",
            "| BLACK_BOX | required |  | req-v1 |",
        )
        self.rewrite(
            "[CTX-BB-001](evidence/bb-input.md) | [EVD-BB-001](evidence/bb-output.md) | pass |",
            "N/A: not started | N/A: not started | pending |",
        )
        codes = {issue.code for issue in validate_traceability(
            self.matrix, project_root=self.root, stage="implementation",
        )}
        self.assertFalse({"missing-agent-run-id", "invalid-gate-artifact"} & codes)

    def test_mixed_none_and_finding_table_fails(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8")
            + "\n|  Finding  | Class | Status | Route | Evidence |\n|---|---|---|---|---|\n"
            + "| bug | implementation_defect | open | implementation | [EVD-FIND-001](evidence/finding.md) |\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_mixed_none_and_bold_finding_header_fails(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8")
            + "\n| **Finding** | Class | Status | Route | Evidence |\n|---|---|---|---|---|\n"
            + "| bug | implementation_defect | open | implementation | [E](evidence/finding.md) |\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_mixed_none_and_linked_finding_header_fails(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8")
            + "\n| [Finding](guide.md) | Class | Status | Route | Evidence |\n|---|---|---|---|---|\n"
            + "| hidden | implementation_defect | open | implementation | [E](evidence/finding.md) |\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_mixed_none_and_reference_linked_finding_header_fails(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8")
            + "\n[fh]: guide.md\n\n| [Finding][fh] | Class | Status | Route | Evidence |\n"
            + "|---|---|---|---|---|\n| hidden | implementation_defect | open | implementation | [E](evidence/finding.md) |\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_mixed_none_and_shortcut_reference_finding_header_fails(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8")
            + "\n[Finding]: guide.md\n\n| [Finding] | Class | Status | Route | Evidence |\n"
            + "|---|---|---|---|---|\n| hidden | implementation_defect | open | implementation | [E](evidence/finding.md) |\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_none_must_be_the_only_open_findings_content(self) -> None:
        self.matrix.write_text(
            self.matrix.read_text(encoding="utf-8") + "\nunexpected extra content\n",
            encoding="utf-8",
        )
        self.assertIn("ambiguous-findings", issue_codes(self.matrix, self.root))

    def test_malformed_trace_row_fails_closed(self) -> None:
        marker = "\n## Independent Gate Evidence"
        malformed = "\n| [REQ-002](requirements/baseline.md) | malformed row |\n"
        self.rewrite(marker, malformed + marker)
        self.assertIn("malformed-table-row", issue_codes(self.matrix, self.root))

    def test_non_ui_change_may_skip_ui_agent_with_reason(self) -> None:
        self.rewrite("Risk level: standard", "Risk level: small")
        self.rewrite("Risk reason: user-visible interaction", "Risk reason: internal refactor")
        self.rewrite("Change surfaces: ui,user-visible", "Change surfaces: internal")
        self.rewrite("[UI-001](ui/prototype.html)", "N/A: no UI behavior")
        self.rewrite(
            "| UI_UX | required | ui-run-1 | req-v1 |",
            "| UI_UX | N/A: no UI behavior |  | req-v1 |",
        )
        self.rewrite(
            "[EVD-UI-001](evidence/ui-output.md) | pass |",
            "[EVD-UI-001](evidence/ui-output.md) | not_applicable |",
        )
        self.assertEqual(set(), issue_codes(self.matrix, self.root))

    def test_ui_change_cannot_skip_ui_agent(self) -> None:
        self.rewrite(
            "| UI_UX | required | ui-run-1 | req-v1 |",
            "| UI_UX | N/A: no UI behavior |  | req-v1 |",
        )
        self.rewrite(
            "[EVD-UI-001](evidence/ui-output.md) | pass |",
            "[EVD-UI-001](evidence/ui-output.md) | not_applicable |",
        )
        self.assertIn("ui-gate-required", issue_codes(self.matrix, self.root))

    def test_shared_artifact_id_and_path_are_allowed(self) -> None:
        row = (
            "| [REQ-002](requirements/baseline.md) | [FLOW-001](flows/system.html) | "
            "[FEAT-001](features/list.md) | [UI-001](ui/prototype.html) | "
            "[UT-001](tests/unit.md) | [AT-001](tests/acceptance.md) | "
            "[MOD-001](src/module.py) | [BB-001](evidence/black-box.md) | completed |\n"
        )
        self.rewrite("\n## Independent Gate Evidence", "\n" + row + "\n## Independent Gate Evidence")
        self.assertNotIn("duplicate-trace-id", issue_codes(self.matrix, self.root))

    def test_shared_artifact_id_cannot_change_path(self) -> None:
        (self.root / "flows" / "other.html").write_text("other", encoding="utf-8")
        row = (
            "| [REQ-002](requirements/baseline.md) | [FLOW-001](flows/other.html) | "
            "[FEAT-002](features/list.md) | [UI-002](ui/prototype.html) | "
            "[UT-002](tests/unit.md) | [AT-002](tests/acceptance.md) | "
            "[MOD-002](src/module.py) | [BB-002](evidence/black-box.md) | completed |\n"
        )
        self.rewrite("\n## Independent Gate Evidence", "\n" + row + "\n## Independent Gate Evidence")
        self.assertIn("conflicting-trace-id", issue_codes(self.matrix, self.root))

    def test_different_trace_roles_cannot_all_reuse_baseline_artifact(self) -> None:
        original = (
            "| [REQ-001](requirements/baseline.md) | [FLOW-001](flows/system.html) | "
            "[FEAT-001](features/list.md) | [UI-001](ui/prototype.html) | "
            "[UT-001](tests/unit.md) | [AT-001](tests/acceptance.md) | "
            "[MOD-001](src/module.py) | [BB-001](evidence/black-box.md) | completed |"
        )
        reused = (
            "| [REQ-001](requirements/baseline.md) | [FLOW-001](requirements/baseline.md) | "
            "[FEAT-001](requirements/baseline.md) | [UI-001](requirements/baseline.md) | "
            "[UT-001](requirements/baseline.md) | [AT-001](requirements/baseline.md) | "
            "[MOD-001](requirements/baseline.md) | [BB-001](requirements/baseline.md) | completed |"
        )
        self.rewrite(original, reused)
        self.assertIn("reused-trace-artifact-role", issue_codes(self.matrix, self.root))


if __name__ == "__main__":
    unittest.main()
