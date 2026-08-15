from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_delivery_bundle as bundle_support
from validate_swimlane_evidence import _ordered_actions, _validate_hashed_file, validate_swimlane_evidence


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets/swimlane-evidence.template.json"
HTML = '<section id="system-overview"><div class="lane-head">Lane</div><path class="flow"></path><a id="open-module" href="#module" data-open-module="module">Open</a><details id="module"></details><a class="back-link" href="#system-overview">Back</a></section>'


class SwimlaneEvidenceValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = bundle_support.DeliveryBundleValidatorTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        (self.root / "flows/swimlane-system.html").write_text(HTML, encoding="utf-8")
        (self.root / "flows/module.html").write_text(HTML, encoding="utf-8")
        transcript = {
            "tool": "browser:control-in-app-browser",
            "run_id": "browser-run-1",
            "page_url": self.fixture.swimlane_url,
            "preview_root": ".",
            "page_artifact_path": "flows/swimlane-system.html",
            "page_artifact_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
            "observed_response_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
            "actions": [
                {"sequence": 1, "action": "navigate", "target": "system", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 2, "action": "click", "target": "module", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 3, "action": "assert", "target": "module", "result": "pass", "visible": True, "enabled": True},
            ],
            "modules_opened": ["module"],
            "assertions": {"single_module_open": True, "lane_headers_visible": True,
                           "connectors_visible": True, "back_to_overview": True},
            "console_errors": [],
            "verdict": "pass",
        }
        self.transcript = self.root / "evidence/swimlane-browser.json"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path = self.root / "swimlane-evidence.json"
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def valid_data(self) -> dict[str, object]:
        baseline = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        diagrams = []
        for module, relative in (("system", "flows/swimlane-system.html"), ("module", "flows/module.html")):
            diagrams.append({
                "module": module,
                "path": relative,
                "sha256": hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
                "code_evidence": ["src/module.py"],
            })
        return {
            "schema_version": 1, "baseline_version": "req-v1", "baseline_sha256": baseline,
            "code_version": "code-v1", "build_id": "build-1", "run_id": "impl-run-1",
            "diagrams": diagrams,
            "browser": {"tool": "browser:control-in-app-browser", "run_id": "browser-run-1",
                        "page_url": self.fixture.swimlane_url,
                        "preview_root": ".",
                        "page_artifact_path": "flows/swimlane-system.html",
                        "page_artifact_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
                        "observed_response_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
                        "transcript_path": "evidence/swimlane-browser.json",
                        "transcript_sha256": hashlib.sha256(self.transcript.read_bytes()).hexdigest()},
            "verdict": "pass",
        }

    def codes(self) -> set[str]:
        return {item.code for item in validate_swimlane_evidence(
            self.path, trace_path=self.fixture.trace_fixture.matrix, context_path=self.fixture.context,
            project_root=self.root,
        )}

    def test_public_template_structure_passes(self) -> None:
        self.assertEqual([], validate_swimlane_evidence(
            PUBLIC_TEMPLATE, trace_path=self.fixture.trace_fixture.matrix, context_path=self.fixture.context,
            project_root=self.root, template=True,
        ))

    def test_template_mode_rejects_invalid_nested_diagram_and_browser(self) -> None:
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["diagrams"][0]["module"] = True
        data["browser"] = {}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_swimlane_evidence(
            self.path, trace_path=self.fixture.trace_fixture.matrix, context_path=self.fixture.context,
            project_root=self.root, template=True,
        )}
        self.assertTrue({"invalid-swimlane-diagram-types", "invalid-swimlane-browser-fields"} <= codes)

    def test_valid_swimlane_evidence_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_malformed_diagrams_fail_closed_without_exception(self) -> None:
        data = self.valid_data()
        data["diagrams"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-swimlane-diagrams", self.codes())

    def test_system_drilldown_targets_must_match_current_modules(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(HTML.replace('data-open-module="module"', 'data-open-module="garbage"'), encoding="utf-8")
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("swimlane-drilldown-target-mismatch", self.codes())

    def test_system_drilldown_controls_require_href_and_target_id(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(HTML.replace('href="#module"', ""), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_hidden_drilldown_controls_and_targets_are_rejected(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        hidden = HTML.replace(
            '<a id="open-module"', '<a id="open-module" hidden aria-hidden="true"',
        ).replace('<details id="module">', '<details id="module" hidden>').replace(
            '<a class="back-link"', '<a class="back-link" hidden',
        )
        system.write_text(hidden, encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_hidden_noninteractive_drilldown_is_rejected(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(
            '<section id="system-overview">'
            '<div class="lane-head">Lane</div><path class="flow"></path>'
            '<div id="fake" href="#module" data-open-module="module">Open</div>'
            '<details id="module"></details><a class="back-link" href="#system-overview">Back</a></section>',
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_hidden_drilldown_anchor_is_rejected(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(
            '<style>section [data-open-module],section #module,section .back-link{display:none}</style><section id="system-overview">'
            '<div class="lane-head">Lane</div><path class="flow"></path>'
            '<a id="open-module" href="#module" data-open-module="module">Open</a>'
            '<details id="module"></details><a class="back-link" href="#system-overview">Back</a></section>',
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_combinators_and_linked_styles_hide_drilldown(self) -> None:
        cases = (
            '<style>section>[data-open-module],section>#module,section>.back-link{display:none}</style>',
            '<link rel="stylesheet" href="hidden.css">',
        )
        (self.root / "flows/hidden.css").write_text(
            '[data-open-module],#module,.back-link{display:none}', encoding="utf-8",
        )
        for prefix in cases:
            with self.subTest(prefix=prefix):
                system = self.root / "flows/swimlane-system.html"
                system.write_text(prefix + HTML, encoding="utf-8")
                self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
                self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_not_selector_hides_matching_drilldown(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(
            '<style>[data-open-module]:not(.shown){display:none}</style>' + HTML,
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_not_selector_respects_excluded_class(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        markup = HTML.replace('id="open-module"', 'id="open-module" class="shown"')
        system.write_text(
            '<style>[data-open-module]:not(.shown){display:none}</style>' + markup,
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertNotIn("invalid-swimlane-drilldown-control", self.codes())

    def test_css_not_selector_supports_multiple_drilldown_exclusions(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        for classes, should_hide in (("", True), ("shown", False), ("active", False)):
            with self.subTest(classes=classes):
                class_attr = f' class="{classes}"' if classes else ""
                markup = HTML.replace('id="open-module"', f'id="open-module"{class_attr}')
                system.write_text(
                    '<style>[data-open-module]:not(.shown,.active){display:none}</style>' + markup,
                    encoding="utf-8",
                )
                self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
                codes = self.codes()
                if should_hide:
                    self.assertIn("invalid-swimlane-drilldown-control", codes)
                else:
                    self.assertNotIn("invalid-swimlane-drilldown-control", codes)

    def test_css_import_is_rejected_and_later_visible_rule_wins(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text('<style>@import url(hidden.css)</style>' + HTML, encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())
        system.write_text(
            '<style>[data-open-module]{display:none}[data-open-module]{display:block}</style>' + HTML,
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertNotIn("invalid-swimlane-drilldown-control", self.codes())
        (self.root / "flows/shown.css").write_text("[data-open-module]{display:block}", encoding="utf-8")
        for prefix in (
            '<style>[data-open-module]{display:none!important}[data-open-module]{display:block}</style>',
            '<style>[data-open-module]{display:none!important;display:block}</style>',
            '<style>[data-open-module]{display:none}[data-open-module].nonexistent{display:block}</style>',
            '<link rel="stylesheet" href="shown.css"><style>[data-open-module]{display:none}</style>',
        ):
            with self.subTest(prefix=prefix):
                system.write_text(prefix + HTML, encoding="utf-8")
                self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
                self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_hidden_void_element_does_not_hide_following_swimlane_controls(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(HTML.replace(
            '<a id="open-module"', '<input hidden name="csrf"><a id="open-module"',
        ), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertNotIn("invalid-swimlane-drilldown-control", self.codes())

    def test_noninteractive_back_control_is_rejected(self) -> None:
        system = self.root / "flows/swimlane-system.html"
        system.write_text(
            '<section id="system-overview"><div class="lane-head">Lane</div><path class="flow"></path>'
            '<a id="open-module" href="#module" data-open-module="module">Open</a>'
            '<details id="module"></details><div class="back-link" href="#system-overview">Back</div></section>',
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-drilldown-control", self.codes())

    def test_swimlane_action_computed_state_must_be_enabled(self) -> None:
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"][1]["enabled"] = False
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = self.valid_data()
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-swimlane-action-order", self.codes())

    def test_file_url_cannot_be_used_as_swimlane_browser_evidence(self) -> None:
        data = self.valid_data()
        data["browser"]["page_url"] = "file:///tmp/swimlane-system.html"
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_url"] = "file:///tmp/swimlane-system.html"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-swimlane-page-url", self.codes())

    def test_swimlane_page_url_must_match_hashed_transcript(self) -> None:
        data = self.valid_data()
        data["browser"]["page_url"] = "https://example.test/current-swimlane"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("swimlane-browser-transcript-mismatch", self.codes())

    def test_swimlane_page_url_must_serve_current_system_diagram(self) -> None:
        data = self.valid_data()
        data["browser"]["page_url"] = "https://example.test/flows/swimlane-system.html"
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["page_url"] = "https://example.test/flows/swimlane-system.html"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        digest = data["browser"]["observed_response_sha256"]
        with patch("browser_page_validation._http_response_hash", return_value=digest):
            self.assertIn("swimlane-page-artifact-mismatch", self.codes())

    def test_swimlane_browser_cannot_serve_module_diagram_as_system_overview(self) -> None:
        data = self.valid_data()
        data["browser"].update({
            "page_url": self.fixture.http.url("flows/module.html"),
            "page_artifact_path": "flows/module.html",
            "page_artifact_sha256": hashlib.sha256((self.root / "flows/module.html").read_bytes()).hexdigest(),
            "observed_response_sha256": hashlib.sha256((self.root / "flows/module.html").read_bytes()).hexdigest(),
        })
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript.update({key: data["browser"][key] for key in (
            "page_url", "page_artifact_path", "page_artifact_sha256", "observed_response_sha256",
        )})
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("swimlane-page-artifact-mismatch", self.codes())

    def test_boolean_schema_version_is_rejected(self) -> None:
        data = self.valid_data()
        data["schema_version"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-schema-version", self.codes())

    def test_duplicate_or_unknown_browser_transcript_fields_fail_closed(self) -> None:
        raw = self.transcript.read_text(encoding="utf-8").replace(
            '"console_errors": []',
            '"console_errors": ["fatal"], "console_errors": []',
        )
        self.transcript.write_text(raw, encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-browser-transcript", self.codes())
        transcript = json.loads(raw)
        transcript["unknown_failure_state"] = "P1 unresolved"
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-transcript-fields", self.codes())

    def test_swimlane_identity_and_actions_are_strictly_typed_and_ordered(self) -> None:
        data = self.valid_data()
        data["build_id"] = 456
        data["run_id"] = 123
        data["browser"]["run_id"] = 789
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"invalid-swimlane-identity-types", "missing-swimlane-browser-run"} <= self.codes())
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"][0].pop("target")
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-action-fields", self.codes())

    def test_swimlane_actions_reject_reverse_unknown_and_unbound_targets(self) -> None:
        actions = json.loads(self.transcript.read_text(encoding="utf-8"))["actions"]
        self.assertTrue(_ordered_actions(actions, {"module"}))
        reversed_actions = [dict(item) for item in reversed(actions)]
        for index, action in enumerate(reversed_actions, start=1):
            action["sequence"] = index
        self.assertFalse(_ordered_actions(reversed_actions, {"module"}))
        unknown = [*actions, {"sequence": 4, "action": 123, "target": "bogus", "result": "pass", "visible": True, "enabled": True}]
        self.assertFalse(_ordered_actions(unknown, {"module"}))
        unrelated = [dict(item, target="unrelated-target") for item in actions]
        self.assertFalse(_ordered_actions(unrelated, {"module"}))
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["actions"] = reversed_actions
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        self.path.write_text(json.dumps(self.valid_data()), encoding="utf-8")
        self.assertIn("invalid-swimlane-action-order", self.codes())

    def test_swimlane_diagram_module_and_code_evidence_must_be_strings(self) -> None:
        data = self.valid_data()
        data["diagrams"][1]["module"] = True
        data["diagrams"][0]["code_evidence"] = [True]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({
            "duplicate-or-missing-swimlane-module", "missing-swimlane-code-evidence",
        } <= self.codes())

    def test_missing_module_swimlane_fails(self) -> None:
        data = self.valid_data()
        data["diagrams"] = [item for item in data["diagrams"] if item["module"] == "system"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-swimlane-module", self.codes())

    def test_changed_diagram_invalidates_hash(self) -> None:
        (self.root / "flows/module.html").write_text(HTML + "changed", encoding="utf-8")
        self.assertIn("stale-swimlane-diagram", self.codes())

    def test_swimlane_artifact_path_must_be_a_json_string(self) -> None:
        alias = self.root / "True"
        alias.write_text(HTML, encoding="utf-8")
        issues = []
        resolved = _validate_hashed_file(
            True, hashlib.sha256(alias.read_bytes()).hexdigest(), self.root,
            "swimlane-diagram", issues,
        )
        self.assertIsNone(resolved)
        self.assertIn("unsafe-swimlane-diagram-path", {item.code for item in issues})

    def test_incomplete_browser_module_clicks_fail(self) -> None:
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        transcript["modules_opened"] = []
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = self.valid_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("incomplete-swimlane-module-clicks", self.codes())

    def test_every_changed_file_must_be_covered_by_swimlanes(self) -> None:
        other = self.root / "src/other.py"
        other.write_text("other", encoding="utf-8")
        context = self.fixture.context.read_text(encoding="utf-8").replace(
            "- Changed files: src/module.py",
            "- Changed files: src/module.py, src/other.py",
        )
        from validate_context_manifest import _cache_key, _parse_metadata, _paths_fingerprint
        metadata, _ = _parse_metadata(context)
        code_hash = _paths_fingerprint("src/module.py, src/other.py", self.root.resolve(), [], "changed-file")
        context = context.replace(metadata["Code fingerprint"], code_hash)
        metadata["Code fingerprint"] = code_hash
        context = context.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.fixture.context.write_text(context, encoding="utf-8")
        self.assertIn("uncovered-swimlane-changed-file", self.codes())

    def test_two_modules_require_distinct_correctly_owned_diagrams(self) -> None:
        data = self._two_module_data()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(set(), self.codes())
        data["diagrams"][2]["code_evidence"] = ["src/module.py"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("swimlane-code-evidence-mismatch", self.codes())

    def test_diagram_roles_cannot_share_path_or_hardlink(self) -> None:
        module_path = self.root / "flows/module.html"
        module_path.unlink()
        os.link(self.root / "flows/swimlane-system.html", module_path)
        self.assertIn("reused-swimlane-diagram", self.codes())

    def _two_module_data(self) -> dict[str, object]:
        (self.root / "src/other.py").write_text("other", encoding="utf-8")
        (self.root / "flows/module2.html").write_text(HTML + "module2", encoding="utf-8")
        system = self.root / "flows/swimlane-system.html"
        system.write_text(
            HTML + '<a href="#module2" data-open-module="module2">Open module2</a><details id="module2"></details>',
            encoding="utf-8",
        )
        context = self.fixture.context.read_text(encoding="utf-8")
        context = context.replace("- Modules: module", "- Modules: module, module2")
        context = context.replace(
            "- Module changed files: module=src/module.py",
            "- Module changed files: module=src/module.py; module2=src/other.py",
        ).replace("- Changed files: src/module.py", "- Changed files: src/module.py, src/other.py")
        from validate_context_manifest import _cache_key, _parse_metadata, _paths_fingerprint
        metadata, _ = _parse_metadata(context)
        code_hash = _paths_fingerprint("src/module.py, src/other.py", self.root.resolve(), [], "changed-file")
        context = context.replace(metadata["Code fingerprint"], code_hash)
        metadata["Code fingerprint"] = code_hash
        context = context.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.fixture.context.write_text(context, encoding="utf-8")
        transcript = json.loads(self.transcript.read_text(encoding="utf-8"))
        system_hash = hashlib.sha256(system.read_bytes()).hexdigest()
        transcript["page_artifact_sha256"] = system_hash
        transcript["observed_response_sha256"] = system_hash
        transcript["modules_opened"] = ["module", "module2"]
        transcript["actions"].insert(
            2, {"sequence": 3, "action": "click", "target": "module2", "result": "pass", "visible": True, "enabled": True},
        )
        for index, action in enumerate(transcript["actions"], start=1):
            action["sequence"] = index
        self.transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = self.valid_data()
        data["diagrams"][0]["code_evidence"] = ["src/module.py", "src/other.py"]
        data["diagrams"].append({
            "module": "module2", "path": "flows/module2.html",
            "sha256": hashlib.sha256((self.root / "flows/module2.html").read_bytes()).hexdigest(),
            "code_evidence": ["src/other.py"],
        })
        data["browser"]["transcript_sha256"] = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        return data


if __name__ == "__main__":
    unittest.main()
