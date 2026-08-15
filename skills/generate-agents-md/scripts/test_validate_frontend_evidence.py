from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_project_commands as command_test_support
import test_validate_traceability as trace_test_support
from browser_dom_validation import css_hidden_ids
from test_http_server import ProjectHttpServer
from test_image_support import png_bytes
from validate_frontend_evidence import _ordered_actions, _validate_hashed_artifact, validate_frontend_evidence


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets" / "frontend-evidence.template.json"


class FrontendEvidenceValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_fixture = trace_test_support.TraceabilityValidatorTests()
        self.trace_fixture.setUp()
        self.root = self.trace_fixture.root
        self.http = ProjectHttpServer(self.root)
        self.page_url = self.http.url("index.html")
        (self.root / "commands.txt").write_text("unittest\npython3 -m unittest\npython3 -m playwright test\n", encoding="utf-8")
        manifest = command_test_support.ProjectCommandValidatorTests()._manifest()
        manifest["frontend_applicable"] = True
        manifest.update({
            "frontend_preview_url": self.page_url,
            "frontend_preview_root": ".",
            "frontend_entry_artifact": "index.html",
        })
        for command in manifest["commands"]:
            if command["id"] in {"frontend_evidence", "frontend_e2e"}:
                command["applicability"] = "required"
            if command["id"] == "frontend_e2e":
                command["argv"] = ["python3", "-m", "playwright", "test"]
                command["source_command"] = "python3 -m playwright test"
        self.commands = self.root / "commands.json"
        self.commands.write_text(json.dumps(manifest), encoding="utf-8")
        page = '<main id="entry">current frontend build<button id="open">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>'
        (self.root / "index.html").write_text(page, encoding="utf-8")
        self.dom_snapshot = self.root / "evidence/browser-dom.html"
        self.dom_snapshot.write_text(page, encoding="utf-8")
        self.after_open = self.root / "evidence/state-after-open.html"
        self.after_click = self.root / "evidence/state-after-click.html"
        self.after_open.write_text(page.replace('id="visible"', 'id="visible" data-state="open"'), encoding="utf-8")
        self.after_click.write_text(page.replace('id="visible"', 'id="visible" data-state="clicked"'), encoding="utf-8")
        self.screenshot = self.root / "evidence" / "frontend.png"
        self.report = self.root / "evidence" / "playwright.json"
        self.screenshot.write_bytes(png_bytes(1280, 720))
        self.report.write_text('{"config":{},"suites":[{"specs":[{"title":"opens and closes module","tests":[{"projectName":"desktop","results":[{"status":"passed"}]},{"projectName":"mobile","results":[{"status":"passed"}]}]}]}],"errors":[],"stats":{"expected":2,"unexpected":0,"flaky":0,"skipped":0}}', encoding="utf-8")
        self.transcript = self.root / "evidence" / "browser-transcript.json"
        self.transcript.write_text(json.dumps({
            "tool": "browser:control-in-app-browser", "run_id": "browser-run-1", "verifier_agent_run_id": "bb-run-1",
            "page_url": self.page_url,
            "preview_root": ".",
            "page_artifact_path": "index.html",
            "page_artifact_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "observed_response_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "dom_snapshot_path": "evidence/browser-dom.html",
            "dom_snapshot_sha256": hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest(),
            "started_at": "2026-08-14T12:00:00+08:00", "ended_at": "2026-08-14T12:01:00+08:00",
            "viewport": [1280, 720],
            "screenshots": [{
                "path": "evidence/frontend.png",
                "sha256": hashlib.sha256(self.screenshot.read_bytes()).hexdigest(),
            }],
            "actions": [
                {"sequence": 1, "action": "navigate", "target": "#entry", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 2, "action": "click", "target": "#open", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 3, "action": "click", "target": "#click", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 4, "action": "assert", "target": "#visible", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 5, "action": "screenshot", "target": "evidence/frontend.png", "result": "pass", "visible": True, "enabled": True},
            ],
            "state_transitions": [
                {"click_target": "#open", "assertion_target": "#visible", "before_state_path": "evidence/browser-dom.html", "before_state_sha256": hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-open.html", "after_state_sha256": hashlib.sha256(self.after_open.read_bytes()).hexdigest()},
                {"click_target": "#click", "assertion_target": "#visible", "before_state_path": "evidence/state-after-open.html", "before_state_sha256": hashlib.sha256(self.after_open.read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-click.html", "after_state_sha256": hashlib.sha256(self.after_click.read_bytes()).hexdigest()},
            ],
            "console_errors": [], "required_request_failures": [],
        }), encoding="utf-8")
        self.path = self.root / "frontend-evidence.json"
        self.path.write_text(json.dumps(self._evidence()), encoding="utf-8")

    def tearDown(self) -> None:
        self.http.close()
        self.trace_fixture.tearDown()

    def test_boolean_schema_version_is_rejected(self) -> None:
        data = self._evidence()
        data["schema_version"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-schema-version", codes)

    def test_viewport_and_e2e_counts_reject_boolean_integer_aliases(self) -> None:
        data = self._evidence()
        data["browser"]["viewport"] = [True, True]
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["viewport"] = [True, True]
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        data["e2e"]["exit_code"] = False
        data["e2e"]["failed"] = False
        data["e2e"]["passed"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertTrue({"invalid-viewport", "e2e-not-passed"} <= codes)

    def test_browser_and_e2e_run_identities_must_be_strings(self) -> None:
        for field, value in (("run_id", 123), ("verifier_agent_run_id", 456)):
            with self.subTest(field=field):
                data = self._evidence()
                data["browser"][field] = value
                self.path.write_text(json.dumps(data), encoding="utf-8")
                codes = {item.code for item in validate_frontend_evidence(
                    self.path, trace_path=self.trace_fixture.matrix,
                    command_manifest=self.commands, project_root=self.root,
                )}
                expected = "missing-browser-run-id" if field == "run_id" else "missing-browser-verifier-run-id"
                self.assertIn(expected, codes)
        data = self._evidence()
        data["e2e"]["execution_run_id"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("missing-e2e-run-id", codes)

    def test_duplicate_or_unknown_browser_transcript_fields_fail_closed(self) -> None:
        raw = self.transcript.read_text(encoding="utf-8").replace(
            '"console_errors": []',
            '"console_errors": ["fatal"], "console_errors": []',
        )
        self.transcript.write_text(raw, encoding="utf-8")
        data = self._evidence()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-browser-transcript", codes)
        transcript = json.loads(raw)
        transcript["unknown_failure_state"] = "P1 unresolved"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self._evidence()), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-browser-transcript-fields", codes)

    def test_browser_actions_require_exact_order_target_and_standard_json(self) -> None:
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"][0].pop("target")
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self._evidence()), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-browser-action-fields", codes)
        raw = json.dumps(transcript).replace('"sequence": 1', '"sequence": NaN', 1)
        self.transcript.write_text(raw, encoding="utf-8")
        self.path.write_text(json.dumps(self._evidence()), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-browser-transcript", codes)

    def test_browser_action_semantics_reject_reverse_unknown_and_unbound_targets(self) -> None:
        evidence = self._browser()
        actions = json.loads(self.transcript.read_text(encoding="utf-8"))["actions"]
        self.assertTrue(_ordered_actions(actions, evidence))
        reversed_actions = [dict(item) for item in reversed(actions)]
        for index, action in enumerate(reversed_actions, start=1):
            action["sequence"] = index
        self.assertFalse(_ordered_actions(reversed_actions, evidence))
        unknown = [*actions, {"sequence": 5, "action": 123, "target": "bogus", "result": "pass", "visible": True, "enabled": True}]
        self.assertFalse(_ordered_actions(unknown, evidence))
        unrelated = [dict(item, target="unrelated-target") for item in actions]
        self.assertFalse(_ordered_actions(unrelated, evidence))
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"] = reversed_actions
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self._evidence()), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root,
        )}
        self.assertIn("invalid-browser-action-order", codes)

    def _browser(self) -> dict[str, object]:
        return {
            "tool": "browser:control-in-app-browser",
            "run_id": "browser-run-1",
            "verifier_agent_run_id": "bb-run-1",
            "page_url": self.page_url,
            "preview_root": ".",
            "page_artifact_path": "index.html",
            "page_artifact_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "observed_response_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "dom_snapshot_path": "evidence/browser-dom.html",
            "dom_snapshot_sha256": hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest(),
            "started_at": "2026-08-14T12:00:00+08:00",
            "ended_at": "2026-08-14T12:01:00+08:00",
            "transcript_path": "evidence/browser-transcript.json",
            "transcript_sha256": hashlib.sha256(self.transcript.read_bytes()).hexdigest(),
            "verdict": "pass",
            "viewport": [1280, 720],
            "click_path": ["#entry", "#open", "#click"],
            "assertions": ["#visible"],
            "state_transitions": [
                {"click_target": "#open", "assertion_target": "#visible", "before_state_path": "evidence/browser-dom.html", "before_state_sha256": hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-open.html", "after_state_sha256": hashlib.sha256(self.after_open.read_bytes()).hexdigest()},
                {"click_target": "#click", "assertion_target": "#visible", "before_state_path": "evidence/state-after-open.html", "before_state_sha256": hashlib.sha256(self.after_open.read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-click.html", "after_state_sha256": hashlib.sha256(self.after_click.read_bytes()).hexdigest()},
            ],
            "console_errors": [],
            "required_request_failures": [],
            "screenshots": [{
                "path": "evidence/frontend.png",
                "sha256": hashlib.sha256(self.screenshot.read_bytes()).hexdigest(),
            }],
        }

    def _evidence(self) -> dict[str, object]:
        digest = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        return {
            "schema_version": 1,
            "baseline_version": "req-v1",
            "baseline_sha256": digest,
            "code_version": "code-v1",
            "build_id": "build-1",
            "run_id": "impl-run-1",
            "browser": self._browser(),
            "e2e": {
                "framework": "Playwright",
                "command_id": "frontend_e2e",
                "execution_run_id": "e2e-run-1",
                "started_at": "2026-08-14T12:01:00+08:00",
                "ended_at": "2026-08-14T12:02:00+08:00",
                "command_argv_sha256": hashlib.sha256(b"python3\0-m\0playwright\0test").hexdigest(),
                "exit_code": 0,
                "passed": 2,
                "failed": 0,
                "report_path": "evidence/playwright.json",
                "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
            },
            "mobile": "N/A: mobile not in approved scope",
            "verdict": "pass",
        }

    def codes(self) -> set[str]:
        return {
            item.code
            for item in validate_frontend_evidence(
                self.path,
                trace_path=self.trace_fixture.matrix,
                command_manifest=self.commands,
                project_root=self.root,
            )
        }

    def _write_dom_variant(self, markup: str) -> None:
        page = self.root / "index.html"
        page.write_text(markup, encoding="utf-8")
        self.dom_snapshot.write_bytes(page.read_bytes())
        digest = hashlib.sha256(page.read_bytes()).hexdigest()
        data = self._evidence()
        data["browser"].update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript.update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_public_template_structure_passes(self) -> None:
        self.assertEqual(
            [],
            validate_frontend_evidence(
                PUBLIC_TEMPLATE,
                trace_path=self.trace_fixture.matrix,
                command_manifest=self.commands,
                project_root=self.root,
                template=True,
            ),
        )

    def test_template_mode_rejects_invalid_nested_browser_and_e2e(self) -> None:
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["browser"] = {}
        data["e2e"]["exit_code"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root, template=True,
        )}
        self.assertTrue({"invalid-browser-fields", "invalid-e2e-counts"} <= codes)

    def test_template_mode_rejects_e2e_object_types_and_malformed_mobile(self) -> None:
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["e2e"]["framework"] = True
        data["e2e"]["report_path"] = {"unsafe": "object"}
        data["mobile"] = {"tool": "browser:control-in-app-browser"}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root, template=True,
        )}
        self.assertTrue({"invalid-e2e-field-types", "invalid-mobile-template"} <= codes)

    def test_template_mobile_object_enforces_scalar_types_and_tool(self) -> None:
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["mobile"] = dict(data["browser"])
        data["mobile"].update({"tool": False, "run_id": True, "page_url": 17})
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_frontend_evidence(
            self.path, trace_path=self.trace_fixture.matrix,
            command_manifest=self.commands, project_root=self.root, template=True,
        )}
        self.assertIn("invalid-mobile-template", codes)

    def test_valid_frontend_evidence_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_screenshot_pixels_must_cover_declared_viewport(self) -> None:
        self.screenshot.write_bytes(png_bytes(1, 1))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("screenshot-viewport-mismatch", self.codes())

    def test_png_dimensions_must_match_decoded_scanlines(self) -> None:
        self.screenshot.write_bytes(png_bytes(1280, 720, truncate_pixels=True))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("screenshot-viewport-mismatch", self.codes())

    def test_png_iend_must_be_empty(self) -> None:
        self.screenshot.write_bytes(png_bytes(1280, 720, invalid_iend=True))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"invalid-screenshot-format", "screenshot-viewport-mismatch"} & self.codes())

    def test_indexed_png_requires_palette(self) -> None:
        self.screenshot.write_bytes(png_bytes(1280, 720, color_type=3))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("screenshot-viewport-mismatch", self.codes())

    def test_png_rejects_unknown_critical_chunks(self) -> None:
        self.screenshot.write_bytes(png_bytes(1280, 720, unknown_critical=True))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("screenshot-viewport-mismatch", self.codes())

    def test_png_idat_chunks_must_be_consecutive(self) -> None:
        self.screenshot.write_bytes(png_bytes(1280, 720, split_idat=True))
        data = self._evidence()
        digest = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        data["browser"]["screenshots"][0]["sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"][0]["sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("screenshot-viewport-mismatch", self.codes())

    def test_click_and_assert_targets_must_exist_in_hashed_dom_snapshot(self) -> None:
        page = self.root / "index.html"
        page.write_text('<main id="entry">no controls or result</main>', encoding="utf-8")
        self.dom_snapshot.write_bytes(page.read_bytes())
        digest = hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest()
        data = self._evidence()
        data["browser"].update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript.update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_dom_snapshot_must_match_live_page_bytes(self) -> None:
        page = self.root / "index.html"
        page.write_text('<main id="entry">no controls or result</main>', encoding="utf-8")
        digest = hashlib.sha256(page.read_bytes()).hexdigest()
        data = self._evidence()
        data["browser"]["page_artifact_sha256"] = digest
        data["browser"]["observed_response_sha256"] = digest
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_artifact_sha256"] = digest
        transcript["observed_response_sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-dom-page-mismatch", self.codes())

    def test_hidden_or_disabled_dom_targets_cannot_prove_interaction(self) -> None:
        cases = (
            '<main id="entry"><button id="open" hidden>Open</button><button id="click" hidden>Click</button><div id="visible" hidden>Invisible</div></main>',
            '<main id="entry"><button id="open" disabled>Open</button><button id="click" disabled>Click</button><div id="visible">Visible</div></main>',
            '<style>main #open,main #click,main #visible{display:none}</style><main id="entry"><button id="open" aria-disabled="true">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>',
        )
        for markup in cases:
            with self.subTest(markup=markup):
                self._write_dom_variant(markup)
                self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_compound_css_selectors_hide_declared_targets(self) -> None:
        selectors = ("main #click", "main>#click", "button#click", "#click:is(button)")
        for selector in selectors:
            with self.subTest(selector=selector):
                self._write_dom_variant(
                    f'<style>{selector} {{display:none}}</style>'
                    '<main id="entry"><button id="open">Open</button><button id="click">Click</button>'
                    '<div id="visible">Visible</div></main>'
                )
                self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_css_not_selector_hides_matching_target(self) -> None:
        self._write_dom_variant(
            '<style>#click:not(.shown){display:none}</style>'
            '<main id="entry"><button id="open">Open</button><button id="click">Click</button>'
            '<div id="visible">Visible</div></main>'
        )
        self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_css_not_selector_does_not_apply_when_excluded_class_exists(self) -> None:
        self._write_dom_variant(
            '<style>#click:not(.shown){display:none}</style>'
            '<main id="entry"><button id="open">Open</button><button id="click" class="shown">Click</button>'
            '<div id="visible">Visible</div></main>'
        )
        self.assertNotIn("browser-dom-action-mismatch", self.codes())

    def test_css_not_selector_supports_multiple_exclusions(self) -> None:
        for classes, should_hide in (("", True), ("shown", False), ("active", False)):
            with self.subTest(classes=classes):
                class_attr = f' class="{classes}"' if classes else ""
                self._write_dom_variant(
                    '<style>#click:not(.shown,.active){display:none}</style>'
                    '<main id="entry"><button id="open">Open</button>'
                    f'<button id="click"{class_attr}>Click</button>'
                    '<div id="visible">Visible</div></main>'
                )
                codes = self.codes()
                if should_hide:
                    self.assertIn("browser-dom-action-mismatch", codes)
                else:
                    self.assertNotIn("browser-dom-action-mismatch", codes)

    def test_css_not_disabled_uses_element_state(self) -> None:
        css = "#click:not(:disabled){display:none}"
        self.assertEqual(
            {"click"}, css_hidden_ids(css, {"click": {"@tag": "button"}}),
        )
        self.assertEqual(
            set(), css_hidden_ids(css, {"click": {"@tag": "button", "disabled": ""}}),
        )

    def test_linked_stylesheet_cannot_hide_declared_targets(self) -> None:
        (self.root / "hidden.css").write_text("#open,#click,#visible{display:none}", encoding="utf-8")
        self._write_dom_variant(
            '<link rel="stylesheet" href="hidden.css"><main id="entry">'
            '<button id="open">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>'
        )
        self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_css_import_is_rejected_and_later_visible_rule_wins(self) -> None:
        (self.root / "hidden.css").write_text("#click{display:none}", encoding="utf-8")
        self._write_dom_variant(
            '<style>@import url(hidden.css)</style><main id="entry"><button id="open">Open</button>'
            '<button id="click">Click</button><div id="visible">Visible</div></main>'
        )
        self.assertIn("browser-dom-action-mismatch", self.codes())
        self._write_dom_variant(
            '<style>#click{display:none} #click{display:block}</style><main id="entry">'
            '<button id="open">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>'
        )
        self.assertNotIn("browser-dom-action-mismatch", self.codes())
        for markup in (
            '<style>#click{display:none!important}#click{display:block}</style>',
            '<style>#click{display:none!important;display:block}</style>',
            '<style>#click{display:none}#click[data-never]{display:block}</style>',
            '<link rel="stylesheet" href="shown.css"><style>#click{display:none}</style>',
        ):
            with self.subTest(markup=markup):
                (self.root / "shown.css").write_text("#click{display:block}", encoding="utf-8")
                self._write_dom_variant(
                    markup + '<main id="entry"><button id="open">Open</button>'
                    '<button id="click">Click</button><div id="visible">Visible</div></main>'
                )
                self.assertIn("browser-dom-action-mismatch", self.codes())

    def test_hidden_void_element_does_not_hide_following_controls(self) -> None:
        markup = ('<main id="entry"><input type="hidden" name="csrf">'
                  '<button id="open">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>')
        self._write_dom_variant(markup)
        self.assertNotIn("browser-dom-action-mismatch", self.codes())

    def test_every_declared_click_target_must_be_executed(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"] = [item for item in transcript["actions"] if item["target"] != "#click"]
        for sequence, action in enumerate(transcript["actions"], start=1):
            action["sequence"] = sequence
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-action-order", self.codes())

    def test_click_path_order_and_multiplicity_are_exact(self) -> None:
        original = json.loads(self.transcript.read_text(encoding="utf-8"))
        for mode in ("reversed", "duplicate"):
            with self.subTest(mode=mode):
                data = self._evidence()
                transcript = json.loads(json.dumps(original))
                if mode == "reversed":
                    transcript["actions"][1], transcript["actions"][2] = transcript["actions"][2], transcript["actions"][1]
                else:
                    data["browser"]["click_path"] = ["#entry", "#open", "#open", "#click"]
                for sequence, action in enumerate(transcript["actions"], start=1):
                    action["sequence"] = sequence
                self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
                data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
                self.path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("invalid-browser-action-order", self.codes())

    def test_action_computed_state_must_be_visible_and_enabled(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"][1]["visible"] = False
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-action-order", self.codes())

    def test_each_click_requires_a_distinct_asserted_state_transition(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        data["browser"]["state_transitions"] = []
        transcript["state_transitions"] = []
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-state-transitions", self.codes())

    def test_state_transition_hashes_must_bind_snapshot_artifacts(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transitions = data["browser"]["state_transitions"]
        transitions[0]["after_state_path"] = "evidence/missing-state.html"
        transitions[0]["after_state_sha256"] = "4" * 64
        transitions[1]["before_state_path"] = "evidence/missing-state.html"
        transitions[1]["before_state_sha256"] = "4" * 64
        transcript["state_transitions"] = transitions
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-evidence-file", self.codes())

    def test_state_transition_must_change_declared_assertion_dom_state(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        page = (self.root / "index.html").read_text(encoding="utf-8")
        self.after_open.write_text(page.replace('<main id="entry"', '<main id="entry" data-unrelated="changed"'), encoding="utf-8")
        digest = hashlib.sha256(self.after_open.read_bytes()).hexdigest()
        for owner in (data["browser"], transcript):
            owner["state_transitions"][0]["after_state_sha256"] = digest
            owner["state_transitions"][1]["before_state_sha256"] = digest
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-state-snapshot", self.codes())

    def test_state_transition_accepts_visible_text_change(self) -> None:
        page = (self.root / "index.html").read_text(encoding="utf-8")
        self.after_open.write_text(page.replace("Visible</div>", "Opened</div>"), encoding="utf-8")
        self.after_click.write_text(page.replace("Visible</div>", "Clicked</div>"), encoding="utf-8")
        self._sync_transition_artifacts()
        self.assertNotIn("invalid-browser-state-snapshot", self.codes())

    def test_state_transition_rejects_unrelated_attribute_change(self) -> None:
        page = (self.root / "index.html").read_text(encoding="utf-8")
        self.after_open.write_text(page.replace('id="visible"', 'id="visible" data-proof="one"'), encoding="utf-8")
        self.after_click.write_text(page.replace('id="visible"', 'id="visible" data-proof="two"'), encoding="utf-8")
        self._sync_transition_artifacts()
        self.assertIn("invalid-browser-state-snapshot", self.codes())

    def _sync_transition_artifacts(self) -> None:
        data = self._evidence()
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["state_transitions"] = data["browser"]["state_transitions"]
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_invalid_utf8_dom_snapshot_fails_closed(self) -> None:
        page = self.root / "index.html"
        page.write_bytes(b"\xff\xfe")
        self.dom_snapshot.write_bytes(page.read_bytes())
        digest = hashlib.sha256(self.dom_snapshot.read_bytes()).hexdigest()
        data = self._evidence()
        data["browser"].update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript.update({
            "page_artifact_sha256": digest, "observed_response_sha256": digest,
            "dom_snapshot_sha256": digest,
        })
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-dom-evidence-mismatch", self.codes())

    def test_browser_entry_must_match_authoritative_project_manifest(self) -> None:
        decoy = self.root / "decoy.html"
        decoy.write_text("<main>unrelated decoy</main>", encoding="utf-8")
        digest = hashlib.sha256(decoy.read_bytes()).hexdigest()
        data = self._evidence()
        data["browser"].update({
            "page_url": "http://127.0.0.1:9/decoy.html",
            "page_artifact_path": "decoy.html",
            "page_artifact_sha256": digest,
            "observed_response_sha256": digest,
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript.update({key: data["browser"][key] for key in (
            "page_url", "page_artifact_path", "page_artifact_sha256", "observed_response_sha256",
        )})
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-page-authority-mismatch", self.codes())

    def test_authoritative_frontend_url_must_return_live_current_bytes(self) -> None:
        unavailable = "http://127.0.0.1:9/index.html"
        manifest = json.loads(self.commands.read_text(encoding="utf-8"))
        manifest["frontend_preview_url"] = unavailable
        self.commands.write_text(json.dumps(manifest), encoding="utf-8")
        data = self._evidence()
        data["browser"]["page_url"] = unavailable
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_url"] = unavailable
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-page-artifact-mismatch", self.codes())

    def test_file_url_cannot_be_used_as_browser_evidence(self) -> None:
        data = self._evidence()
        data["browser"]["page_url"] = "file:///tmp/index.html"
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_url"] = "file:///tmp/index.html"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-page-url", self.codes())

    def test_browser_page_url_must_match_hashed_transcript(self) -> None:
        data = self._evidence()
        data["browser"]["page_url"] = "https://example.test/current"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-transcript-mismatch", self.codes())

    def test_browser_page_url_must_identify_current_served_artifact(self) -> None:
        data = self._evidence()
        data["browser"]["page_url"] = "https://example.test/unrelated"
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_url"] = "https://example.test/unrelated"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-page-artifact-mismatch", self.codes())

    def test_browser_observed_response_must_match_current_entry_artifact(self) -> None:
        data = self._evidence()
        data["browser"]["observed_response_sha256"] = "0" * 64
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["observed_response_sha256"] = "0" * 64
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-page-artifact-mismatch", self.codes())

    def test_console_error_blocks_pass(self) -> None:
        data = self._evidence()
        data["browser"]["console_errors"] = ["TypeError"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("nonempty-console-errors", self.codes())

    def test_stale_screenshot_hash_fails(self) -> None:
        data = self._evidence()
        data["browser"]["screenshots"][0]["sha256"] = "0" * 64
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-evidence-hash", self.codes())

    def test_frontend_artifact_path_must_be_a_json_string(self) -> None:
        alias = self.root / "True"
        alias.write_bytes(self.screenshot.read_bytes())
        issues = []
        resolved = _validate_hashed_artifact(
            {"path": True, "sha256": hashlib.sha256(alias.read_bytes()).hexdigest()},
            self.root, issues, "browser-screenshot",
        )
        self.assertIsNone(resolved)
        self.assertIn("invalid-evidence-artifact-types", {item.code for item in issues})

    def test_empty_artifacts_and_report_self_report_fail(self) -> None:
        self.screenshot.write_bytes(b"")
        self.report.write_bytes(b"")
        data = self._evidence()
        data["browser"]["screenshots"][0]["sha256"] = hashlib.sha256(b"").hexdigest()
        data["e2e"]["report_sha256"] = hashlib.sha256(b"").hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"empty-evidence-file", "invalid-e2e-report"} & self.codes())

    def test_symlinked_evidence_cannot_escape_project(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\noutside")
        self.screenshot.unlink()
        self.screenshot.symlink_to(outside)
        data = self._evidence()
        data["browser"]["screenshots"][0]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        try:
            self.assertIn("unsafe-evidence-path", self.codes())
        finally:
            outside.unlink(missing_ok=True)

    def test_e2e_report_content_must_match_summary(self) -> None:
        self.report.write_text('{"config":{},"suites":[{"specs":[{"tests":[{}]}]}],"stats":{"expected":99,"unexpected":0}}', encoding="utf-8")
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_empty_playwright_test_tree_cannot_pass_from_summary_counts(self) -> None:
        self.report.write_text('{"config":{},"suites":[],"errors":[],"stats":{"expected":2,"unexpected":0}}', encoding="utf-8")
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_png_signature_without_decodable_image_is_rejected(self) -> None:
        self.screenshot.write_bytes(b"\x89PNG\r\n\x1a\nimage-evidence")
        data = self._evidence()
        data["browser"]["screenshots"][0]["sha256"] = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-screenshot-format", self.codes())

    def test_browser_transcript_hash_and_actions_are_required(self) -> None:
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"] = [{"action": "navigate", "result": "pass"}]
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = self._evidence()
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("incomplete-browser-transcript", self.codes())

    def test_keyword_only_command_cannot_masquerade_as_e2e_runner(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        command = next(item for item in data["commands"] if item["id"] == "frontend_e2e")
        command["argv"] = ["python3", "-m", "unittest", "-k", "playwright"]
        command["source_command"] = "python3 -m unittest -k playwright"
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + "python3 -m unittest -k playwright\n",
            encoding="utf-8",
        )
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-command-framework-mismatch", self.codes())

    def test_echoing_runner_words_cannot_masquerade_as_e2e_runner(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        command = next(item for item in data["commands"] if item["id"] == "frontend_e2e")
        command["argv"] = ["echo", "playwright", "test"]
        command["source_command"] = "echo playwright test"
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + "echo playwright test\n",
            encoding="utf-8",
        )
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-command-framework-mismatch", self.codes())

    def test_project_local_file_named_playwright_cannot_masquerade_as_runner(self) -> None:
        fake = self.root / "tools/playwright"
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text("not a runner", encoding="utf-8")
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        command = next(item for item in data["commands"] if item["id"] == "frontend_e2e")
        command["argv"] = ["tools/playwright", "test"]
        command["source_command"] = "tools/playwright test"
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + "tools/playwright test\n",
            encoding="utf-8",
        )
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-command-framework-mismatch", self.codes())

    def _use_cypress_command(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        command = next(item for item in data["commands"] if item["id"] == "frontend_e2e")
        command["argv"] = ["npx", "cypress", "run"]
        command["source_command"] = "npx cypress run"
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + "npx cypress run\n",
            encoding="utf-8",
        )
        self.commands.write_text(json.dumps(data), encoding="utf-8")

    def test_runner_framework_must_match_evidence_framework(self) -> None:
        self._use_cypress_command()
        data = self._evidence()
        data["e2e"]["command_argv_sha256"] = hashlib.sha256(b"npx\0cypress\0run").hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-runner-framework-mismatch", self.codes())

    def test_native_cypress_mocha_json_report_passes(self) -> None:
        self._use_cypress_command()
        self.report.write_text(json.dumps({
            "stats": {"tests": 2, "passes": 2, "pending": 0, "failures": 0},
            "tests": [{"title": "opens", "fullTitle": "flow opens"}, {"title": "closes", "fullTitle": "flow closes"}],
            "pending": [], "failures": [],
            "passes": [{"title": "opens", "fullTitle": "flow opens"}, {"title": "closes", "fullTitle": "flow closes"}],
        }), encoding="utf-8")
        data = self._evidence()
        data["e2e"].update({
            "framework": "Cypress",
            "command_argv_sha256": hashlib.sha256(b"npx\0cypress\0run").hexdigest(),
            "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("e2e-runner-framework-mismatch", self.codes())
        self.assertNotIn("e2e-report-mismatch", self.codes())

    def test_placeholder_cypress_mocha_json_cannot_pass(self) -> None:
        self._use_cypress_command()
        self.report.write_text(json.dumps({
            "stats": {"tests": 2, "passes": 2, "pending": 0, "failures": 0},
            "tests": [{}, {}], "pending": [], "failures": [], "passes": [{}, {}],
        }), encoding="utf-8")
        data = self._evidence()
        data["e2e"].update({
            "framework": "Cypress",
            "command_argv_sha256": hashlib.sha256(b"npx\0cypress\0run").hexdigest(),
            "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_anonymous_playwright_spec_cannot_pass(self) -> None:
        self.report.write_text(
            '{"config":{},"suites":[{"specs":[{"tests":[{"results":[{"status":"passed"}]},{"results":[{"status":"passed"}]}]}]}],"errors":[],"stats":{"expected":2,"unexpected":0}}',
            encoding="utf-8",
        )
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_playwright_terminal_test_count_must_equal_stats(self) -> None:
        self.report.write_text(
            '{"config":{},"suites":[{"specs":[{"title":"flow.spec.ts","tests":['
            '{"results":[{"status":"passed"}]},{"results":[{"status":"passed"}]},'
            '{"results":[{"status":"passed"}]}]}]}],"errors":[],"stats":{"expected":2,"unexpected":0}}',
            encoding="utf-8",
        )
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_playwright_failed_terminal_state_must_match_unexpected_stats(self) -> None:
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["suites"][0]["specs"][0]["tests"][0]["results"][0]["status"] = "failed"
        self.report.write_text(json.dumps(report), encoding="utf-8")
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_playwright_timeout_or_interrupt_cannot_be_declared_expected(self) -> None:
        for terminal in ("timedOut", "interrupted"):
            with self.subTest(terminal=terminal):
                report = json.loads(self.report.read_text(encoding="utf-8"))
                test = report["suites"][0]["specs"][0]["tests"][0]
                test["expectedStatus"] = terminal
                test["results"][0]["status"] = terminal
                self.report.write_text(json.dumps(report), encoding="utf-8")
                data = self._evidence()
                data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
                self.path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("e2e-report-mismatch", self.codes())
                self.report.write_text(
                    '{"config":{},"suites":[{"specs":[{"title":"opens and closes module","tests":['
                    '{"projectName":"desktop","results":[{"status":"passed"}]},'
                    '{"projectName":"mobile","results":[{"status":"passed"}]}]}]}],'
                    '"errors":[],"stats":{"expected":2,"unexpected":0,"flaky":0,"skipped":0}}',
                    encoding="utf-8",
                )

    def test_playwright_global_errors_block_completion(self) -> None:
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["errors"] = [{"message": "global setup failed"}]
        self.report.write_text(json.dumps(report), encoding="utf-8")
        data = self._evidence()
        data["e2e"]["report_sha256"] = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_native_cypress_results_tree_passes(self) -> None:
        self._use_cypress_command()
        self.report.write_text(json.dumps({
            "stats": {"passes": 2, "failures": 0},
            "results": [{"tests": [
                {"title": ["flow", "opens"], "state": "passed"},
                {"title": ["flow", "closes"], "attempts": [{"state": "passed"}]},
            ]}],
        }), encoding="utf-8")
        data = self._evidence()
        data["e2e"].update({
            "framework": "Cypress",
            "command_argv_sha256": hashlib.sha256(b"npx\0cypress\0run").hexdigest(),
            "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("e2e-report-mismatch", self.codes())

    def test_empty_cypress_results_cannot_pass_from_summary_counts(self) -> None:
        self._use_cypress_command()
        self.report.write_text('{"results":[],"stats":{"passes":2,"failures":0}}', encoding="utf-8")
        data = self._evidence()
        data["e2e"].update({
            "framework": "Cypress",
            "command_argv_sha256": hashlib.sha256(b"npx\0cypress\0run").hexdigest(),
            "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_placeholder_cypress_results_cannot_pass_from_summary_counts(self) -> None:
        self._use_cypress_command()
        self.report.write_text('{"results":[{},{}],"stats":{"passes":2,"failures":0}}', encoding="utf-8")
        data = self._evidence()
        data["e2e"].update({
            "framework": "Cypress",
            "command_argv_sha256": hashlib.sha256(b"npx\0cypress\0run").hexdigest(),
            "report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("e2e-report-mismatch", self.codes())

    def test_mobile_surface_requires_mobile_evidence(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible",
            "Change surfaces: ui,user-visible,mobile",
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        self.assertIn("missing-mobile-evidence", self.codes())

    def test_invalid_or_reversed_times_are_rejected(self) -> None:
        data = self._evidence()
        data["browser"]["started_at"] = "2026-99-99T99:99:99+99:99"
        data["e2e"]["started_at"] = "2026-08-14T12:03:00+08:00"
        data["e2e"]["ended_at"] = "2026-08-14T12:02:00+08:00"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"invalid-browser-time", "invalid-e2e-time"} <= self.codes())

    def test_mobile_evidence_requires_full_run_time_and_transcript(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: ui,user-visible,mobile"
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        data = self._evidence()
        mobile = self._browser()
        for field in ("run_id", "verifier_agent_run_id", "started_at", "ended_at", "transcript_path", "transcript_sha256"):
            mobile.pop(field, None)
        data["mobile"] = mobile
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"missing-browser-run-id", "missing-browser-verifier-run-id"} <= self.codes())

    def test_mobile_evidence_cannot_copy_desktop_viewport_and_artifacts(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: ui,user-visible,mobile"
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        data = self._evidence()
        data["mobile"] = dict(data["browser"])
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"mobile-viewport-not-distinct", "mobile-evidence-reused-desktop"} <= self.codes())

    def test_mobile_evidence_cannot_reuse_run_or_artifact_content_under_new_paths(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: ui,user-visible,mobile"
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        mobile_screenshot = self.root / "evidence/mobile.png"
        mobile_screenshot.write_bytes(self.screenshot.read_bytes())
        mobile_transcript = self.root / "evidence/mobile-transcript.json"
        mobile_transcript.write_bytes(self.transcript.read_bytes())
        data = self._evidence()
        mobile = dict(data["browser"])
        mobile.update({
            "viewport": [390, 844],
            "transcript_path": "evidence/mobile-transcript.json",
            "screenshots": [{
                "path": "evidence/mobile.png",
                "sha256": hashlib.sha256(mobile_screenshot.read_bytes()).hexdigest(),
            }],
        })
        data["mobile"] = mobile
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("mobile-evidence-reused-desktop", self.codes())

    def test_transcript_must_bind_viewport_and_screenshots(self) -> None:
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["viewport"] = [390, 844]
        transcript["screenshots"] = []
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = self._evidence()
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("browser-transcript-artifact-mismatch", self.codes())

    def test_transcript_actions_cover_every_declared_assertion_and_screenshot(self) -> None:
        second = self.root / "evidence/second.png"
        second.write_bytes(self.screenshot.read_bytes())
        data = self._evidence()
        data["browser"]["assertions"].append("second critical assertion")
        data["browser"]["screenshots"].append({
            "path": "evidence/second.png",
            "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["screenshots"] = data["browser"]["screenshots"]
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-browser-action-order", self.codes())


if __name__ == "__main__":
    unittest.main()
