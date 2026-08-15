from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_validate_agents_md import project_root_fixture
import test_validate_traceability as trace_test_support
from validate_context_manifest import _cache_key, _paths_fingerprint
from delivery_record_validation import _module_changed_files
from validate_delivery_bundle import _frontend_applicable, _metadata_binding_issues, validate_delivery_bundle
from validate_project_commands import REQUIRED_COMMANDS
from test_http_server import ProjectHttpServer
from test_execution_run_support import reusable_execution_run
from test_image_support import png_bytes


class DeliveryBundleValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_fixture = trace_test_support.TraceabilityValidatorTests()
        self.trace_fixture.setUp()
        self.root = self.trace_fixture.root
        self.http = ProjectHttpServer(self.root)
        self.frontend_url = self.http.url("index.html")
        self.swimlane_url = self.http.url("flows/swimlane-system.html")
        self.agents = self.root / "AGENTS.md"
        self.agents.write_text(project_root_fixture(), encoding="utf-8")
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        docs = self.root / "docs"
        docs.mkdir()
        self.plan = docs / "development_plan_path.md"
        self.plan.write_text(
            f"""# Development Plan

- Baseline version: req-v1
- Baseline SHA-256: {baseline_sha}
- Objective: deliver approved REQ-001
- Scope: module only
- Ordered steps: implement, verify, accept
- Verification criteria: all declared gates pass
- Known risks: user-visible regression
""",
            encoding="utf-8",
        )
        self.progress = docs / "progress_record_path.md"
        self.progress.write_text(
            """# Completion Progress

- Run ID: impl-run-1
- Code version: code-v1
- Modules: module
- Module run records: module=docs/module_execution_log_directory/module/run-impl-run-1.md
- Module latest records: module=docs/module_execution_log_directory/module/latest.md
- Completion date: 2026-08-14
- Delivered result: approved module behavior
- Validation performed: unit, E2E, black-box
- Remaining work: none
- Status: completed
""",
            encoding="utf-8",
        )
        (self.root / "commands.txt").write_text("unittest\npython3 -m unittest\npython3 -m playwright test\n", encoding="utf-8")
        self.commands = self.root / "commands.json"
        self.commands.write_text(json.dumps(self._command_manifest()), encoding="utf-8")
        self.context = self.root / "context.md"
        self.context.write_text(self._context_manifest(), encoding="utf-8")
        self.review = docs / "automated_review_evidence_path.md"
        review_argv_sha = hashlib.sha256(b"python3\0-m\0unittest").hexdigest()
        code_fingerprint = _paths_fingerprint("src/module.py", self.root.resolve(), [], "changed-file")
        command_manifest_fingerprint = _paths_fingerprint("commands.json", self.root.resolve(), [], "command-manifest")
        review_output = self.root / "evidence/automated-review.json"
        review_output.write_text(json.dumps({
            "schema_version": 1, "implementation_run_id": "impl-run-1", "code_version": "code-v1",
            "code_fingerprint": code_fingerprint, "changed_files": ["src/module.py"],
            "command_manifest_fingerprint": command_manifest_fingerprint,
            "command_id": "automated_review", "argv_sha256": review_argv_sha, "exit_code": 0,
            "started_at": "2026-08-14T11:00:00+08:00", "ended_at": "2026-08-14T11:01:00+08:00",
            "findings": [], "reruns": {
                "automated_review": 0, "code_standards": 0, "swimlane_evidence": 0,
                "targeted_tests": 0, "traceability": 0,
            },
        }), encoding="utf-8")
        review_evidence_sha = hashlib.sha256(review_output.read_bytes()).hexdigest()
        self.review.write_text(
            f"""# Automated Review Evidence

- Run ID: impl-run-1
- Code version: code-v1
- Code fingerprint: {code_fingerprint}
- Command manifest fingerprint: {command_manifest_fingerprint}
- Scope: src/module.py; callers; callees; interfaces; configuration; tests; traceability; swimlanes
- Changed files: src/module.py
- Review command ID: automated_review
- Review command argv SHA-256: {review_argv_sha}
- Review exit code: 0
- Review evidence path: evidence/automated-review.json
- Review evidence SHA-256: {review_evidence_sha}
- Findings: none
- Rerun command IDs: automated_review, code_standards, swimlane_evidence, targeted_tests, traceability
- Rerun exit codes: automated_review=0, code_standards=0, swimlane_evidence=0, targeted_tests=0, traceability=0
- Verdict: pass
""",
            encoding="utf-8",
        )
        self.module_log_dir = docs / "module_execution_log_directory" / "module"
        self.module_log_dir.mkdir(parents=True)
        self.module_run = self.module_log_dir / "run-impl-run-1.md"
        self.module_run.write_text(self._module_run_record(), encoding="utf-8")
        self.module_latest = self.module_log_dir / "latest.md"
        self.module_latest.write_text(self._module_latest_record(), encoding="utf-8")
        for relative in ("evidence/change-input.md", "evidence/change-output.md"):
            (self.root / relative).write_text(relative, encoding="utf-8")
        self.multi_agent = self.root / "multi-agent.json"
        self._write_agent_inputs()
        self._write_agent_outputs()
        self.multi_agent.write_text(json.dumps(self._multi_agent_evidence()), encoding="utf-8")
        page = '<main id="entry">current frontend build<button id="open">Open</button><button id="click">Click</button><div id="visible">Visible</div></main>'
        (self.root / "index.html").write_text(page, encoding="utf-8")
        (self.root / "evidence/browser-dom.html").write_text(page, encoding="utf-8")
        (self.root / "evidence/state-after-open.html").write_text(
            page.replace('id="visible"', 'id="visible" data-state="open"'), encoding="utf-8",
        )
        (self.root / "evidence/state-after-click.html").write_text(
            page.replace('id="visible"', 'id="visible" data-state="clicked"'), encoding="utf-8",
        )
        (self.root / "evidence/frontend.png").write_bytes(png_bytes(1280, 720))
        (self.root / "evidence/playwright.json").write_text('{"config":{},"suites":[{"specs":[{"title":"opens and closes module","tests":[{"projectName":"desktop","results":[{"status":"passed"}]},{"projectName":"mobile","results":[{"status":"passed"}]}]}]}],"errors":[],"stats":{"expected":2,"unexpected":0,"flaky":0,"skipped":0}}', encoding="utf-8")
        browser_transcript = {
            "tool": "browser:control-in-app-browser", "run_id": "browser-run-1", "verifier_agent_run_id": "bb-run-1",
            "page_url": self.frontend_url,
            "preview_root": ".",
            "page_artifact_path": "index.html",
            "page_artifact_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "observed_response_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
            "dom_snapshot_path": "evidence/browser-dom.html",
            "dom_snapshot_sha256": hashlib.sha256((self.root / "evidence/browser-dom.html").read_bytes()).hexdigest(),
            "started_at": "2026-08-14T12:00:00+08:00", "ended_at": "2026-08-14T12:01:00+08:00",
            "viewport": [1280, 720],
            "screenshots": [{"path": "evidence/frontend.png", "sha256": hashlib.sha256(
                (self.root / "evidence/frontend.png").read_bytes()).hexdigest()}],
            "actions": [
                {"sequence": 1, "action": "navigate", "target": "#entry", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 2, "action": "click", "target": "#open", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 3, "action": "click", "target": "#click", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 4, "action": "assert", "target": "#visible", "result": "pass", "visible": True, "enabled": True},
                {"sequence": 5, "action": "screenshot", "target": "evidence/frontend.png", "result": "pass", "visible": True, "enabled": True},
            ],
            "state_transitions": [
                {"click_target": "#open", "assertion_target": "#visible", "before_state_path": "evidence/browser-dom.html", "before_state_sha256": hashlib.sha256((self.root / "evidence/browser-dom.html").read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-open.html", "after_state_sha256": hashlib.sha256((self.root / "evidence/state-after-open.html").read_bytes()).hexdigest()},
                {"click_target": "#click", "assertion_target": "#visible", "before_state_path": "evidence/state-after-open.html", "before_state_sha256": hashlib.sha256((self.root / "evidence/state-after-open.html").read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-click.html", "after_state_sha256": hashlib.sha256((self.root / "evidence/state-after-click.html").read_bytes()).hexdigest()},
            ],
            "console_errors": [], "required_request_failures": [],
        }
        (self.root / "evidence/browser-transcript.json").write_text(json.dumps(browser_transcript), encoding="utf-8")
        self.frontend = self.root / "frontend.json"
        self.frontend.write_text(json.dumps(self._frontend_evidence()), encoding="utf-8")
        swimlane_html = '<section id="system-overview"><div class="lane-head">Lane</div><path class="flow"></path><a id="open-module" href="#module" data-open-module="module">Open</a><details id="module"></details><a class="back-link" href="#system-overview">Back</a></section>'
        (self.root / "flows/swimlane-system.html").write_text(swimlane_html, encoding="utf-8")
        (self.root / "flows/module.html").write_text(swimlane_html, encoding="utf-8")
        transcript = {
            "tool": "browser:control-in-app-browser", "run_id": "swimlane-browser-run-1",
            "page_url": self.swimlane_url,
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
            "console_errors": [], "verdict": "pass",
        }
        (self.root / "evidence/swimlane-browser.json").write_text(json.dumps(transcript), encoding="utf-8")
        self.swimlane = self.root / "swimlane.json"
        self.swimlane.write_text(json.dumps(self._swimlane_evidence()), encoding="utf-8")

    def tearDown(self) -> None:
        self.http.close()
        self.trace_fixture.tearDown()

    def _context_manifest(
        self, *, code_version: str = "code-v1",
        risk_reason: str = "standard; user-visible interaction; no expansion",
    ) -> str:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        empty = hashlib.sha256(b"").hexdigest()
        code = _paths_fingerprint("src/module.py", self.root.resolve(), [], "changed-file")
        command = hashlib.sha256(b"python3 -m unittest").hexdigest()
        command_manifest = _paths_fingerprint("commands.json", self.root.resolve(), [], "command-manifest")
        values = {
            "Baseline artifact": "requirements/baseline.md",
            "Baseline version": "req-v1",
            "Baseline SHA-256": baseline_sha,
            "Requirement IDs": "REQ-001",
            "Module changed files": "module=src/module.py",
            "Risk / expansion reason": risk_reason,
            "Direct dependency boundaries": "direct callers and tests",
            "Code version": code_version,
            "Build ID": "build-1",
            "Code fingerprint": code,
            "Command fingerprint": command,
            "Effective AGENTS fingerprint": _paths_fingerprint("AGENTS.md", self.root.resolve(), [], "agents-file"),
            "Command manifest fingerprint": command_manifest,
            "Configuration fingerprint": empty,
            "Environment ID": "local-release",
            "Input fingerprint": empty,
            "Evidence fingerprint": _paths_fingerprint("evidence/black-box.md", self.root.resolve(), [], "reuse-evidence"),
        }
        cache_key = _cache_key(values)
        source_run = self.root / "docs/reuse_runs/run-prior-run.md"
        source_run.parent.mkdir(parents=True, exist_ok=True)
        source_context = source_run.parent / "context-prior-run.md"
        source_context.write_text(
            f"# Context Workset prior-run\n\n- Run ID: prior-run\n- Evidence cache key: {cache_key}\n",
            encoding="utf-8",
        )
        source_run.write_text(reusable_execution_run(
            "prior-run", cache_key, "evidence/black-box.md",
            baseline_sha=baseline_sha, risk_reason=risk_reason,
            build_id="build-1", environment_id="local-release",
            source_context_path="docs/reuse_runs/context-prior-run.md",
        ), encoding="utf-8")
        reuse_record = self.root / "evidence/reuse-prior-run.json"
        reuse_record.write_text(json.dumps({
            "schema_version": 1,
            "run_id": "prior-run",
            "status": "passed",
            "evidence_cache_key": cache_key,
            "source_run_record": {
                "module": "module",
                "path": "docs/reuse_runs/run-prior-run.md",
                "sha256": hashlib.sha256(source_run.read_bytes()).hexdigest(),
                "context_path": "docs/reuse_runs/context-prior-run.md",
                "context_sha256": hashlib.sha256(source_context.read_bytes()).hexdigest(),
            },
            "evidence_paths": [{
                "path": "evidence/black-box.md",
                "sha256": hashlib.sha256((self.root / "evidence/black-box.md").read_bytes()).hexdigest(),
            }],
        }), encoding="utf-8")
        return f"""# Context Workset impl-run-1

- Run ID: impl-run-1
- Baseline artifact: requirements/baseline.md
- Baseline version: req-v1
- Baseline SHA-256: {baseline_sha}
- Code version: {code_version}
- Build ID: build-1
- Risk / expansion reason: {risk_reason}
- Requirement IDs: REQ-001
- Modules: module
- Module changed files: module=src/module.py
- Changed files: src/module.py
- Configuration files: N/A: no configuration inputs
- Input files: N/A: no external inputs
- Direct dependency boundaries: direct callers and tests
- Required commands: python3 -m unittest
- Effective AGENTS files: AGENTS.md
- Effective AGENTS fingerprint: {values["Effective AGENTS fingerprint"]}
- Command manifest: commands.json
- Command manifest fingerprint: {command_manifest}
- Code fingerprint: {code}
- Command fingerprint: {command}
- Configuration fingerprint: {empty}
- Environment ID: local-release
- Input fingerprint: {empty}
- Evidence fingerprint: {values["Evidence fingerprint"]}
- Evidence cache key: {cache_key}
- Reuse decision: reuse: prior-run
- Reuse record: evidence/reuse-prior-run.json
- Evidence paths: evidence/black-box.md
"""

    def _module_run_record(
        self, *, status: str = "completed",
        risk_reason: str = "standard; user-visible interaction; no expansion",
    ) -> str:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        context_text = self.context.read_text(encoding="utf-8")
        cache_key = re.search(r"^- Evidence cache key: (.+)$", context_text, re.MULTILINE).group(1)
        return f"""# Run impl-run-1

- Run ID: impl-run-1
- Module: module
- Status: {status}
- Code version: code-v1
- Context cache key: {cache_key}
- Baseline version and SHA-256: req-v1 / {baseline_sha}
- Build ID and acceptance environment: build-1 / local-release
- Risk level and reason: {risk_reason}
- Traceability IDs: REQ-001
- Changed files: src/module.py
- Delivered result: approved module behavior
- Context workset manifest and reused evidence fingerprints: context.md / {cache_key}
- Automated review evidence: docs/automated_review_evidence_path.md
- Independent review evidence: multi-agent.json
- Verification evidence: swimlane.json, frontend.json
- Swimlane evidence: swimlane.json
- Frontend evidence: frontend.json
- Swimlane diagrams and validated evidence: flows/swimlane-system.html, flows/module.html, swimlane.json
- Remaining risks: none
"""

    def _module_latest_record(self) -> str:
        return """# Latest module

- Module: module
- Run ID: impl-run-1
- Code version: code-v1
- Status: completed
- Record: docs/module_execution_log_directory/module/run-impl-run-1.md
- Delivered result: approved module behavior
- Verification evidence: swimlane.json, frontend.json
- Swimlane evidence: swimlane.json
- Remaining risks: none
"""

    def _command_manifest(self) -> dict[str, object]:
        commands = [
            {
                "id": command_id,
                "argv": ["python3", "-m", "unittest"],
                "source": "commands.txt",
                "source_selector": "unittest",
                "source_command": "python3 -m unittest",
                "working_directory": ".",
                "applicability": "required",
            }
            for command_id in sorted(REQUIRED_COMMANDS)
        ]
        commands.append({
            "id": "frontend_evidence",
            "argv": ["python3", "-m", "unittest"],
            "source": "commands.txt",
            "source_selector": "unittest",
            "source_command": "python3 -m unittest",
            "working_directory": ".",
            "applicability": "required",
        })
        commands.append({
            "id": "frontend_e2e",
            "argv": ["python3", "-m", "playwright", "test"],
            "source": "commands.txt",
            "source_selector": "unittest",
            "source_command": "python3 -m playwright test",
            "working_directory": ".",
            "applicability": "required",
        })
        return {
            "schema_version": 1,
            "frontend_applicable": True,
            "frontend_preview_url": self.frontend_url,
            "frontend_preview_root": ".",
            "frontend_entry_artifact": "index.html",
            "commands": commands,
        }

    def _frontend_evidence(self) -> dict[str, object]:
        digest = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        return {
            "schema_version": 1, "baseline_version": "req-v1", "baseline_sha256": digest,
            "code_version": "code-v1", "build_id": "build-1", "run_id": "impl-run-1",
            "browser": {"tool": "browser:control-in-app-browser", "run_id": "browser-run-1", "verifier_agent_run_id": "bb-run-1",
                        "page_url": self.frontend_url,
                        "preview_root": ".", "page_artifact_path": "index.html",
                        "page_artifact_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
                        "observed_response_sha256": hashlib.sha256((self.root / "index.html").read_bytes()).hexdigest(),
                        "dom_snapshot_path": "evidence/browser-dom.html",
                        "dom_snapshot_sha256": hashlib.sha256((self.root / "evidence/browser-dom.html").read_bytes()).hexdigest(),
                        "started_at": "2026-08-14T12:00:00+08:00", "ended_at": "2026-08-14T12:01:00+08:00",
                        "transcript_path": "evidence/browser-transcript.json",
                        "transcript_sha256": hashlib.sha256((self.root / "evidence/browser-transcript.json").read_bytes()).hexdigest(),
                        "verdict": "pass", "viewport": [1280, 720],
                        "click_path": ["#entry", "#open", "#click"], "assertions": ["#visible"],
                        "state_transitions": [
                            {"click_target": "#open", "assertion_target": "#visible", "before_state_path": "evidence/browser-dom.html", "before_state_sha256": hashlib.sha256((self.root / "evidence/browser-dom.html").read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-open.html", "after_state_sha256": hashlib.sha256((self.root / "evidence/state-after-open.html").read_bytes()).hexdigest()},
                            {"click_target": "#click", "assertion_target": "#visible", "before_state_path": "evidence/state-after-open.html", "before_state_sha256": hashlib.sha256((self.root / "evidence/state-after-open.html").read_bytes()).hexdigest(), "after_state_path": "evidence/state-after-click.html", "after_state_sha256": hashlib.sha256((self.root / "evidence/state-after-click.html").read_bytes()).hexdigest()},
                        ],
                        "console_errors": [], "required_request_failures": [],
                        "screenshots": [{"path": "evidence/frontend.png", "sha256": hashlib.sha256((self.root / "evidence/frontend.png").read_bytes()).hexdigest()}]},
            "e2e": {"framework": "Playwright", "command_id": "frontend_e2e", "execution_run_id": "e2e-run-1",
                    "started_at": "2026-08-14T12:01:00+08:00", "ended_at": "2026-08-14T12:02:00+08:00",
                    "command_argv_sha256": hashlib.sha256(b"python3\0-m\0playwright\0test").hexdigest(),
                    "exit_code": 0, "passed": 2, "failed": 0,
                    "report_path": "evidence/playwright.json", "report_sha256": hashlib.sha256((self.root / "evidence/playwright.json").read_bytes()).hexdigest()},
            "mobile": "N/A: not approved", "verdict": "pass",
        }

    def _swimlane_evidence(self) -> dict[str, object]:
        baseline = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        diagrams = [
            {"module": module, "path": path,
             "sha256": hashlib.sha256((self.root / path).read_bytes()).hexdigest(),
             "code_evidence": ["src/module.py"]}
            for module, path in (("system", "flows/swimlane-system.html"), ("module", "flows/module.html"))
        ]
        transcript = self.root / "evidence/swimlane-browser.json"
        return {
            "schema_version": 1, "baseline_version": "req-v1", "baseline_sha256": baseline,
            "code_version": "code-v1", "build_id": "build-1", "run_id": "impl-run-1",
            "diagrams": diagrams,
            "browser": {"tool": "browser:control-in-app-browser", "run_id": "swimlane-browser-run-1",
                        "page_url": self.swimlane_url,
                        "preview_root": ".", "page_artifact_path": "flows/swimlane-system.html",
                        "page_artifact_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
                        "observed_response_sha256": hashlib.sha256((self.root / "flows/swimlane-system.html").read_bytes()).hexdigest(),
                        "transcript_path": "evidence/swimlane-browser.json",
                        "transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest()},
            "verdict": "pass",
        }

    def _implementation_trace(self) -> str:
        text = self.trace_fixture.matrix.read_text(encoding="utf-8")
        baseline = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        row = (
            f"| BLACK_BOX | required |  | req-v1 | {baseline} | code-v1 | build-1 | "
            "N/A: not started | N/A: not started | pending |"
        )
        return re.sub(r"^\| BLACK_BOX \|.*$", row, text, flags=re.MULTILINE)

    def _agent_gate(self, role: str, run_id: str, source: str, output: str) -> dict[str, object]:
        return {
            "role": role,
            "run_id": run_id,
            "provider": "independent-agent",
            "focus": f"{role} bounded review",
            "input_manifest": source,
            "input_sha256": hashlib.sha256((self.root / source).read_bytes()).hexdigest(),
            "output_evidence": output,
            "output_sha256": hashlib.sha256((self.root / output).read_bytes()).hexdigest(),
            "may_modify_code": False,
            "may_modify_shared_records": False,
            "received_full_chat": False,
            "received_other_agent_reasoning": False,
            "accepted_implementation_self_report": False,
            "verdict": "pass",
        }

    def _write_agent_outputs(self) -> None:
        roles = {
            "UI_UX": ("ui-run-1", "evidence/ui-output.md"),
            "ACCEPTANCE_CASES": ("at-run-1", "evidence/at-output.md"),
            "CHANGE_REVIEW": ("change-run-1", "evidence/change-output.md"),
            "BLACK_BOX": ("bb-run-1", "evidence/bb-output.md"),
        }
        for role, (run_id, relative) in roles.items():
            self._write_agent_output(role, run_id, relative)

    def _write_agent_inputs(self) -> None:
        roles = {
            "UI_UX": ("ui-run-1", "evidence/ui-input.md", ["requirements/baseline.md", "flows/system.html", "features/list.md", "ui/prototype.html"]),
            "ACCEPTANCE_CASES": ("at-run-1", "evidence/at-input.md", ["requirements/baseline.md", "features/list.md", "ui/prototype.html", "tests/unit.md", "tests/acceptance.md"]),
            "CHANGE_REVIEW": ("change-run-1", "evidence/change-input.md", ["requirements/baseline.md", "flows/system.html", "tests/unit.md", "src/module.py"]),
            "BLACK_BOX": ("bb-run-1", "evidence/bb-input.md", ["requirements/baseline.md", "ui/prototype.html", "tests/acceptance.md"]),
        }
        for role, (run_id, relative, paths) in roles.items():
            self._write_agent_input(role, run_id, relative, paths)

    def _write_agent_input(
        self, role: str, run_id: str, relative: str, artifact_paths: list[str],
    ) -> None:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        payload = {
            "schema_version": 1, "role": role, "run_id": run_id,
            "baseline_version": "req-v1", "baseline_sha256": baseline_sha,
            "requirement_ids": ["REQ-001"],
            "artifacts": [
                {
                    "path": item,
                    "sha256": hashlib.sha256((self.root / item).read_bytes()).hexdigest(),
                }
                for item in artifact_paths
            ],
            "includes_full_chat": False, "includes_other_agent_reasoning": False,
            "includes_implementation_self_report": False,
        }
        (self.root / relative).write_text(json.dumps(payload), encoding="utf-8")

    def _write_agent_output(self, role: str, run_id: str, relative: str) -> None:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        input_relative = relative.replace("-output", "-input")
        payload = {
            "schema_version": 1, "role": role, "run_id": run_id,
            "baseline_version": "req-v1", "baseline_sha256": baseline_sha,
            "code_version": "code-v1",
            "input_sha256": hashlib.sha256((self.root / input_relative).read_bytes()).hexdigest(),
            "verdict": "pass", "findings": [],
        }
        (self.root / relative).write_text(json.dumps(payload), encoding="utf-8")

    def _multi_agent_evidence(self) -> dict[str, object]:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        return {
            "schema_version": 1,
            "stage": "completion",
            "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha,
            "code_version": "code-v1",
            "build_id": "build-1",
            "implementation_run_id": "impl-run-1",
            "single_writer_run_id": "impl-run-1",
            "gates": [
                self._agent_gate("UI_UX", "ui-run-1", "evidence/ui-input.md", "evidence/ui-output.md"),
                self._agent_gate("ACCEPTANCE_CASES", "at-run-1", "evidence/at-input.md", "evidence/at-output.md"),
                self._agent_gate("CHANGE_REVIEW", "change-run-1", "evidence/change-input.md", "evidence/change-output.md"),
                self._agent_gate("BLACK_BOX", "bb-run-1", "evidence/bb-input.md", "evidence/bb-output.md"),
            ],
            "open_disagreements": [],
        }

    def codes(self) -> set[str]:
        return {
            issue.code
            for issue in validate_delivery_bundle(
                agents_path=self.agents,
                trace_path=self.trace_fixture.matrix,
                context_path=self.context,
                command_manifest_path=self.commands,
                multi_agent_evidence_path=self.multi_agent,
                swimlane_evidence_path=self.swimlane,
                frontend_evidence_path=self.frontend,
                project_root=self.root,
            )
            if issue.severity == "error"
        }

    def test_valid_delivery_bundle_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_missing_swimlane_evidence_blocks_delivery(self) -> None:
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=None, frontend_evidence_path=self.frontend, project_root=self.root,
        )
        self.assertIn("missing-swimlane-evidence", {item.code for item in issues})

    def test_frontend_browser_must_bind_independent_black_box_run(self) -> None:
        data = json.loads(self.frontend.read_text(encoding="utf-8"))
        data["browser"]["verifier_agent_run_id"] = "implementation-run"
        self.frontend.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("frontend-black-box-run-mismatch", self.codes())

    def test_mobile_browser_must_bind_independent_black_box_run(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: ui,user-visible,mobile"
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        mobile_png = self.root / "evidence/mobile.png"
        mobile_png.write_bytes((self.root / "evidence/frontend.png").read_bytes())
        transcript = json.loads((self.root / "evidence/browser-transcript.json").read_text(encoding="utf-8"))
        transcript.update({
            "run_id": "mobile-browser-run-1", "verifier_agent_run_id": "wrong-bb-run",
            "viewport": [390, 844],
            "screenshots": [{"path": "evidence/mobile.png", "sha256": hashlib.sha256(mobile_png.read_bytes()).hexdigest()}],
        })
        mobile_transcript = self.root / "evidence/mobile-browser-transcript.json"
        mobile_transcript.write_text(json.dumps(transcript), encoding="utf-8")
        data = json.loads(self.frontend.read_text(encoding="utf-8"))
        mobile = dict(data["browser"])
        mobile.update({
            "run_id": "mobile-browser-run-1", "verifier_agent_run_id": "wrong-bb-run",
            "viewport": [390, 844], "transcript_path": "evidence/mobile-browser-transcript.json",
            "transcript_sha256": hashlib.sha256(mobile_transcript.read_bytes()).hexdigest(),
            "screenshots": [{"path": "evidence/mobile.png", "sha256": hashlib.sha256(mobile_png.read_bytes()).hexdigest()}],
        })
        data["mobile"] = mobile
        self.frontend.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("frontend-black-box-run-mismatch", self.codes())

    def test_cross_artifact_code_version_drift_fails(self) -> None:
        self.context.write_text(self._context_manifest(code_version="code-v2"), encoding="utf-8")
        self.assertIn("bundle-code-version-mismatch", self.codes())

    def test_missing_command_manifest_returns_structured_errors(self) -> None:
        self.commands.unlink()
        issues = validate_delivery_bundle(
            agents_path=self.agents,
            trace_path=self.trace_fixture.matrix,
            context_path=self.context,
            command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend,
            project_root=self.root,
        )
        codes = {item.code for item in issues}
        self.assertIn("bundle-command-manifest-unreadable", codes)

    def test_missing_development_plan_blocks_delivery(self) -> None:
        self.plan.unlink()
        self.assertIn("bundle-development-plan-missing", self.codes())

    def test_stale_progress_record_blocks_delivery(self) -> None:
        text = self.progress.read_text(encoding="utf-8").replace(
            "Run ID: impl-run-1", "Run ID: old-run",
        ).replace("Code version: code-v1", "Code version: old-code")
        self.progress.write_text(text, encoding="utf-8")
        self.assertIn("bundle-progress-record-stale", self.codes())

    def test_incomplete_plan_and_progress_block_delivery(self) -> None:
        self.plan.write_text("# Development Plan\n\n- Baseline version: req-v1\n", encoding="utf-8")
        self.progress.write_text("# Completion Progress\n\n- Run ID: impl-run-1\n- Code version: code-v1\n", encoding="utf-8")
        self.assertTrue({
            "bundle-development-plan-incomplete", "bundle-progress-record-incomplete",
        } <= self.codes())

    def test_missing_plan_semantics_blocks_delivery(self) -> None:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        self.plan.write_text(
            f"# Development Plan\n\n- Baseline version: req-v1\n- Baseline SHA-256: {baseline_sha}\n"
            "- Scope: module only\n- Ordered steps: implement\n"
            "- Verification criteria: gates pass\n- Known risks: regression\n",
            encoding="utf-8",
        )
        self.assertIn("bundle-development-plan-incomplete", self.codes())

    def test_completion_rejects_open_remaining_work(self) -> None:
        text = self.progress.read_text(encoding="utf-8").replace(
            "Remaining work: none", "Remaining work: critical blocker unresolved",
        )
        self.progress.write_text(text, encoding="utf-8")
        self.assertIn("bundle-progress-record-open-work", self.codes())

    def test_missing_current_module_run_blocks_delivery(self) -> None:
        self.module_run.unlink()
        self.assertIn("bundle-execution-run-missing", self.codes())

    def test_missing_module_latest_blocks_completion(self) -> None:
        self.module_latest.unlink()
        self.assertIn("bundle-module-latest-missing", self.codes())

    def test_stale_module_latest_blocks_completion(self) -> None:
        text = self.module_latest.read_text(encoding="utf-8").replace(
            "Run ID: impl-run-1", "Run ID: old-run",
        )
        self.module_latest.write_text(text, encoding="utf-8")
        self.assertIn("bundle-module-latest-stale", self.codes())

    def test_module_latest_must_link_current_run_record(self) -> None:
        text = self.module_latest.read_text(encoding="utf-8").replace(
            "Record: docs/module_execution_log_directory/module/run-impl-run-1.md",
            "Record: docs/module_execution_log_directory/module/run-old.md",
        )
        self.module_latest.write_text(text, encoding="utf-8")
        self.assertIn("bundle-module-latest-stale", self.codes())

    def test_module_latest_must_bind_current_swimlane_evidence(self) -> None:
        text = self.module_latest.read_text(encoding="utf-8").replace(
            "Swimlane evidence: swimlane.json", "Swimlane evidence: missing/stale-swimlane.json",
        )
        self.module_latest.write_text(text, encoding="utf-8")
        self.assertIn("bundle-module-latest-stale", self.codes())

    def test_missing_automated_review_evidence_blocks_delivery(self) -> None:
        self.review.unlink()
        self.assertIn("bundle-automated-review-missing", self.codes())

    def test_open_automated_review_finding_blocks_delivery(self) -> None:
        text = self.review.read_text(encoding="utf-8").replace(
            "Findings: none", "Findings: P1 unresolved authorization bypass",
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-open-findings", self.codes())

    def test_unexecuted_automated_review_cannot_claim_pass(self) -> None:
        text = self.review.read_text(encoding="utf-8").replace(
            "Review exit code: 0", "Review exit code: not run",
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_command_hash_must_bind_command_manifest(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["argv_sha256"] = "0" * 64
        transcript.write_text(json.dumps(data), encoding="utf-8")
        transcript_hash = hashlib.sha256(transcript.read_bytes()).hexdigest()
        text = re.sub(
            r"Review command argv SHA-256: [0-9a-f]{64}",
            f"Review command argv SHA-256: {'0' * 64}",
            self.review.read_text(encoding="utf-8"),
        )
        text = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {transcript_hash}", text,
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_output_hash_must_bind_existing_artifact(self) -> None:
        text = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {'0' * 64}",
            self.review.read_text(encoding="utf-8"),
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_evidence_cannot_reuse_changed_source_file(self) -> None:
        review_payload = (self.root / "evidence/automated-review.json").read_bytes()
        (self.root / "src/module.py").write_bytes(review_payload)
        source_hash = hashlib.sha256((self.root / "src/module.py").read_bytes()).hexdigest()
        text = re.sub(
            r"- Review evidence path: .*\n- Review evidence SHA-256: [0-9a-f]{64}",
            f"- Review evidence path: src/module.py\n- Review evidence SHA-256: {source_hash}",
            self.review.read_text(encoding="utf-8"),
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_evidence_requires_structured_transcript(self) -> None:
        artifact = self.root / "evidence/malformed-review-output.json"
        artifact.write_text("not-json", encoding="utf-8")
        artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        text = re.sub(
            r"- Review evidence path: .*\n- Review evidence SHA-256: [0-9a-f]{64}",
            f"- Review evidence path: evidence/malformed-review-output.json\n- Review evidence SHA-256: {artifact_hash}",
            self.review.read_text(encoding="utf-8"),
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_rejects_unknown_failure_fields(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data.update({"verdict": "failed", "errors": ["P1 unresolved"]})
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_rejects_boolean_integer_aliases(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["schema_version"] = True
        data["exit_code"] = False
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_rejects_boolean_rerun_results(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["reruns"] = {key: False for key in data["reruns"]}
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_rejects_duplicate_json_keys(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        text = transcript.read_text(encoding="utf-8").replace(
            '"exit_code": 0,', '"exit_code": 1, "exit_code": 0,',
        ).replace(
            '"findings": [],', '"findings": [{"id": "P1", "status": "open"}], "findings": [],',
        )
        transcript.write_text(text, encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_binds_changed_files(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["changed_files"] = ["src/module.py", "src/unreviewed.py"]
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_binds_code_fingerprint(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["code_fingerprint"] = "0" * 64
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_transcript_binds_command_manifest_fingerprint(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["command_manifest_fingerprint"] = "0" * 64
        transcript.write_text(json.dumps(data), encoding="utf-8")
        self._bind_review_transcript_hash(transcript)
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_scope_must_cover_changed_files_and_dependency_surfaces(self) -> None:
        text = self.review.read_text(encoding="utf-8").replace(
            "Scope: src/module.py; callers; callees; interfaces; configuration; tests; traceability; swimlanes",
            "Scope: N/A: skipped all affected dependencies, tests, trace, and swimlanes",
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

    def test_review_scope_cannot_hide_nonexecution_after_valid_categories(self) -> None:
        for phrase in ("not run", "not executed", "unexecuted", "execution omitted", "no execution"):
            with self.subTest(phrase=phrase):
                original = self.review.read_text(encoding="utf-8")
                text = original.replace(
                    "Scope: src/module.py; callers; callees; interfaces; configuration; tests; traceability; swimlanes",
                    "Scope: src/module.py; callers; callees; interfaces; configuration; tests; traceability; swimlanes; " + phrase,
                )
                self.review.write_text(text, encoding="utf-8")
                self.assertIn("bundle-automated-review-unexecuted", self.codes())
                self.review.write_text(original, encoding="utf-8")

    def _bind_review_transcript_hash(self, transcript: Path) -> None:
        digest = hashlib.sha256(transcript.read_bytes()).hexdigest()
        text = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {digest}", self.review.read_text(encoding="utf-8"),
        )
        self.review.write_text(text, encoding="utf-8")

    def test_module_records_must_bind_current_verification_paths(self) -> None:
        self.module_run.write_text(
            self.module_run.read_text(encoding="utf-8")
            .replace("Verification evidence: swimlane.json, frontend.json", "Verification evidence: N/A")
            .replace(
                "Swimlane diagrams and validated evidence: flows/swimlane-system.html, flows/module.html, swimlane.json",
                "Swimlane diagrams and validated evidence: N/A",
            ),
            encoding="utf-8",
        )
        self.module_latest.write_text(
            self.module_latest.read_text(encoding="utf-8").replace(
                "Verification evidence: swimlane.json, frontend.json", "Verification evidence: N/A",
            ),
            encoding="utf-8",
        )
        self.assertTrue({
            "bundle-execution-run-evidence-stale", "bundle-module-latest-evidence-stale",
        } <= self.codes())

    def test_module_records_reject_extra_fake_evidence_paths(self) -> None:
        self.module_run.write_text(
            self.module_run.read_text(encoding="utf-8")
            .replace(
                "Verification evidence: swimlane.json, frontend.json",
                "Verification evidence: swimlane.json, frontend.json, missing/fake.json",
            )
            .replace(
                "Swimlane diagrams and validated evidence: flows/swimlane-system.html, flows/module.html, swimlane.json",
                "Swimlane diagrams and validated evidence: flows/swimlane-system.html, flows/module.html, swimlane.json, missing/fake.html",
            ),
            encoding="utf-8",
        )
        self.module_latest.write_text(
            self.module_latest.read_text(encoding="utf-8").replace(
                "Verification evidence: swimlane.json, frontend.json",
                "Verification evidence: swimlane.json, frontend.json, missing/fake.json",
            ),
            encoding="utf-8",
        )
        self.assertTrue({
            "bundle-execution-run-evidence-stale", "bundle-module-latest-evidence-stale",
        } <= self.codes())

    def test_declared_records_reject_real_nul_bytes(self) -> None:
        cases = (
            (self.plan, "bundle-development-plan-nul-byte"),
            (self.progress, "bundle-progress-record-nul-byte"),
            (self.review, "bundle-automated-review-nul-byte"),
            (self.module_run, "bundle-execution-run-nul-byte"),
            (self.module_latest, "bundle-module-latest-nul-byte"),
        )
        for path, expected in cases:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"\x00")
                self.assertIn(expected, self.codes())
                path.write_bytes(original)

    def test_declared_records_reject_casefold_duplicates_and_hidden_content(self) -> None:
        self.review.write_text(
            self.review.read_text(encoding="utf-8") + "\n- findings: P1 unresolved bypass\n",
            encoding="utf-8",
        )
        self.assertIn("bundle-automated-review-duplicate-field", self.codes())
        self.review.write_text(
            self.review.read_text(encoding="utf-8").replace(
                "- findings: P1 unresolved bypass", "P1 unresolved bypass remains open",
            ),
            encoding="utf-8",
        )
        self.assertIn("bundle-automated-review-unexpected-content", self.codes())

    def test_declared_records_reject_unknown_open_fields(self) -> None:
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8") + "\n- Open work: release blocker\n",
            encoding="utf-8",
        )
        self.assertIn("bundle-progress-record-unexpected-content", self.codes())

    def test_declared_records_reject_hidden_open_headings(self) -> None:
        cases = (
            (self.review, "bundle-automated-review-unexpected-content"),
            (self.progress, "bundle-progress-record-unexpected-content"),
            (self.module_run, "bundle-execution-run-unexpected-content"),
            (self.module_latest, "bundle-module-latest-unexpected-content"),
        )
        for path, expected in cases:
            with self.subTest(path=path.name):
                original = path.read_text(encoding="utf-8")
                path.write_text(original + "\n## P1 unresolved release blocker\n", encoding="utf-8")
                self.assertIn(expected, self.codes())
                path.write_text(original, encoding="utf-8")

    def test_module_run_binds_baseline(self) -> None:
        text = self.module_run.read_text(encoding="utf-8")
        text = re.sub(r"Baseline version and SHA-256: .*", "Baseline version and SHA-256: stale-v0 / " + "0" * 64, text)
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-stale", self.codes())

    def test_module_run_binds_build_and_environment(self) -> None:
        text = self.module_run.read_text(encoding="utf-8")
        text = re.sub(r"Build ID and acceptance environment: .*", "Build ID and acceptance environment: stale-build / stale-env", text)
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-stale", self.codes())

    def test_module_run_binds_context_manifest_and_cache(self) -> None:
        text = self.module_run.read_text(encoding="utf-8")
        text = re.sub(r"Context workset manifest and reused evidence fingerprints: .*", "Context workset manifest and reused evidence fingerprints: missing/context.md / stale", text)
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-stale", self.codes())

    def test_module_run_binds_risk_level_and_reason(self) -> None:
        text = self.module_run.read_text(encoding="utf-8").replace(
            "Risk level and reason: standard; user-visible interaction; no expansion",
            "Risk level and reason: small; harmless docs only; no expansion",
        )
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-stale", self.codes())

    def test_context_risk_must_bind_trace_risk(self) -> None:
        text = self.context.read_text(encoding="utf-8").replace(
            "Risk / expansion reason: standard; user-visible interaction; no expansion",
            "Risk / expansion reason: small; harmless docs only; no expansion",
        )
        self.context.write_text(text, encoding="utf-8")
        self.assertIn("bundle-risk-context-mismatch", self.codes())

    def test_module_record_headings_bind_run_and_module(self) -> None:
        cases = (
            (self.module_run, "# Run impl-run-1", "# Run stale-run", "bundle-execution-run-unexpected-content"),
            (self.module_latest, "# Latest module", "# Latest wrong-module", "bundle-module-latest-unexpected-content"),
        )
        for path, current, stale, expected in cases:
            with self.subTest(path=path.name):
                original = path.read_text(encoding="utf-8")
                path.write_text(original.replace(current, stale), encoding="utf-8")
                self.assertIn(expected, self.codes())
                path.write_text(original, encoding="utf-8")

    def test_closed_semantics_are_field_specific(self) -> None:
        self.review.write_text(
            self.review.read_text(encoding="utf-8").replace("Findings: none", "Findings: no remaining work"),
            encoding="utf-8",
        )
        self.assertIn("bundle-automated-review-open-findings", self.codes())

    def test_record_parent_symlink_is_rejected(self) -> None:
        original = self.root / "docs/module_execution_log_directory"
        redirected = self.root / "docs/redirected_records"
        original.rename(redirected)
        original.symlink_to(redirected, target_is_directory=True)
        self.assertIn("bundle-execution-run-missing", self.codes())

    def test_module_run_and_latest_cannot_share_hardlink(self) -> None:
        self.module_run.write_text(
            self.module_run.read_text(encoding="utf-8")
            + "\n- Record: docs/module_execution_log_directory/module/run-impl-run-1.md\n",
            encoding="utf-8",
        )
        self.module_latest.unlink()
        os.link(self.module_run, self.module_latest)
        self.assertIn("bundle-declared-record-alias", self.codes())

    def test_module_run_must_bind_declared_evidence_paths(self) -> None:
        text = self.module_run.read_text(encoding="utf-8").replace(
            "Automated review evidence: docs/automated_review_evidence_path.md",
            "Automated review evidence: docs/unrelated-review.md",
        )
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-stale", self.codes())

    def test_completion_rejects_open_module_risks(self) -> None:
        text = self.module_run.read_text(encoding="utf-8").replace(
            "Remaining risks: none", "Remaining risks: critical race unresolved",
        )
        self.module_run.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-open-work", self.codes())

    def test_progress_index_must_link_current_module_run(self) -> None:
        text = self.progress.read_text(encoding="utf-8").replace(
            "- Module run records: module=docs/module_execution_log_directory/module/run-impl-run-1.md\n",
            "",
        )
        self.progress.write_text(text, encoding="utf-8")
        self.assertIn("bundle-progress-index-stale", self.codes())

    def test_context_requirement_ids_must_match_trace(self) -> None:
        text = self.context.read_text(encoding="utf-8").replace(
            "Requirement IDs: REQ-001", "Requirement IDs: REQ-999",
        )
        self.context.write_text(text, encoding="utf-8")
        self.assertIn("bundle-requirement-ids-mismatch", self.codes())

    def test_context_requirement_ids_may_select_current_trace_subset(self) -> None:
        trace_text = self.trace_fixture.matrix.read_text(encoding="utf-8")
        row = (
            "| [REQ-002](requirements/baseline.md) | [FLOW-002](flows/system.html) | "
            "[FEAT-002](features/list.md) | [UI-002](ui/prototype.html) | [UT-002](tests/unit.md) | "
            "[AT-002](tests/acceptance.md) | [MOD-002](src/module.py) | "
            "[BB-002](evidence/black-box.md) | completed |\n"
        )
        trace_text = trace_text.replace("\n## Independent Gate Evidence", "\n" + row + "\n## Independent Gate Evidence")
        context = {"Requirement IDs": "REQ-001", "Risk / expansion reason": "standard; user-visible interaction; no expansion"}
        trace = {"Risk level": "standard", "Risk reason": "user-visible interaction"}
        codes = {item.code for item in _metadata_binding_issues(trace, context, trace_text, self.root)}
        self.assertNotIn("bundle-requirement-ids-mismatch", codes)

    def test_requirement_cell_may_bind_multiple_current_requirement_ids(self) -> None:
        trace_text = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "[REQ-001](requirements/baseline.md)",
            "[REQ-001](requirements/baseline.md), [REQ-002](requirements/baseline.md)",
            1,
        )
        context = {
            "Requirement IDs": "REQ-001, REQ-002",
            "Changed files": "src/module.py",
            "Risk / expansion reason": "standard; user-visible interaction; no expansion",
        }
        trace = {"Risk level": "standard", "Risk reason": "user-visible interaction"}
        codes = {item.code for item in _metadata_binding_issues(trace, context, trace_text, self.root)}
        self.assertNotIn("bundle-requirement-ids-mismatch", codes)

    def test_module_run_changed_files_use_module_ownership_map(self) -> None:
        context = {"Changed files": "src/a.py, src/b.py", "Module changed files": "a=src/a.py; b=src/b.py"}
        self.assertEqual("src/a.py", _module_changed_files(context, "a"))
        self.assertEqual("src/b.py", _module_changed_files(context, "b"))

    def test_run_id_cannot_escape_module_log_directory(self) -> None:
        text = self.context.read_text(encoding="utf-8").replace(
            "Run ID: impl-run-1", "Run ID: x/../../../escaped-run",
        )
        self.context.write_text(text, encoding="utf-8")
        self.assertIn("bundle-execution-run-unsafe-id", self.codes())

    def test_module_id_cannot_escape_module_log_directory(self) -> None:
        text = self.context.read_text(encoding="utf-8").replace("Modules: module", "Modules: ..")
        self.context.write_text(text, encoding="utf-8")
        self.assertTrue({"context-invalid-modules", "bundle-execution-run-unsafe-module"} <= self.codes())

    def test_ui_trace_cannot_disable_frontend_applicability(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        data["frontend_applicable"] = False
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("frontend-applicability-mismatch", self.codes())

    def test_nonfrontend_user_visible_change_does_not_require_browser_evidence(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        data["frontend_applicable"] = False
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        trace_text = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: user-visible",
        )
        self.trace_fixture.matrix.write_text(trace_text, encoding="utf-8")
        issues = []
        self.assertFalse(_frontend_applicable(self.commands, self.trace_fixture.matrix, "implementation", issues))
        self.assertNotIn("frontend-applicability-mismatch", {item.code for item in issues})

    def test_frontend_internal_change_uses_command_applicability(self) -> None:
        trace_text = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: internal",
        )
        self.trace_fixture.matrix.write_text(trace_text, encoding="utf-8")
        issues = []
        self.assertTrue(_frontend_applicable(self.commands, self.trace_fixture.matrix, "implementation", issues))
        self.assertNotIn("frontend-applicability-mismatch", {item.code for item in issues})

    def test_execution_run_template_uses_module_owned_requirement_ids(self) -> None:
        template = (Path(__file__).resolve().parent.parent / "assets/execution-run.template.md").read_text(encoding="utf-8")
        self.assertIn("{{MODULE_OWNED_REQUIREMENT_IDS}}", template)
        self.assertNotIn("{{REQ_FLOW_FEAT_UI_UT_AT_MOD_BB_IDS}}", template)

    def test_agents_content_drift_breaks_bundle_binding(self) -> None:
        self.agents.write_text(self.agents.read_text(encoding="utf-8") + "\n## Project Identity\n\n- Repository: unrelated-project\n", encoding="utf-8")
        self.assertTrue({"context-stale-effective-agents-fingerprint", "bundle-agents-mismatch"} <= self.codes())

    def test_implementation_stage_does_not_require_black_box_but_requires_frontend(self) -> None:
        trace = self._implementation_trace()
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["gates"] = [gate for gate in evidence["gates"] if gate["role"] != "BLACK_BOX"]
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        progress = self.progress.read_text(encoding="utf-8").replace("Status: completed", "Status: in_progress")
        self.progress.write_text(progress, encoding="utf-8")
        implementation_run = self._module_run_record(status="in_progress")
        self.module_run.write_text(implementation_run, encoding="utf-8")
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend,
            project_root=self.root, stage="implementation",
        )
        self.assertEqual(set(), {issue.code for issue in issues if issue.severity == "error"})

    def test_implementation_stage_rejects_started_black_box_without_multi_agent_gate(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "| pass |\n\n## Open Findings", "| pending |\n\n## Open Findings",
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["gates"] = [gate for gate in evidence["gates"] if gate["role"] != "BLACK_BOX"]
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8").replace("Status: completed", "Status: in_progress"),
            encoding="utf-8",
        )
        self.module_run.write_text(self._module_run_record(status="in_progress"), encoding="utf-8")
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane, frontend_evidence_path=self.frontend,
            project_root=self.root, stage="implementation",
        )
        self.assertIn("trace-implementation-black-box-started", {item.code for item in issues})

    def test_risk_reason_binding_is_exact_not_prefix_based(self) -> None:
        trace = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Risk reason: user-visible interaction", "Risk reason: user",
        )
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        self.assertIn("bundle-risk-context-mismatch", self.codes())

    def test_risk_binding_allows_explicit_nonempty_expansion_reason(self) -> None:
        context = {"Requirement IDs": "REQ-001", "Risk / expansion reason": "standard; user-visible interaction; no expansion"}
        trace = {"Risk level": "standard", "Risk reason": "user-visible interaction"}
        issues = _metadata_binding_issues(trace, context, "", self.root)
        self.assertNotIn("bundle-risk-context-mismatch", {item.code for item in issues})

    def test_risk_binding_requires_exactly_three_segments(self) -> None:
        trace = {"Risk level": "standard", "Risk reason": "user-visible interaction"}
        for value in (
            "standard; user-visible interaction",
            "standard; user-visible interaction; no expansion; injected fourth",
        ):
            with self.subTest(value=value):
                context = {"Requirement IDs": "REQ-001", "Risk / expansion reason": value}
                codes = {item.code for item in _metadata_binding_issues(trace, context, "", self.root)}
                self.assertIn("bundle-risk-context-mismatch", codes)

    def test_implementation_stage_missing_frontend_evidence_is_blocked(self) -> None:
        trace = self._implementation_trace()
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["gates"] = [gate for gate in evidence["gates"] if gate["role"] != "BLACK_BOX"]
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8").replace("Status: completed", "Status: in_progress"),
            encoding="utf-8",
        )
        self.module_run.write_text(self._module_run_record(status="in_progress"), encoding="utf-8")
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane, project_root=self.root, stage="implementation",
        )
        self.assertIn("missing-frontend-evidence", {issue.code for issue in issues})

    def test_implementation_stage_rejects_completed_progress(self) -> None:
        trace = self._implementation_trace()
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["gates"] = [gate for gate in evidence["gates"] if gate["role"] != "BLACK_BOX"]
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane, project_root=self.root, stage="implementation",
        )
        self.assertIn("bundle-progress-record-stage-mismatch", {item.code for item in issues})

    def test_implementation_stage_rejects_completed_module_run(self) -> None:
        trace = self._implementation_trace()
        self.trace_fixture.matrix.write_text(trace, encoding="utf-8")
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["gates"] = [gate for gate in evidence["gates"] if gate["role"] != "BLACK_BOX"]
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8").replace("Status: completed", "Status: in_progress"),
            encoding="utf-8",
        )
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane, project_root=self.root, stage="implementation",
        )
        self.assertIn("bundle-execution-run-stage-mismatch", {item.code for item in issues})


if __name__ == "__main__":
    unittest.main()
