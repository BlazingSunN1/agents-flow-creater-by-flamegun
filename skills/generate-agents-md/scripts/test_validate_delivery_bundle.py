from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_validate_agents_md import project_root_fixture
import test_validate_traceability as trace_test_support
from validate_context_manifest import (
    _cache_key, _parse_metadata as parse_context_metadata, _paths_fingerprint,
    _split_paths,
)
from delivery_record_validation import _module_changed_files
from delivery_gate_planner import (
    build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)
from validate_delivery_bundle import (
    _frontend_applicable, _metadata_binding_issues,
    _test_only_validate_delivery_bundle, validate_delivery_bundle,
)
from validate_project_commands import REQUIRED_COMMANDS
from validate_delivery_contract import validate_delivery_contract
from validate_traceability import _parse_metadata as parse_trace_metadata
from test_http_server import ProjectHttpServer
from test_execution_run_support import reusable_execution_run
from test_image_support import png_bytes
from authority_binding_validation import AUTHORITY_MATRIX_LOCATOR
from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256


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
        self.requirement_questions = self.root / "requirement-questions.json"
        self._write_requirement_questions(self._requirement_questions_payload(baseline_sha))
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
            "review_trigger": "module_closure_candidate", "human_trigger_reference": "N/A",
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
- Review trigger: module_closure_candidate
- Human trigger reference: N/A
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
        self._write_implementation_receipt()
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
        self.contract = self.root / "docs/delivery-contract.json"
        self._write_delivery_contract()

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
            "Authority matrix locator": AUTHORITY_MATRIX_LOCATOR,
            "Authority matrix SHA-256": AUTHORITY_MATRIX_SHA256,
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
            f"# Context Workset prior-run\n\n"
            "- Run ID: prior-run\n"
            f"- Authority matrix locator: {AUTHORITY_MATRIX_LOCATOR}\n"
            f"- Authority matrix SHA-256: {AUTHORITY_MATRIX_SHA256}\n"
            f"- Evidence cache key: {cache_key}\n",
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
- Authority matrix locator: {AUTHORITY_MATRIX_LOCATOR}
- Authority matrix SHA-256: {AUTHORITY_MATRIX_SHA256}
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
        slug = role.casefold().replace("_", "-")
        receipt = f"evidence/{slug}-spawn-receipt.json"
        output_receipt = f"evidence/{slug}-output-result.json"
        payload = {
            "schema_version": 1, "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent", "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol", "agent_id": f"{slug}-agent-1",
            "requested_reasoning_effort": "xhigh", "recorded_reasoning_effort": "xhigh",
            "run_id": run_id, "role": f"{slug}-gate", "module": "module",
            "maintainer_title": f"{role} Gate Reviewer",
        }
        (self.root / receipt).write_text(json.dumps(payload), encoding="utf-8")
        input_sha256 = hashlib.sha256((self.root / source).read_bytes()).hexdigest()
        output_sha256 = hashlib.sha256((self.root / output).read_bytes()).hexdigest()
        output_result = {
            **payload,
            "receipt_kind": "codex-native-output-result",
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "baseline_version": "req-v1",
            "code_version": "code-v1",
            "build_id": "build-1",
            "candidate_sha256": hashlib.sha256(b"module-candidate").hexdigest(),
            "verdict": "pass",
        }
        (self.root / output_receipt).write_text(json.dumps(output_result), encoding="utf-8")
        return {
            "role": role,
            "run_id": run_id,
            "provider": "codex-native-agent",
            "agent_model": "gpt-5.6-sol",
            "agent_reasoning_effort": "xhigh",
            "agent_id": f"{slug}-agent-1",
            "spawn_receipt": receipt,
            "spawn_receipt_sha256": hashlib.sha256((self.root / receipt).read_bytes()).hexdigest(),
            "output_receipt": output_receipt,
            "output_receipt_sha256": hashlib.sha256(
                (self.root / output_receipt).read_bytes()
            ).hexdigest(),
            "focus": f"{role} bounded review",
            "input_manifest": source,
            "input_sha256": input_sha256,
            "output_evidence": output,
            "output_sha256": output_sha256,
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
            "requirement_questions_locator": self.requirement_questions.relative_to(
                self.root
            ).as_posix(),
            "requirement_questions_sha256": hashlib.sha256(
                self.requirement_questions.read_bytes()
            ).hexdigest(),
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

    def _write_implementation_receipt(self) -> None:
        payload = {
            "schema_version": 1,
            "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-5.6-sol",
            "recorded_model": "gpt-5.6-sol",
            "requested_reasoning_effort": "high",
            "recorded_reasoning_effort": "high",
            "agent_id": "module-maintainer-agent-1",
            "run_id": "impl-run-1",
            "role": "module-maintainer",
            "module": "module",
            "maintainer_title": "ModuleMaintainer",
        }
        (self.root / "evidence/implementation-spawn-receipt.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )

    def _multi_agent_evidence(self) -> dict[str, object]:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        return {
            "schema_version": 1,
            "stage": "completion",
            "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha,
            "code_version": "code-v1",
            "build_id": "build-1",
            "candidate_sha256": hashlib.sha256(b"module-candidate").hexdigest(),
            "implementation_agent_title": "ModuleMaintainer",
            "implementation_agent_provider": "codex-native-agent",
            "implementation_agent_model": "gpt-5.6-sol",
            "implementation_agent_reasoning_effort": "high",
            "implementation_agent_id": "module-maintainer-agent-1",
            "implementation_run_id": "impl-run-1",
            "implementation_spawn_receipt": "evidence/implementation-spawn-receipt.json",
            "implementation_spawn_receipt_sha256": hashlib.sha256(
                (self.root / "evidence/implementation-spawn-receipt.json").read_bytes()
            ).hexdigest(),
            "single_writer_run_id": "impl-run-1",
            "gates": [
                self._agent_gate("BLACK_BOX", "bb-run-1", "evidence/bb-input.md", "evidence/bb-output.md"),
            ],
            "open_disagreements": [],
        }

    def codes(self, verifier=lambda *_: True, *, stage: str = "completion") -> set[str]:
        return {
            issue.code
            for issue in _test_only_validate_delivery_bundle(
                delivery_contract_path=self.contract,
                agents_path=self.agents,
                trace_path=self.trace_fixture.matrix,
                context_path=self.context,
                command_manifest_path=self.commands,
                multi_agent_evidence_path=self.multi_agent,
                swimlane_evidence_path=self.swimlane,
                frontend_evidence_path=self.frontend,
                requirement_questions_path=self.requirement_questions,
                requirement_questions_sha256=self.requirement_questions_sha256,
                requirement_baseline_version="req-v1",
                requirement_baseline_sha256=hashlib.sha256(
                    (self.root / "requirements/baseline.md").read_bytes()
                ).hexdigest(),
                project_root=self.root,
                stage=stage,
                _test_only_host_attestation_verifier=verifier,
            )
            if issue.severity == "error"
        }

    def _requirement_questions_payload(self, baseline_sha: str) -> dict[str, object]:
        return {
            "schema_version": 1, "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha,
            "questions": [{
                "question_id": "Q-001", "impact_scope": ["REQ-001"],
                "risk": "standard", "proposed_default": "Keep current behavior.",
                "safe_fallback": "Disable the additive change.",
                "answer_status": "NOT_PROVIDED", "delivery_disposition": "NON_BLOCKING_P2",
                "assumption": "Compatibility is required.",
                "owner": "product-owner", "review_due": "2026-09-03T10:00:00+08:00",
            }],
            "gate_reruns": [],
        }

    def _write_requirement_questions(self, payload: dict[str, object]) -> None:
        self.requirement_questions.write_text(json.dumps(payload), encoding="utf-8")
        self.requirement_questions_sha256 = hashlib.sha256(self.requirement_questions.read_bytes()).hexdigest()
        if hasattr(self, "multi_agent") and self.multi_agent.exists():
            self._write_agent_inputs()
            self._write_agent_outputs()
            self.multi_agent.write_text(
                json.dumps(self._multi_agent_evidence()), encoding="utf-8",
            )
        if hasattr(self, "contract"):
            self._write_delivery_contract()

    def _contract_ref(self, path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _write_delivery_contract(self, *, stage: str = "completion") -> None:
        trace = parse_trace_metadata(self.trace_fixture.matrix.read_text(encoding="utf-8"))
        context, _ = parse_context_metadata(self.context.read_text(encoding="utf-8"))
        commands = json.loads(self.commands.read_text(encoding="utf-8"))
        surfaces = [
            item.strip().casefold()
            for item in trace.get("Change surfaces", "").split(",")
            if item.strip()
        ]
        modules = [item.strip() for item in context.get("Modules", "").split(",") if item.strip()]
        delivery_phase = {
            "completion": "completed",
            "closure_candidate": "closure_candidate",
        }.get(stage, "result_candidate")
        data: dict[str, object] = {
            "schema_version": 1,
            "contract_id": "impl-run-1",
            "stage": stage,
            "status": {
                "completion": "completed",
                "closure_candidate": "closure_candidate",
            }.get(stage, "in_progress"),
            "baseline": {
                "version": "req-v1",
                **self._contract_ref(self.root / "requirements/baseline.md"),
            },
            "artifacts": {
                "traceability": self._contract_ref(self.trace_fixture.matrix),
                "questions": self._contract_ref(self.requirement_questions),
                "development_plan": self._contract_ref(self.plan),
                "progress": self._contract_ref(self.progress),
                "command_manifest": self._contract_ref(self.commands),
            },
            "identity": {
                "code_version": trace.get("Code version"),
                "build_id": trace.get("Build ID"),
                "environment_id": trace.get("Acceptance environment"),
            },
            "change": {
                "delivery_phase": delivery_phase,
                "baseline_frozen": stage in {"closure_candidate", "completion"},
                "requirement_ids": [item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()],
                "modules": modules,
                "changed_files": _split_paths(context.get("Changed files", "")),
                "configuration_files": _split_paths(context.get("Configuration files", "")),
                "input_files": _split_paths(context.get("Input files", "")),
                "direct_dependency_boundaries": context.get("Direct dependency boundaries"),
                "risk_level": trace.get("Risk level"),
                "risk_reason": trace.get("Risk reason"),
                "surfaces": surfaces,
                "flow_impact": "changed",
                "frontend_applicable": isinstance(commands, dict) and commands.get("frontend_applicable") is True,
                "swimlane_applicable": True,
                "cross_module": len(modules) > 1 or "cross-module" in surfaces,
                "human_review_triggered": False,
            },
            "repair_policy": {
                "max_rounds": 3,
                "same_failure_limit": 2,
                "regression_test_before_fix": True,
                "on_exhaustion": "block_completion_and_record_open_defect",
            },
            "gate_plan": {},
            "gate_receipts": {},
        }
        self._bind_contract_gate_plan(data, stage)
        self.contract.write_text(json.dumps(data), encoding="utf-8")

    def _bind_contract_gate_plan(self, data: dict[str, object], stage: str) -> None:
        impact = compute_impact_fingerprint(data, self.root)
        data["gate_plan"] = build_gate_plan(
            data["change"], stage=stage, impact_fingerprint=impact,
            command_fingerprints=compute_command_fingerprints(data, self.root),
        )
        receipts = {}
        for command_id, fingerprint in data["gate_plan"]["gate_input_fingerprints"].items():
            output = self.root / f"evidence/contract-gate-{command_id}.txt"
            output.write_text(f"passed {command_id}", encoding="utf-8")
            receipt = self.root / f"evidence/contract-gate-{command_id}.json"
            receipt.write_text(json.dumps({
                "schema_version": 1,
                "command_id": command_id,
                "gate_input_fingerprint": fingerprint,
                "verdict": "pass",
                "run_id": f"run-{command_id}",
                "output_path": output.relative_to(self.root).as_posix(),
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            receipts[command_id] = self._contract_ref(receipt)
        data["gate_receipts"] = receipts

    def _rewrite_contract_change(self, field: str, value: object) -> None:
        data = json.loads(self.contract.read_text(encoding="utf-8"))
        data["change"][field] = value
        self._bind_contract_gate_plan(data, str(data["stage"]))
        self.contract.write_text(json.dumps(data), encoding="utf-8")

    def _apply_swimlane_gate_plan_to_records(self) -> None:
        contract = json.loads(self.contract.read_text(encoding="utf-8"))
        planned = set(contract["gate_plan"]["required_command_ids"])
        swimlane_reruns = sorted(planned & {"swimlane_evidence", "swimlane_freshness"})
        review_output = self.root / "evidence/automated-review.json"
        payload = json.loads(review_output.read_text(encoding="utf-8"))
        payload["reruns"].pop("swimlane_evidence")
        payload["reruns"].update({command_id: 0 for command_id in swimlane_reruns})
        review_output.write_text(json.dumps(payload), encoding="utf-8")
        output_sha = hashlib.sha256(review_output.read_bytes()).hexdigest()
        review = self.review.read_text(encoding="utf-8")
        if not swimlane_reruns:
            review = review.replace("; swimlanes\n", "\n")
        rerun_ids = sorted({"automated_review", "code_standards", "targeted_tests", "traceability", *swimlane_reruns})
        review = re.sub(
            r"(?m)^- Rerun command IDs: .+$",
            f"- Rerun command IDs: {', '.join(rerun_ids)}",
            review,
        )
        review = re.sub(
            r"(?m)^- Rerun exit codes: .+$",
            f"- Rerun exit codes: {', '.join(f'{command_id}=0' for command_id in rerun_ids)}",
            review,
        )
        review = re.sub(
            r"(?m)^- Review evidence SHA-256: .+$",
            f"- Review evidence SHA-256: {output_sha}",
            review,
        )
        self.review.write_text(review, encoding="utf-8")
        module_run = self.module_run.read_text(encoding="utf-8")
        module_run = module_run.replace(
            "- Verification evidence: swimlane.json, frontend.json\n",
            "- Verification evidence: frontend.json\n",
        )
        module_run = re.sub(
            r"(?m)^- Swimlane (?:evidence|diagrams and validated evidence): .+\n",
            "",
            module_run,
        )
        self.module_run.write_text(module_run, encoding="utf-8")
        latest = self.module_latest.read_text(encoding="utf-8")
        latest = latest.replace(
            "- Verification evidence: swimlane.json, frontend.json\n",
            "- Verification evidence: frontend.json\n",
        )
        latest = re.sub(r"(?m)^- Swimlane evidence: .+\n", "", latest)
        self.module_latest.write_text(latest, encoding="utf-8")

    def _assert_valid_contract_change_drift_is_rejected(self, field: str, value: object) -> None:
        self._rewrite_contract_change(field, value)
        standalone = {
            item.code for item in validate_delivery_contract(self.contract, project_root=self.root)
            if item.severity == "error"
        }
        self.assertEqual(set(), standalone)
        self.assertIn("contract-change-identity-mismatch", self.codes())

    def _rebind_gate_inputs_to_questions(self, questions: Path) -> None:
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        locator = questions.relative_to(self.root).as_posix()
        questions_sha = hashlib.sha256(questions.read_bytes()).hexdigest()
        for gate in evidence["gates"]:
            input_path = self.root / gate["input_manifest"]
            gate_input = json.loads(input_path.read_text(encoding="utf-8"))
            gate_input["requirement_questions_locator"] = locator
            gate_input["requirement_questions_sha256"] = questions_sha
            input_path.write_text(json.dumps(gate_input), encoding="utf-8")
            gate["input_sha256"] = hashlib.sha256(input_path.read_bytes()).hexdigest()

            output_path = self.root / gate["output_evidence"]
            gate_output = json.loads(output_path.read_text(encoding="utf-8"))
            gate_output["input_sha256"] = gate["input_sha256"]
            output_path.write_text(json.dumps(gate_output), encoding="utf-8")
            gate["output_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()

            receipt_path = self.root / gate["output_receipt"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["input_sha256"] = gate["input_sha256"]
            receipt["output_sha256"] = gate["output_sha256"]
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            gate["output_receipt_sha256"] = hashlib.sha256(
                receipt_path.read_bytes()
            ).hexdigest()
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")

    def _answered_requirement_questions(self) -> dict[str, object]:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        payload = self._requirement_questions_payload(baseline_sha)
        question = payload["questions"][0]
        question.update({
            "answer_status": "ANSWERED", "human_answer": "Keep current behavior.",
            "pre_answer_baseline_version": "req-v0", "pre_answer_baseline_sha256": "c" * 64,
        })
        answer = {
            "schema_version": 1, "evidence_kind": "human-requirement-answer",
            "question_id": "Q-001", "human_answer": "Keep current behavior.",
            "pre_answer_baseline_version": "req-v0", "pre_answer_baseline_sha256": "c" * 64,
            "post_answer_baseline_version": "req-v1", "post_answer_baseline_sha256": baseline_sha,
        }
        answer_path = self.root / "evidence/requirement-answer.json"
        answer_path.write_text(json.dumps(answer, sort_keys=True), encoding="utf-8")
        question["answer_evidence_locator"] = "evidence/requirement-answer.json"
        question["answer_evidence_sha256"] = hashlib.sha256(answer_path.read_bytes()).hexdigest()
        receipt = {
            "schema_version": 1, "receipt_kind": "requirement-gate-rerun",
            "question_id": "Q-001", "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha, "affected_scope": ["REQ-001"],
            "status": "COMPLETED",
        }
        receipt_path = self.root / "evidence/requirement-rerun.json"
        receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        payload["gate_reruns"] = [{
            "question_id": "Q-001", "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha, "affected_scope": ["REQ-001"],
            "status": "COMPLETED", "receipt_locator": "evidence/requirement-rerun.json",
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        }]
        return payload

    def test_requirement_questions_are_required_and_hash_bound(self) -> None:
        self.requirement_questions.unlink()
        self.assertIn("questions-artifact-invalid", self.codes())

    def test_requirement_questions_hash_drift_fails(self) -> None:
        expected = hashlib.sha256(self.requirement_questions.read_bytes()).hexdigest()
        self.requirement_questions.write_text("{}", encoding="utf-8")
        issues = _test_only_validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent, swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend, requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=expected, requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest(),
            project_root=self.root, _test_only_host_attestation_verifier=lambda *_: True,
        )
        self.assertIn("questions-artifact-invalid", {item.code for item in issues})

    def test_requirement_questions_never_block_delivery(self) -> None:
        payload = json.loads(self.requirement_questions.read_text(encoding="utf-8"))
        payload["questions"][0]["risk"] = "security"
        self._write_requirement_questions(payload)
        self.assertNotIn("questions-unanswered-question-blocked", self.codes())

    def test_requirement_questions_baseline_must_match_delivery_and_trace(self) -> None:
        payload = json.loads(self.requirement_questions.read_text(encoding="utf-8"))
        payload["baseline_version"] = "req-old"
        self._write_requirement_questions(payload)
        self.assertIn("questions-baseline-mismatch", self.codes())

    def test_answered_questions_require_bound_evidence_and_validated_receipt(self) -> None:
        payload = self._answered_requirement_questions()
        self._write_requirement_questions(payload)
        self.assertEqual(set(), self.codes())
        self.assertIn(
            "questions-question-rerun-receipt-not-validated",
            self.codes(verifier=lambda *_: False),
        )
        payload["questions"][0]["human_answer"] = "forged answer"
        self._write_requirement_questions(payload)
        self.assertIn("questions-invalid-answer-evidence", self.codes())

    def test_answered_questions_reject_pre_post_or_impact_drift(self) -> None:
        payload = self._answered_requirement_questions()
        payload["questions"][0]["pre_answer_baseline_version"] = "req-v1"
        payload["questions"][0]["pre_answer_baseline_sha256"] = payload["baseline_sha256"]
        self._write_requirement_questions(payload)
        self.assertIn("questions-answered-question-baseline-not-updated", self.codes())
        payload = self._answered_requirement_questions()
        payload["gate_reruns"][0]["affected_scope"] = ["REQ-X"]
        self._write_requirement_questions(payload)
        self.assertIn("questions-answered-question-rerun-required", self.codes())

    def test_answered_questions_allow_local_rerun_receipt_without_host_verifier(self) -> None:
        self._write_requirement_questions(self._answered_requirement_questions())
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent, swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend, requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=self.requirement_questions_sha256,
            requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest(),
            project_root=self.root,
        )
        self.assertNotIn("questions-question-rerun-receipt-not-validated", {item.code for item in issues})

    def test_valid_delivery_bundle_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_closure_candidate_bundle_passes_at_the_planned_stage(self) -> None:
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8").replace(
                "- Status: completed", "- Status: in_progress",
            ),
            encoding="utf-8",
        )
        self.module_run.write_text(
            self.module_run.read_text(encoding="utf-8").replace(
                "- Status: completed", "- Status: in_progress",
            ),
            encoding="utf-8",
        )
        evidence = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        evidence["stage"] = "closure_candidate"
        self.multi_agent.write_text(json.dumps(evidence), encoding="utf-8")
        self._write_delivery_contract(stage="closure_candidate")

        self.assertEqual(set(), self.codes(stage="closure_candidate"))

    def test_closure_candidate_is_exposed_by_all_delivery_clis(self) -> None:
        for script in (
            "validate_traceability.py",
            "validate_multi_agent_evidence.py",
            "validate_delivery_bundle.py",
        ):
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / script), "--help"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("closure_candidate", result.stdout)

    def test_gate_inputs_cannot_rebind_to_noncanonical_questions(self) -> None:
        alternate = self.root / "alternate-requirement-questions.json"
        alternate.write_bytes(self.requirement_questions.read_bytes())
        self._rebind_gate_inputs_to_questions(alternate)
        self.assertIn(
            "agents-evidence-noncanonical-requirement-questions", self.codes(),
        )

    def test_public_delivery_api_rejects_host_verifier_injection(self) -> None:
        self.assertNotIn("host_attestation_verifier", inspect.signature(validate_delivery_bundle).parameters)
        with self.assertRaises(TypeError):
            validate_delivery_bundle(
                agents_path=self.agents, trace_path=self.trace_fixture.matrix,
                context_path=self.context, command_manifest_path=self.commands,
                multi_agent_evidence_path=self.multi_agent,
                swimlane_evidence_path=self.swimlane, frontend_evidence_path=self.frontend,
                project_root=self.root, host_attestation_verifier=lambda *_: True,
            )

    def test_public_delivery_accepts_bound_local_coordination_receipts(self) -> None:
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane, frontend_evidence_path=self.frontend,
            project_root=self.root,
        )
        self.assertNotIn(
            "agents-evidence-implementation-receipt-not-validated",
            {issue.code for issue in issues},
        )

    def test_context_module_must_exist_in_canonical_ownership_map(self) -> None:
        text = self.context.read_text(encoding="utf-8")
        text = text.replace("Modules: module", "Modules: fake-module")
        text = text.replace("Module changed files: module=", "Module changed files: fake-module=")
        self.context.write_text(text, encoding="utf-8")
        self.assertIn("bundle-unknown-canonical-module", self.codes())

    def test_changed_file_must_be_owned_by_declared_module(self) -> None:
        self.agents.write_text(
            project_root_fixture().replace("`src/` | ModuleMaintainer", "`lib/` | ModuleMaintainer"),
            encoding="utf-8",
        )
        self.assertIn("bundle-changed-file-owner-mismatch", self.codes())

    def test_implementation_title_must_match_registered_module_maintainer(self) -> None:
        data = self._multi_agent_evidence()
        data["implementation_agent_title"] = "AnotherAgent"
        self.multi_agent.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("bundle-maintainer-title-mismatch", self.codes())

    def test_implementation_model_must_be_machine_verified_sol(self) -> None:
        data = self._multi_agent_evidence()
        data["implementation_agent_model"] = "gpt-5.6-terra"
        self.multi_agent.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("agents-evidence-invalid-implementation-agent", self.codes())

    def test_non_path_ownership_cannot_disable_runtime_binding(self) -> None:
        self.agents.write_text(
            project_root_fixture().replace("`src/` | ModuleMaintainer", "shared protocol API | ModuleMaintainer"),
            encoding="utf-8",
        )
        data = self._multi_agent_evidence()
        data["implementation_agent_title"] = "SpoofedMaintainer"
        self.multi_agent.write_text(json.dumps(data), encoding="utf-8")
        codes = self.codes()
        self.assertIn("agents-invalid-module-agent-boundary-path", codes)
        self.assertIn("bundle-module-ownership-invalid", codes)

    def test_cross_module_system_bundle_requires_individual_module_closures(self) -> None:
        text = self.context.read_text(encoding="utf-8")
        text = text.replace("Modules: module", "Modules: module, module2")
        text = text.replace(
            "Module changed files: module=src/module.py",
            "Module changed files: module=src/module.py; module2=src/module.py",
        )
        self.context.write_text(text, encoding="utf-8")
        self.assertIn("cross-module-bundle-requires-module-closures", self.codes())

    def test_missing_swimlane_evidence_blocks_delivery(self) -> None:
        issues = validate_delivery_bundle(
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=None, frontend_evidence_path=self.frontend, project_root=self.root,
        )
        self.assertIn("missing-swimlane-evidence", {item.code for item in issues})

    def test_non_applicable_swimlane_does_not_require_evidence(self) -> None:
        self._rewrite_contract_change("flow_impact", "none")
        self._rewrite_contract_change("swimlane_applicable", False)
        self._apply_swimlane_gate_plan_to_records()
        issues = _test_only_validate_delivery_bundle(
            delivery_contract_path=self.contract,
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent, swimlane_evidence_path=None,
            frontend_evidence_path=self.frontend,
            requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=self.requirement_questions_sha256,
            requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256(
                (self.root / "requirements/baseline.md").read_bytes()
            ).hexdigest(),
            project_root=self.root, _test_only_host_attestation_verifier=lambda *_: True,
        )
        self.assertEqual([], issues)

    def test_swimlane_freshness_gate_drives_review_without_evidence_path(self) -> None:
        self._rewrite_contract_change("flow_impact", "none")
        self._apply_swimlane_gate_plan_to_records()
        issues = _test_only_validate_delivery_bundle(
            delivery_contract_path=self.contract,
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent, swimlane_evidence_path=None,
            frontend_evidence_path=self.frontend,
            requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=self.requirement_questions_sha256,
            requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256(
                (self.root / "requirements/baseline.md").read_bytes()
            ).hexdigest(),
            project_root=self.root, _test_only_host_attestation_verifier=lambda *_: True,
        )
        self.assertEqual([], issues)

    def test_frontend_browser_must_bind_independent_black_box_run(self) -> None:
        data = json.loads(self.frontend.read_text(encoding="utf-8"))
        data["browser"]["verifier_agent_run_id"] = "implementation-run"
        self.frontend.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("frontend-black-box-run-mismatch", self.codes())

    def test_closure_candidate_frontend_browser_must_bind_independent_black_box_run(self) -> None:
        self.progress.write_text(
            self.progress.read_text(encoding="utf-8").replace(
                "- Status: completed", "- Status: in_progress",
            ),
            encoding="utf-8",
        )
        self.module_run.write_text(
            self.module_run.read_text(encoding="utf-8").replace(
                "- Status: completed", "- Status: in_progress",
            ),
            encoding="utf-8",
        )
        agents = json.loads(self.multi_agent.read_text(encoding="utf-8"))
        agents["stage"] = "closure_candidate"
        self.multi_agent.write_text(json.dumps(agents), encoding="utf-8")
        frontend = json.loads(self.frontend.read_text(encoding="utf-8"))
        transcript_path = self.root / frontend["browser"]["transcript_path"]
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        transcript["verifier_agent_run_id"] = "implementation-run"
        transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
        frontend["browser"]["verifier_agent_run_id"] = "implementation-run"
        frontend["browser"]["transcript_sha256"] = hashlib.sha256(
            transcript_path.read_bytes(),
        ).hexdigest()
        self.frontend.write_text(json.dumps(frontend), encoding="utf-8")
        self._write_delivery_contract(stage="closure_candidate")

        self.assertIn(
            "frontend-black-box-run-mismatch",
            self.codes(stage="closure_candidate"),
        )

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

    def test_review_trigger_must_be_closure_candidate_or_bound_human_request(self) -> None:
        transcript = self.root / "evidence/automated-review.json"
        data = json.loads(transcript.read_text(encoding="utf-8"))
        data["review_trigger"] = "after_each_code_change"
        transcript.write_text(json.dumps(data), encoding="utf-8")
        transcript_hash = hashlib.sha256(transcript.read_bytes()).hexdigest()
        text = self.review.read_text(encoding="utf-8").replace(
            "Review trigger: module_closure_candidate", "Review trigger: after_each_code_change",
        )
        text = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {transcript_hash}", text,
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertIn("bundle-automated-review-unexecuted", self.codes())

        data["review_trigger"] = "human_requested"
        data["human_trigger_reference"] = "user-message:review-1"
        transcript.write_text(json.dumps(data), encoding="utf-8")
        transcript_hash = hashlib.sha256(transcript.read_bytes()).hexdigest()
        text = self.review.read_text(encoding="utf-8").replace(
            "Review trigger: after_each_code_change", "Review trigger: human_requested",
        ).replace(
            "Human trigger reference: N/A", "Human trigger reference: user-message:review-1",
        )
        text = re.sub(
            r"Review evidence SHA-256: [0-9a-f]{64}",
            f"Review evidence SHA-256: {transcript_hash}", text,
        )
        self.review.write_text(text, encoding="utf-8")
        self.assertNotIn("bundle-automated-review-unexecuted", self.codes())

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

    def test_mobile_web_trace_cannot_disable_frontend_applicability(self) -> None:
        data = json.loads(self.commands.read_text(encoding="utf-8"))
        data["frontend_applicable"] = False
        self.commands.write_text(json.dumps(data), encoding="utf-8")
        trace_text = self.trace_fixture.matrix.read_text(encoding="utf-8").replace(
            "Change surfaces: ui,user-visible", "Change surfaces: mobile-web",
        )
        self.trace_fixture.matrix.write_text(trace_text, encoding="utf-8")
        issues = []
        self.assertTrue(
            _frontend_applicable(
                self.commands, self.trace_fixture.matrix, "implementation", issues,
            )
        )
        self.assertIn("frontend-applicability-mismatch", {item.code for item in issues})

    def test_delivery_contract_artifacts_must_match_bundle_inputs(self) -> None:
        alternate = self.root / "docs/alternate-trace.md"
        alternate.write_bytes(self.trace_fixture.matrix.read_bytes())
        contract = self.root / "docs/delivery-contract.json"
        contract.write_text(json.dumps({
            "artifacts": {
                "traceability": {
                    "path": alternate.relative_to(self.root).as_posix(),
                    "sha256": hashlib.sha256(alternate.read_bytes()).hexdigest(),
                },
                "command_manifest": {
                    "path": self.commands.relative_to(self.root).as_posix(),
                    "sha256": hashlib.sha256(self.commands.read_bytes()).hexdigest(),
                },
            },
        }), encoding="utf-8")
        issues = _test_only_validate_delivery_bundle(
            delivery_contract_path=contract,
            agents_path=self.agents, trace_path=self.trace_fixture.matrix,
            context_path=self.context, command_manifest_path=self.commands,
            multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend,
            requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=self.requirement_questions_sha256,
            requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256(
                (self.root / "requirements/baseline.md").read_bytes()
            ).hexdigest(),
            project_root=self.root,
            _test_only_host_attestation_verifier=lambda *_: True,
        )
        self.assertIn("contract-artifact-path-mismatch", {item.code for item in issues})

    def test_delivery_contract_configuration_files_must_match_context(self) -> None:
        self._assert_valid_contract_change_drift_is_rejected(
            "configuration_files", ["commands.txt"],
        )

    def test_delivery_contract_input_files_must_match_context(self) -> None:
        self._assert_valid_contract_change_drift_is_rejected(
            "input_files", ["index.html"],
        )

    def test_delivery_contract_dependency_boundaries_must_match_context(self) -> None:
        self._assert_valid_contract_change_drift_is_rejected(
            "direct_dependency_boundaries", "unrelated dependency boundary",
        )

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

    def test_swimlane_templates_delegate_records_paths_and_reruns_to_gate_plan(self) -> None:
        assets = Path(__file__).resolve().parent.parent / "assets"
        agents = (assets / "AGENTS.template.md").read_text(encoding="utf-8")
        review = (assets / "automated-review-evidence.template.md").read_text(encoding="utf-8")
        output = (assets / "automated-review-output.template.json").read_text(encoding="utf-8")
        module_bundle = (assets / "module-delivery-bundle.template.json").read_text(encoding="utf-8")
        execution = (assets / "execution-run.template.md").read_text(encoding="utf-8")
        latest = (assets / "module-latest.template.md").read_text(encoding="utf-8")
        self.assertIn("synchronize only applicable and mapped design, swimlane, UI, test, and acceptance artifacts selected by the gate plan", agents)
        self.assertIn("{{GATE_PLAN_SWIMLANE_SCOPE_SUFFIX_OR_EMPTY}}", review)
        self.assertIn("{{TARGETED_TESTS_CODE_STANDARDS_TRACEABILITY_AUTOMATED_REVIEW_AND_GATE_PLAN_SWIMLANE_IDS}}", review)
        self.assertIn("{{GATE_PLAN_SWIMLANE_RERUN_ID_OR_REMOVE_ENTRY}}", output)
        self.assertIn("{{GATE_PLAN_SWIMLANE_EVIDENCE_PATH_OR_NULL}}", module_bundle)
        self.assertIn("{{GATE_PLAN_SWIMLANE_EVIDENCE_RECORD_OR_OMIT}}", execution)
        self.assertIn("{{GATE_PLAN_SWIMLANE_DIAGRAM_RECORD_OR_OMIT}}", execution)
        self.assertIn("{{GATE_PLAN_SWIMLANE_EVIDENCE_RECORD_OR_OMIT}}", latest)

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
        self._write_delivery_contract(stage="implementation")
        self._apply_swimlane_gate_plan_to_records()
        issues = _test_only_validate_delivery_bundle(
            delivery_contract_path=self.contract,
            agents_path=self.agents, trace_path=self.trace_fixture.matrix, context_path=self.context,
            command_manifest_path=self.commands, multi_agent_evidence_path=self.multi_agent,
            swimlane_evidence_path=self.swimlane,
            frontend_evidence_path=self.frontend,
            requirement_questions_path=self.requirement_questions,
            requirement_questions_sha256=self.requirement_questions_sha256,
            requirement_baseline_version="req-v1",
            requirement_baseline_sha256=hashlib.sha256(
                (self.root / "requirements/baseline.md").read_bytes()
            ).hexdigest(),
            project_root=self.root, stage="implementation",
            _test_only_host_attestation_verifier=lambda *_: True,
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
