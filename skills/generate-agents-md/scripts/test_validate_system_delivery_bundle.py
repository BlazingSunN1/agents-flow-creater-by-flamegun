from __future__ import annotations

import hashlib
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_system_delivery_bundle import (
    _test_only_validate_system_delivery_bundle,
    validate_system_delivery_bundle,
)
from system_actor_validation import system_candidate_payload_sha256
from system_record_path_validation import cross_module_record_template_error
from test_validate_agents_md import project_root_fixture


AUTHORITY_LOCATOR = "AGENTS.md#machine-enforced-authority-matrix"
AUTHORITY_SHA256 = "aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643"
MODULE_AUTHORITY_ROWS = [
    {"role": "module-maintainer", "action": "write_module_artifacts", "policy": "allow"},
    {
        "role": "module-maintainer",
        "action": "record_completion_after_verified_gates",
        "policy": "independent-only",
    },
    {
        "role": "independent-reviewer",
        "action": "issue_independent_verdict",
        "policy": "allow",
    },
]
SYSTEM_AUTHORITY_ROWS = [
    {"role": "system-aggregation", "action": "write_system_manifest", "policy": "allow"},
    {"role": "dispatcher", "action": "orchestrate_read_validate", "policy": "allow"},
]


def authority_binding(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "locator": AUTHORITY_LOCATOR,
        "sha256": AUTHORITY_SHA256,
        "required_rows": rows,
    }


class SystemDeliveryBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "evidence").mkdir()
        (self.root / "src/a").mkdir(parents=True)
        (self.root / "src/b").mkdir(parents=True)
        (self.root / "src/a/a.py").write_text("a = 1\n", encoding="utf-8")
        (self.root / "src/b/b.py").write_text("b = 1\n", encoding="utf-8")
        self.agents = self.root / "AGENTS.md"
        agents_text = project_root_fixture().replace(
            "| module | verified module scope | `src/` | ModuleMaintainer |",
            "| module-a | capability a | `src/a/` | Maintainer A |\n"
            "| module-b | capability b | `src/b/` | Maintainer B |",
        ).replace(
            "docs/progress_record_path.md",
            "docs/progress/<module>/<run_id>.md",
        ).replace(
            "docs/automated_review_evidence_path.md",
            "docs/reviews/<module>/<run_id>.md",
        )
        self.agents.write_text(agents_text, encoding="utf-8")
        self.bundle_paths = [self._module_bundle("module-a", "REQ-A"), self._module_bundle("module-b", "REQ-B")]
        self.dispatcher_receipt = self.root / "evidence/system-dispatcher-spawn-receipt.json"
        self.dispatcher_receipt.write_text(json.dumps({
            "schema_version": 1,
            "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "agent_id": "system-dispatcher-agent-1",
            "run_id": "dispatcher-run-1",
            "role": "dispatcher",
            "module": "system",
            "maintainer_title": "System Dispatcher",
        }), encoding="utf-8")
        self.aggregation_receipt = self.root / "evidence/system-aggregation-spawn-receipt.json"
        self.manifest = self.root / "evidence/system-bundle.json"
        self._write_system_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _module_bundle(self, module: str, requirement: str) -> Path:
        suffix = module[-1]
        context = self.root / f"evidence/{module}-context.md"
        context.write_text(
            f"- Modules: {module}\n"
            f"- Requirement IDs: {requirement}\n"
            "- Code version: code-v1\n"
            "- Build ID: build-1\n"
            f"- Module changed files: {module}=src/{suffix}/{suffix}.py\n",
            encoding="utf-8",
        )
        evidence = self.root / f"evidence/{module}-agents.json"
        title = f"Maintainer {suffix.upper()}"
        receipt = self.root / f"evidence/{module}-spawn-receipt.json"
        receipt.write_text(json.dumps({
            "schema_version": 1,
            "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "requested_reasoning_effort": "medium",
            "recorded_reasoning_effort": "medium",
            "agent_id": f"maintainer-agent-{suffix}",
            "run_id": f"impl-run-{suffix}",
            "role": "module-maintainer",
            "module": module,
            "maintainer_title": title,
        }), encoding="utf-8")
        gate_receipt = self.root / f"evidence/{module}-black-box-spawn-receipt.json"
        gate_receipt.write_text(json.dumps({
            "schema_version": 1,
            "receipt_kind": "codex-native-spawn-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "requested_reasoning_effort": "high",
            "recorded_reasoning_effort": "high",
            "agent_id": f"bb-agent-{suffix}",
            "run_id": f"bb-run-{suffix}",
            "role": "black-box-gate",
            "module": module,
            "maintainer_title": "BLACK_BOX Gate Reviewer",
        }), encoding="utf-8")
        gate_input_sha256 = hashlib.sha256(f"{module}-input".encode()).hexdigest()
        gate_output_sha256 = hashlib.sha256(f"{module}-output".encode()).hexdigest()
        candidate_sha256 = hashlib.sha256(f"{module}-candidate".encode()).hexdigest()
        gate_output_receipt = self.root / f"evidence/{module}-black-box-output-result.json"
        gate_output_receipt.write_text(json.dumps({
            "schema_version": 1,
            "receipt_kind": "codex-native-output-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "requested_reasoning_effort": "high",
            "recorded_reasoning_effort": "high",
            "agent_id": f"bb-agent-{suffix}",
            "run_id": f"bb-run-{suffix}",
            "role": "black-box-gate",
            "module": module,
            "maintainer_title": "BLACK_BOX Gate Reviewer",
            "input_sha256": gate_input_sha256,
            "output_sha256": gate_output_sha256,
            "baseline_version": "req-v1",
            "code_version": "code-v1",
            "build_id": "build-1",
            "candidate_sha256": candidate_sha256,
            "verdict": "pass",
        }), encoding="utf-8")
        evidence.write_text(json.dumps({
            "schema_version": 1,
            "stage": "completion",
            "implementation_agent_title": title,
            "implementation_agent_provider": "codex-native-agent",
            "implementation_agent_model": "gpt-6-astra",
            "implementation_agent_reasoning_effort": "medium",
            "implementation_agent_id": f"maintainer-agent-{suffix}",
            "implementation_run_id": f"impl-run-{suffix}",
            "implementation_spawn_receipt": f"evidence/{module}-spawn-receipt.json",
            "implementation_spawn_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
            "baseline_version": "req-v1",
            "baseline_sha256": hashlib.sha256(f"{module}-baseline".encode()).hexdigest(),
            "candidate_sha256": candidate_sha256,
            "code_version": "code-v1",
            "build_id": "build-1",
            "single_writer_run_id": f"impl-run-{suffix}",
            "gates": [{
                "role": "BLACK_BOX", "run_id": f"bb-run-{suffix}",
                "provider": "codex-native-agent", "agent_model": "gpt-6-astra",
                "agent_reasoning_effort": "high",
                "agent_id": f"bb-agent-{suffix}",
                "spawn_receipt": f"evidence/{module}-black-box-spawn-receipt.json",
                "spawn_receipt_sha256": hashlib.sha256(gate_receipt.read_bytes()).hexdigest(),
                "output_receipt": f"evidence/{module}-black-box-output-result.json",
                "output_receipt_sha256": hashlib.sha256(gate_output_receipt.read_bytes()).hexdigest(),
                "input_sha256": gate_input_sha256,
                "output_sha256": gate_output_sha256,
                "verdict": "pass",
            }],
            "open_disagreements": [],
        }), encoding="utf-8")
        baseline_sha = hashlib.sha256(f"{module}-baseline".encode()).hexdigest()
        questions = self.root / f"evidence/{module}-requirement-questions.json"
        questions.write_text(json.dumps({
            "schema_version": 1,
            "baseline_version": "req-v1",
            "baseline_sha256": baseline_sha,
            "questions": [],
            "gate_reruns": [],
        }), encoding="utf-8")
        artifacts = {"agents": "AGENTS.md", "context": f"evidence/{module}-context.md",
                     "multi_agent_evidence": f"evidence/{module}-agents.json",
                     "requirement_questions": f"evidence/{module}-requirement-questions.json",
                     "requirement_questions_sha256": hashlib.sha256(questions.read_bytes()).hexdigest()}
        for key in ("trace", "command_manifest", "swimlane_evidence"):
            path = self.root / f"evidence/{module}-{key}.json"
            path.write_text("{}\n", encoding="utf-8")
            artifacts[key] = f"evidence/{module}-{key}.json"
        artifacts["frontend_evidence"] = None
        bundle = {
            "schema_version": 2, "module": module, "requirement_ids": [requirement],
            "requirement_baseline_version": "req-v1",
            "requirement_baseline_sha256": baseline_sha,
            "authority_binding": authority_binding(MODULE_AUTHORITY_ROWS),
            "code_version": "code-v1", "build_id": "build-1", "maintainer_title": title,
            "maintainer_provider": "codex-native-agent", "maintainer_model": "gpt-6-astra",
            "maintainer_reasoning_effort": "medium",
            "maintainer_agent_id": f"maintainer-agent-{suffix}",
            "maintainer_spawn_receipt": f"evidence/{module}-spawn-receipt.json",
            "maintainer_spawn_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
            "implementation_run_id": f"impl-run-{suffix}", "stage": "completion",
            "open_findings": [], "artifacts": artifacts,
        }
        path = self.root / f"evidence/{module}-bundle.json"
        path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")
        return path

    def _write_system_manifest(self, **updates: object) -> None:
        entries = [{
            "module": path.stem.removesuffix("-bundle"),
            "bundle_manifest_path": f"evidence/{path.name}",
            "bundle_manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in self.bundle_paths]
        value = {
            "schema_version": 2, "dispatcher_mode": "read-only",
            "authority_binding": authority_binding(SYSTEM_AUTHORITY_ROWS),
            "dispatcher_title": "System Dispatcher",
            "dispatcher_provider": "codex-native-agent",
            "dispatcher_model": "gpt-6-astra",
            "dispatcher_agent_id": "system-dispatcher-agent-1",
            "dispatcher_run_id": "dispatcher-run-1",
            "dispatcher_spawn_receipt": "evidence/system-dispatcher-spawn-receipt.json",
            "dispatcher_spawn_receipt_sha256": hashlib.sha256(self.dispatcher_receipt.read_bytes()).hexdigest(),
            "aggregation_writer_role": "SYSTEM_AGGREGATION",
            "aggregation_writer_title": "System Aggregation Writer",
            "aggregation_writer_provider": "codex-native-agent",
            "aggregation_writer_model": "gpt-6-astra",
            "aggregation_writer_agent_id": "system-aggregation-agent-1",
            "aggregation_writer_run_id": "system-aggregation-run-1",
            "aggregation_spawn_receipt": "evidence/system-aggregation-spawn-receipt.json",
            "aggregation_spawn_receipt_sha256": "pending",
            "requirement_ids": ["REQ-A", "REQ-B"], "code_version": "code-v1", "build_id": "build-1",
            "agents_path": "AGENTS.md", "agents_sha256": hashlib.sha256(self.agents.read_bytes()).hexdigest(),
            "system_changed_files": ["src/a/a.py", "src/b/b.py"],
            "affected_modules": ["module-a", "module-b"], "module_bundles": entries,
            "open_findings": [],
        }
        value.update(updates)
        aggregation_receipt = {
            "schema_version": 1,
            "receipt_kind": "codex-native-output-result",
            "provider": "codex-native-agent",
            "requested_model": "gpt-6-astra",
            "recorded_model": "gpt-6-astra",
            "agent_id": value["aggregation_writer_agent_id"],
            "run_id": value["aggregation_writer_run_id"],
            "role": "system-aggregation",
            "module": "system",
            "maintainer_title": "System Aggregation Writer",
            "candidate_payload_sha256": system_candidate_payload_sha256(value),
            "authority_binding": value["authority_binding"],
        }
        self.aggregation_receipt.write_text(json.dumps(aggregation_receipt), encoding="utf-8")
        value["aggregation_spawn_receipt_sha256"] = hashlib.sha256(self.aggregation_receipt.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    def codes(self, validator=lambda **_: [], *, stage: str = "completion") -> set[str]:
        return {item.code for item in _test_only_validate_system_delivery_bundle(
            manifest_path=self.manifest, project_root=self.root, stage=stage,
            _test_only_module_validator=validator,
            _test_only_host_attestation_verifier=lambda *_: True,
        )}

    def test_valid_cross_module_closures_pass_read_only_aggregation(self) -> None:
        self.assertEqual(set(), self.codes())
        strict_codes = {
            item.code
            for item in _test_only_validate_system_delivery_bundle(
                manifest_path=self.manifest,
                project_root=self.root,
                _test_only_module_validator=lambda **_: [],
                _test_only_host_attestation_verifier=lambda *_: False,
            )
        }
        self.assertIn("system-dispatcher-receipt-not-validated", strict_codes)

    def test_cross_module_aggregation_rejects_shared_progress_path(self) -> None:
        text = self.agents.read_text(encoding="utf-8").replace(
            "docs/progress/<module>/<run_id>.md",
            "docs/progress.md",
        )
        self.agents.write_text(text, encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-record-path-template", self.codes())

    def test_cross_module_aggregation_rejects_shared_review_path(self) -> None:
        text = self.agents.read_text(encoding="utf-8").replace(
            "docs/reviews/<module>/<run_id>.md",
            "docs/reviews.md",
        )
        self.agents.write_text(text, encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-record-path-template", self.codes())

    def test_cross_module_record_placeholders_require_separate_components(self) -> None:
        text = self.agents.read_text(encoding="utf-8").replace(
            "docs/progress/<module>/<run_id>.md",
            "docs/progress/<module><run_id>.md",
        )
        self.agents.write_text(text, encoding="utf-8")
        self._write_system_manifest()
        issues = _test_only_validate_system_delivery_bundle(
            manifest_path=self.manifest,
            project_root=self.root,
            _test_only_module_validator=lambda **_: [],
            _test_only_host_attestation_verifier=lambda *_: True,
        )
        message = next(
            item.message for item in issues
            if item.code == "system-module-record-path-template"
        )
        self.assertIn("分别位于不同且不含路径遍历的安全组件", message)

    def test_cross_module_record_templates_reject_parent_traversal(self) -> None:
        text = self.agents.read_text(encoding="utf-8").replace(
            "docs/progress/<module>/<run_id>.md",
            "docs/<module>/../shared-progress/<run_id>.md",
        )
        self.agents.write_text(text, encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-record-path-template", self.codes())

    def test_commented_path_declaration_cannot_spoof_real_static_paths(self) -> None:
        text = """## Development Plan and Progress

<!-- - Completion progress path: `docs/progress/<module>/<run_id>.md` -->
- Completion progress path: `docs/progress.md`

## Automated Code Review

<!-- - Automated review evidence path: `docs/reviews/<module>/<run_id>.md` -->
- Automated review evidence path: `docs/reviews.md`
"""
        self.assertIsNotNone(cross_module_record_template_error(text))

    def test_fenced_path_declaration_cannot_spoof_real_static_paths(self) -> None:
        text = """## Development Plan and Progress

```text
- Completion progress path: `docs/progress/<module>/<run_id>.md`
```
- Completion progress path: `docs/progress.md`

## Automated Code Review

```text
- Automated review evidence path: `docs/reviews/<module>/<run_id>.md`
```
- Automated review evidence path: `docs/reviews.md`
"""
        self.assertIsNotNone(cross_module_record_template_error(text))

    def test_duplicate_path_declarations_fail_closed(self) -> None:
        text = """## Development Plan and Progress

- Completion progress path: `docs/progress/<module>/<run_id>.md`
- Completion progress path: `docs/progress/<module>/<run_id>.md`

## Automated Code Review

- Automated review evidence path: `docs/reviews/<module>/<run_id>.md`
"""
        self.assertIsNotNone(cross_module_record_template_error(text))

    def test_review_scope_is_not_a_review_evidence_path_declaration(self) -> None:
        text = """## Development Plan and Progress

- Completion progress path: `docs/progress/<module>/<run_id>.md`

## Automated Code Review

- Review scope: `src/`
- Automated review evidence path: `docs/reviews/<module>/<run_id>.md`
"""
        self.assertIsNone(cross_module_record_template_error(text))

    def test_closure_candidate_forwards_two_module_artifacts_and_composes_real_module_passes(self) -> None:
        from test_validate_delivery_bundle import DeliveryBundleValidatorTests

        fixtures: list[DeliveryBundleValidatorTests] = []
        calls: list[dict[str, object]] = []
        try:
            for path in self.bundle_paths:
                bundle = json.loads(path.read_text(encoding="utf-8"))
                bundle["stage"] = "closure_candidate"
                evidence_path = self.root / bundle["artifacts"]["multi_agent_evidence"]
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence["stage"] = "closure_candidate"
                evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")
            self._write_system_manifest()

            for _ in self.bundle_paths:
                fixture = DeliveryBundleValidatorTests(
                    methodName="test_closure_candidate_bundle_passes_at_the_planned_stage",
                )
                fixture.setUp()
                fixture.prepare_closure_candidate()
                fixtures.append(fixture)

            def validate_real_module(**kwargs: object) -> list[object]:
                # Process-level coverage invokes the public module-close validator directly.
                # This composition test isolates system-to-module argument binding while
                # requiring two independently complete module candidates to pass it.
                index = len(calls)
                calls.append(kwargs)
                fixture = fixtures[index]
                return fixture.public_issues(stage=str(kwargs["stage"]))

            self.assertEqual(
                set(),
                self.codes(validate_real_module, stage="closure_candidate"),
            )
            self.assertEqual(2, len(calls))
            path_arguments = {
                "agents": "agents_path",
                "trace": "trace_path",
                "context": "context_path",
                "command_manifest": "command_manifest_path",
                "multi_agent_evidence": "multi_agent_evidence_path",
                "swimlane_evidence": "swimlane_evidence_path",
                "frontend_evidence": "frontend_evidence_path",
                "delivery_contract": "delivery_contract_path",
                "requirement_questions": "requirement_questions_path",
            }
            for bundle_path, call in zip(self.bundle_paths, calls):
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
                artifacts = bundle["artifacts"]
                for artifact_field, argument in path_arguments.items():
                    expected = artifacts.get(artifact_field)
                    if expected is None:
                        self.assertIsNone(call[argument])
                    else:
                        self.assertEqual((self.root / expected).resolve(), Path(call[argument]).resolve())
                self.assertEqual(
                    artifacts["requirement_questions_sha256"],
                    call["requirement_questions_sha256"],
                )
                self.assertEqual(bundle["requirement_baseline_version"], call["requirement_baseline_version"])
                self.assertEqual(bundle["requirement_baseline_sha256"], call["requirement_baseline_sha256"])
            self.assertEqual({"closure_candidate"}, {call["stage"] for call in calls})
            self.assertEqual({self.root.resolve()}, {Path(call["project_root"]).resolve() for call in calls})
            self.assertEqual({False}, {call["allow_passwords"] for call in calls})
        finally:
            for fixture in fixtures:
                fixture.tearDown()

    def test_requested_stage_rejects_mismatched_or_invalid_system_aggregation(self) -> None:
        self.assertIn("system-module-not-complete", self.codes(stage="closure_candidate"))
        self.assertEqual({"system-stage-invalid"}, self.codes(stage="draft"))

    def test_old_module_without_requirement_closure_fields_fails_closed(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle.pop("requirement_baseline_version")
        bundle.pop("requirement_baseline_sha256")
        bundle["artifacts"].pop("requirement_questions")
        bundle["artifacts"].pop("requirement_questions_sha256")
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-bundle-schema", self.codes())

    def test_requirement_questions_hash_drift_fails_closed(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["artifacts"]["requirement_questions_sha256"] = "0" * 64
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-requirement-questions-hash-mismatch", self.codes())

    def test_module_validator_receives_requirement_closure_binding(self) -> None:
        calls: list[dict[str, object]] = []

        def validator(**kwargs: object) -> list[object]:
            calls.append(kwargs)
            return []

        self.assertEqual(set(), self.codes(validator))
        self.assertEqual(2, len(calls))
        for call in calls:
            self.assertIsInstance(call["requirement_questions_path"], Path)
            self.assertRegex(str(call["requirement_questions_sha256"]), r"^[0-9a-f]{64}$")
            self.assertEqual("req-v1", call["requirement_baseline_version"])
            self.assertRegex(str(call["requirement_baseline_sha256"]), r"^[0-9a-f]{64}$")

    def test_module_validator_receives_optional_contract_and_swimlane_path(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        contract = self.root / "evidence/module-a-delivery-contract.json"
        contract.write_text(json.dumps({"gate_plan": {"required_command_ids": []}}), encoding="utf-8")
        bundle["artifacts"]["delivery_contract"] = "evidence/module-a-delivery-contract.json"
        bundle["artifacts"]["swimlane_evidence"] = None
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        calls: list[dict[str, object]] = []

        self.assertEqual(set(), self.codes(lambda **kwargs: calls.append(kwargs) or []))
        module_a = next(call for call in calls if call["context_path"].name == "module-a-context.md")
        self.assertEqual(contract.resolve(), module_a["delivery_contract_path"])
        self.assertIsNone(module_a["swimlane_evidence_path"])

    def test_production_api_does_not_expose_module_validator_override(self) -> None:
        parameters = inspect.signature(validate_system_delivery_bundle).parameters
        self.assertNotIn("_test_only_module_validator", parameters)
        self.assertNotIn("host_attestation_verifier", parameters)
        with self.assertRaises(TypeError):
            validate_system_delivery_bundle(
                manifest_path=self.manifest, project_root=self.root,
                module_validator=lambda **_: [],  # type: ignore[call-arg]
            )
        with self.assertRaises(TypeError):
            validate_system_delivery_bundle(
                manifest_path=self.manifest, project_root=self.root,
                _test_only_module_validator=lambda **_: [],  # type: ignore[call-arg]
            )
        with self.assertRaises(TypeError):
            validate_system_delivery_bundle(
                manifest_path=self.manifest, project_root=self.root,
                host_attestation_verifier=lambda *_: True,  # type: ignore[call-arg]
            )

    def test_dispatcher_cannot_claim_write_authority(self) -> None:
        self._write_system_manifest(dispatcher_mode="writer")
        self.assertIn("system-bundle-authority", self.codes())

    def test_dispatcher_cannot_author_system_manifest(self) -> None:
        self._write_system_manifest(aggregation_writer_role="Dispatcher")
        self.assertIn("system-bundle-authority", self.codes())

    def test_aggregation_writer_must_be_independent_of_dispatcher_and_modules(self) -> None:
        for run_id in ("dispatcher-run-1", "impl-run-a", "bb-run-a"):
            with self.subTest(run_id=run_id):
                self._write_system_manifest(aggregation_writer_run_id=run_id)
                self.assertIn("system-aggregation-writer-not-independent", self.codes())

    def test_aggregation_writer_cannot_reuse_maintainer_agent_with_new_run(self) -> None:
        self._write_system_manifest(aggregation_writer_agent_id="maintainer-agent-a")
        self.assertIn("system-aggregation-writer-not-independent", self.codes())

    def test_dispatcher_cannot_reuse_maintainer_agent_with_new_run(self) -> None:
        receipt = json.loads(self.dispatcher_receipt.read_text(encoding="utf-8"))
        receipt["agent_id"] = "maintainer-agent-a"
        self.dispatcher_receipt.write_text(json.dumps(receipt), encoding="utf-8")
        self._write_system_manifest(dispatcher_agent_id="maintainer-agent-a")
        self.assertIn("system-native-agent-identity-collision", self.codes())

    def test_each_module_requires_a_distinct_maintainer_agent_id(self) -> None:
        bundle = json.loads(self.bundle_paths[1].read_text(encoding="utf-8"))
        evidence_path = self.root / "evidence/module-b-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        receipt_path = self.root / "evidence/module-b-spawn-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for value in (bundle, evidence, receipt):
            key = "maintainer_agent_id" if value is bundle else (
                "implementation_agent_id" if value is evidence else "agent_id"
            )
            value[key] = "maintainer-agent-a"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        bundle["maintainer_spawn_receipt_sha256"] = receipt_hash
        evidence["implementation_spawn_receipt_sha256"] = receipt_hash
        self.bundle_paths[1].write_text(json.dumps(bundle), encoding="utf-8")
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-maintainer-agent-duplicate", self.codes())

    def test_aggregation_receipt_binds_system_candidate_payload(self) -> None:
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["code_version"] = "tampered-after-aggregation"
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.assertIn("invalid-system-aggregation-spawn-receipt", self.codes())

    def test_old_module_and_system_schema_versions_fail_closed(self) -> None:
        self._write_system_manifest(schema_version=1)
        self.assertIn("system-bundle-authority", self.codes())
        self._write_system_manifest()
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["schema_version"] = 1
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-not-complete", self.codes())

    def test_module_authority_binding_missing_or_hash_drift_fails_closed(self) -> None:
        for mutation in ("missing", "drift"):
            with self.subTest(mutation=mutation):
                bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
                if mutation == "missing":
                    bundle.pop("authority_binding")
                else:
                    bundle["authority_binding"]["sha256"] = "0" * 64
                self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
                self._write_system_manifest()
                self.assertTrue(
                    {"system-module-bundle-schema", "system-module-authority-binding"}
                    & self.codes()
                )
                self.bundle_paths[0] = self._module_bundle("module-a", "REQ-A")

    def test_unknown_module_authority_role_action_or_policy_fails_closed(self) -> None:
        for field, value in (
            ("role", "dispatcher"),
            ("action", "unknown-action"),
            ("policy", "deny"),
        ):
            with self.subTest(field=field):
                bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
                bundle["authority_binding"]["required_rows"][0][field] = value
                self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
                self._write_system_manifest()
                self.assertIn("system-module-authority-binding", self.codes())
                self.bundle_paths[0] = self._module_bundle("module-a", "REQ-A")

    def test_system_authority_binding_missing_or_unknown_row_fails_closed(self) -> None:
        self._write_system_manifest(authority_binding={
            "locator": AUTHORITY_LOCATOR,
            "sha256": AUTHORITY_SHA256,
            "required_rows": [
                {"role": "dispatcher", "action": "write_system_manifest", "policy": "allow"},
            ],
        })
        self.assertIn("system-authority-binding", self.codes())

    def test_aggregation_output_receipt_must_repeat_authority_binding(self) -> None:
        receipt = json.loads(self.aggregation_receipt.read_text(encoding="utf-8"))
        receipt.pop("authority_binding")
        self.aggregation_receipt.write_text(json.dumps(receipt), encoding="utf-8")
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["aggregation_spawn_receipt_sha256"] = hashlib.sha256(
            self.aggregation_receipt.read_bytes()
        ).hexdigest()
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.assertIn("system-aggregation-authority-binding", self.codes())

    def test_system_and_every_module_bind_same_authority_locator_and_sha(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["authority_binding"]["locator"] = "AGENTS.md#old-authority-matrix"
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-authority-binding", self.codes())

    def test_effective_agents_authority_locator_or_sha_drift_fails_closed(self) -> None:
        for old, new in (
            (AUTHORITY_LOCATOR, "AGENTS.md#old-authority-matrix"),
            (AUTHORITY_SHA256, "0" * 64),
        ):
            with self.subTest(field=old[:12]):
                original = self.agents.read_text(encoding="utf-8")
                self.agents.write_text(original.replace(old, new), encoding="utf-8")
                self._write_system_manifest(
                    agents_sha256=hashlib.sha256(self.agents.read_bytes()).hexdigest(),
                )
                self.assertIn("system-agents-authority-binding", self.codes())
                self.agents.write_text(original, encoding="utf-8")

    def test_effective_agents_missing_authority_matrix_body_fails_closed(self) -> None:
        text = self.agents.read_text(encoding="utf-8")
        start = text.index("## Machine-Enforced Authority Matrix")
        end = text.index("\n## ", start + 3)
        self.agents.write_text(text[:start] + text[end + 1:], encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-agents-authority-binding", self.codes())

    def test_system_candidate_hash_uses_normalized_json_body(self) -> None:
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.manifest.write_text(
            json.dumps(value, ensure_ascii=False, indent=4, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(set(), self.codes())

    def test_bound_local_aggregation_receipts_do_not_block_delivery(self) -> None:
        codes = {item.code for item in validate_system_delivery_bundle(
            manifest_path=self.manifest, project_root=self.root,
        )}
        self.assertNotIn("system-dispatcher-receipt-not-validated", codes)
        self.assertNotIn("system-aggregation-receipt-not-validated", codes)

    def test_system_revalidates_gate_identity_when_module_validator_is_injected(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        gate = evidence["gates"][0]
        gate["agent_id"] = "maintainer-agent-a"
        receipt_path = self.root / gate["spawn_receipt"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["agent_id"] = "maintainer-agent-a"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        gate["spawn_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-reused-or-missing-agent-id", self.codes())

    def test_injected_module_validator_cannot_bypass_gate_fail_verdict(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        gate = evidence["gates"][0]
        gate["verdict"] = "fail"
        output_path = self.root / gate["output_receipt"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["verdict"] = "fail"
        output_path.write_text(json.dumps(output), encoding="utf-8")
        gate["output_receipt_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("system-module-gate-not-pass", self.codes())

    def test_system_revalidates_gate_output_candidate_binding(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        gate = evidence["gates"][0]
        output_path = self.root / gate["output_receipt"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["candidate_sha256"] = "0" * 64
        output_path.write_text(json.dumps(output), encoding="utf-8")
        gate["output_receipt_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("system-invalid-gate-output-receipt", self.codes())

    def test_system_rejects_gate_output_missing_candidate_binding(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        gate = evidence["gates"][0]
        output_path = self.root / gate["output_receipt"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output.pop("candidate_sha256")
        output_path.write_text(json.dumps(output), encoding="utf-8")
        gate["output_receipt_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("system-invalid-gate-output-receipt", self.codes())

    def test_injected_module_validator_cannot_bypass_invalid_candidate_binding(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["candidate_sha256"] = None
        gate = evidence["gates"][0]
        output_path = self.root / gate["output_receipt"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["candidate_sha256"] = None
        output_path.write_text(json.dumps(output), encoding="utf-8")
        gate["output_receipt_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("system-module-candidate-binding-invalid", self.codes())

    def test_injected_module_validator_cannot_bypass_missing_gate_closure(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["gates"] = []
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assertIn("system-module-gates-incomplete", self.codes())

    def test_injected_module_validator_cannot_bypass_open_disagreement_or_stage(self) -> None:
        evidence_path = self.root / "evidence/module-a-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["stage"] = "implementation"
        evidence["open_disagreements"] = ["P1 unresolved"]
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        codes = self.codes()
        self.assertIn("system-module-not-closed", codes)
        self.assertIn("system-module-open-disagreement", codes)

    def test_injected_module_validator_cannot_bypass_module_open_findings(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["open_findings"] = ["P1 unresolved"]
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-open-finding", self.codes())

    def test_gate_reviewers_are_globally_distinct_between_modules(self) -> None:
        evidence_path = self.root / "evidence/module-b-agents.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        gate = evidence["gates"][0]
        gate["agent_id"] = "bb-agent-a"
        receipt_path = self.root / gate["spawn_receipt"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["agent_id"] = "bb-agent-a"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        gate["spawn_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-native-agent-identity-collision", self.codes())

    def test_boolean_system_schema_version_is_rejected(self) -> None:
        self._write_system_manifest(schema_version=True)
        self.assertIn("system-bundle-authority", self.codes())

    def test_boolean_module_schema_version_is_rejected(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["schema_version"] = True
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-not-complete", self.codes())

    def test_every_module_manifest_hash_is_bound(self) -> None:
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["module_bundles"][0]["bundle_manifest_sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.assertIn("system-module-bundle-hash-mismatch", self.codes())

    def test_affected_modules_must_equal_changed_file_owners_and_bundles(self) -> None:
        self._write_system_manifest(affected_modules=["module-a"])
        self.assertIn("system-affected-modules-mismatch", self.codes())

    def test_module_bundle_must_pass_individual_delivery_validator(self) -> None:
        failing = lambda **_: [SimpleNamespace(severity="error")]
        self.assertIn("system-module-bundle-invalid", self.codes(failing))

    def test_default_delivery_validator_runs_and_fails_closed_on_incomplete_artifacts(self) -> None:
        codes = {item.code for item in validate_system_delivery_bundle(
            manifest_path=self.manifest,
            project_root=self.root,
        )}
        self.assertIn("system-module-bundle-invalid", codes)

    def test_module_validator_crash_fails_closed(self) -> None:
        def crashing(**_: object) -> list[object]:
            raise RuntimeError("validator unavailable")

        self.assertIn("system-module-validator-crash", self.codes(crashing))

    def test_module_code_build_identity_must_match_system_candidate(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["build_id"] = "other-build"
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-module-build-mismatch", self.codes())

    def test_module_requirement_identity_must_match_context(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["requirement_ids"] = ["FAKE-REQ"]
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest(requirement_ids=["FAKE-REQ", "REQ-B"])
        self.assertIn("system-module-requirements-mismatch", self.codes())

    def test_module_code_build_identity_must_match_context_and_evidence(self) -> None:
        bundle = json.loads(self.bundle_paths[0].read_text(encoding="utf-8"))
        bundle["code_version"] = "fake-code"
        bundle["build_id"] = "fake-build"
        self.bundle_paths[0].write_text(json.dumps(bundle), encoding="utf-8")
        self._write_system_manifest(code_version="fake-code", build_id="fake-build")
        self.assertIn("system-module-artifact-identity-mismatch", self.codes())

    def test_system_changed_files_require_exact_module_context_coverage(self) -> None:
        self._write_system_manifest(system_changed_files=["src/a/a.py", "src/b/b.py", "src/b/extra.py"])
        self.assertIn("system-changed-files-mismatch", self.codes())

    def test_each_module_requires_a_distinct_implementation_run(self) -> None:
        bundle = json.loads(self.bundle_paths[1].read_text(encoding="utf-8"))
        bundle["implementation_run_id"] = "impl-run-a"
        self.bundle_paths[1].write_text(json.dumps(bundle), encoding="utf-8")
        evidence = self.root / "evidence/module-b-agents.json"
        value = json.loads(evidence.read_text(encoding="utf-8"))
        value["implementation_run_id"] = "impl-run-a"
        evidence.write_text(json.dumps(value), encoding="utf-8")
        self._write_system_manifest()
        self.assertIn("system-implementation-run-duplicate", self.codes())

    def test_module_manifest_hashes_must_be_unique(self) -> None:
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        duplicate = self.root / "evidence/duplicate-module-bundle.json"
        duplicate.write_bytes(self.bundle_paths[0].read_bytes())
        value["module_bundles"][1]["bundle_manifest_path"] = "evidence/duplicate-module-bundle.json"
        value["module_bundles"][1]["bundle_manifest_sha256"] = value["module_bundles"][0]["bundle_manifest_sha256"]
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.assertIn("system-module-bundle-duplicate", self.codes())

    def test_duplicate_json_keys_fail_closed(self) -> None:
        raw = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(raw.replace(
            '"dispatcher_mode": "read-only"',
            '"dispatcher_mode": "writer", "dispatcher_mode": "read-only"',
        ), encoding="utf-8")
        self.assertIn("system-bundle-unreadable", self.codes())

    def test_system_changed_files_reject_noncanonical_paths(self) -> None:
        for path in ("/src/a/a.py", "src\\a\\a.py", "src/./a.py", "src//a/a.py"):
            with self.subTest(path=path):
                self._write_system_manifest(system_changed_files=[path, "src/b/b.py"])
                self.assertIn("system-changed-file-owner-mismatch", self.codes())

    def test_system_changed_files_preserve_posix_case(self) -> None:
        self._write_system_manifest(system_changed_files=["SRC/A/A.PY", "SRC/B/B.PY"])
        self.assertTrue(
            {"system-changed-file-owner-mismatch", "system-changed-files-mismatch"} & self.codes()
        )


if __name__ == "__main__":
    unittest.main()
