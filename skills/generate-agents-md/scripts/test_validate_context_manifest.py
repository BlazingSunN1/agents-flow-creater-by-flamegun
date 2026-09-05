from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_context_manifest import _cache_key, _parse_metadata, _paths_fingerprint, validate_context_manifest
from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256, EXPECTED_AUTHORITY_MATRIX
from test_execution_run_support import reusable_execution_run
from reuse_source_run_validation import _valid_source_context


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets" / "context-manifest.template.md"


class ContextManifestValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("requirements/baseline.md", "src/module.py", "evidence/test.txt"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative, encoding="utf-8")
        (self.root / "commands.json").write_text('{"commands":[]}', encoding="utf-8")
        self._write_root_agents()
        self.path = self.root / "context.md"
        self.path.write_text(self._valid_manifest(), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_root_agents(self) -> None:
        matrix = json.dumps(EXPECTED_AUTHORITY_MATRIX, ensure_ascii=False, separators=(",", ":"))
        (self.root / "AGENTS.md").write_text(
            f"authority_matrix_sha256: {AUTHORITY_MATRIX_SHA256}\n\n"
            f"## Machine-Enforced Authority Matrix\n\n```json\n{matrix}\n```\n",
            encoding="utf-8",
        )

    def _valid_manifest(self, effective_agents: str = "AGENTS.md") -> str:
        baseline_sha = hashlib.sha256((self.root / "requirements/baseline.md").read_bytes()).hexdigest()
        code_fingerprint = _paths_fingerprint("src/module.py", self.root.resolve(), [], "changed-file")
        empty_fingerprint = hashlib.sha256(b"").hexdigest()
        command_fingerprint = hashlib.sha256(b"python3 -m unittest").hexdigest()
        values = {
            "Baseline artifact": "requirements/baseline.md",
            "Baseline version": "req-v1",
            "Baseline SHA-256": baseline_sha,
            "Authority matrix locator": "AGENTS.md#machine-enforced-authority-matrix",
            "Authority matrix SHA-256": AUTHORITY_MATRIX_SHA256,
            "Requirement IDs": "REQ-001",
            "Module changed files": "module=src/module.py",
            "Risk / expansion reason": "small; direct module only; no expansion",
            "Direct dependency boundaries": "direct callers and tests",
            "Code version": "code-v1",
            "Build ID": "build-1",
            "Code fingerprint": code_fingerprint,
            "Command fingerprint": command_fingerprint,
            "Effective AGENTS fingerprint": _paths_fingerprint(effective_agents, self.root.resolve(), [], "agents-file"),
            "Command manifest fingerprint": _paths_fingerprint("commands.json", self.root.resolve(), [], "command-manifest"),
            "Configuration fingerprint": empty_fingerprint,
            "Environment ID": "local-test",
            "Input fingerprint": empty_fingerprint,
            "Evidence fingerprint": _paths_fingerprint("evidence/test.txt", self.root.resolve(), [], "reuse-evidence"),
        }
        cache_key = _cache_key(values)
        source_run = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source_run.parent.mkdir(parents=True, exist_ok=True)
        source_context = source_run.parent / "context-prior-run.md"
        source_context.write_text(
            f"# Context Workset prior-run\n\n- Run ID: prior-run\n"
            f"- Authority matrix locator: AGENTS.md#machine-enforced-authority-matrix\n"
            f"- Authority matrix SHA-256: {AUTHORITY_MATRIX_SHA256}\n"
            f"- Evidence cache key: {cache_key}\n",
            encoding="utf-8",
        )
        source_run.write_text(reusable_execution_run(
            "prior-run", cache_key, "evidence/test.txt",
            baseline_sha=values["Baseline SHA-256"], risk_reason=values["Risk / expansion reason"],
        ), encoding="utf-8")
        reuse_record = self.root / "evidence/reuse-prior-run.json"
        reuse_record.write_text(json.dumps({
            "schema_version": 1,
            "run_id": "prior-run",
            "status": "passed",
            "evidence_cache_key": cache_key,
            "source_run_record": {
                "module": "module",
                "path": "docs/module_execution_log_directory/module/run-prior-run.md",
                "sha256": hashlib.sha256(source_run.read_bytes()).hexdigest(),
                "context_path": "docs/module_execution_log_directory/module/context-prior-run.md",
                "context_sha256": hashlib.sha256(source_context.read_bytes()).hexdigest(),
            },
            "evidence_paths": [{
                "path": "evidence/test.txt",
                "sha256": hashlib.sha256((self.root / "evidence/test.txt").read_bytes()).hexdigest(),
            }],
        }), encoding="utf-8")
        return f"""# Context Workset run-1

- Run ID: run-1
- Baseline artifact: requirements/baseline.md
- Baseline version: req-v1
- Baseline SHA-256: {baseline_sha}
- Authority matrix locator: AGENTS.md#machine-enforced-authority-matrix
- Authority matrix SHA-256: {AUTHORITY_MATRIX_SHA256}
- Code version: code-v1
- Build ID: build-1
- Risk / expansion reason: small; direct module only; no expansion
- Requirement IDs: REQ-001
- Modules: module
- Module changed files: module=src/module.py
- Changed files: src/module.py
- Configuration files: N/A: no configuration inputs
- Input files: N/A: no external inputs
- Direct dependency boundaries: direct callers and tests
- Required commands: python3 -m unittest
- Effective AGENTS files: {effective_agents}
- Effective AGENTS fingerprint: {values["Effective AGENTS fingerprint"]}
- Command manifest: commands.json
- Command manifest fingerprint: {values["Command manifest fingerprint"]}
- Code fingerprint: {code_fingerprint}
- Command fingerprint: {command_fingerprint}
- Configuration fingerprint: {empty_fingerprint}
- Environment ID: local-test
- Input fingerprint: {empty_fingerprint}
- Evidence fingerprint: {values["Evidence fingerprint"]}
- Evidence cache key: {cache_key}
- Reuse decision: reuse: prior-run
- Reuse record: evidence/reuse-prior-run.json
- Evidence paths: evidence/test.txt
"""

    def codes(self) -> set[str]:
        return {issue.code for issue in validate_context_manifest(self.path, project_root=self.root)}

    def _sync_source_context(self, data: dict[str, object], cache_key: str) -> None:
        source = data["source_run_record"]
        path = self.root / source["context_path"]
        path.write_text(
            f"# Context Workset prior-run\n\n- Run ID: prior-run\n"
            f"- Authority matrix locator: AGENTS.md#machine-enforced-authority-matrix\n"
            f"- Authority matrix SHA-256: {AUTHORITY_MATRIX_SHA256}\n"
            f"- Evidence cache key: {cache_key}\n",
            encoding="utf-8",
        )
        source["context_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def test_public_template_structure_passes(self) -> None:
        self.assertEqual([], validate_context_manifest(PUBLIC_TEMPLATE, project_root=SKILL_ROOT, template=True))

    def test_public_template_cannot_drift_from_frozen_authority_binding(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8").replace(AUTHORITY_MATRIX_SHA256, "0" * 64)
        self.path.write_text(text, encoding="utf-8")
        codes = {issue.code for issue in validate_context_manifest(
            self.path, project_root=self.root, template=True,
        )}
        self.assertIn("stale-authority-matrix-binding", codes)

    def test_authority_locator_and_sha_are_required(self) -> None:
        for field in ("Authority matrix locator", "Authority matrix SHA-256"):
            with self.subTest(field=field):
                text = "\n".join(
                    line for line in self._valid_manifest().splitlines()
                    if not line.startswith(f"- {field}:")
                ) + "\n"
                self.path.write_text(text, encoding="utf-8")
                self.assertIn("missing-field", self.codes())

    def test_authority_locator_and_sha_must_match_frozen_interface(self) -> None:
        for old, new in (
            ("AGENTS.md#machine-enforced-authority-matrix", "AGENTS.md#legacy-authority"),
            (AUTHORITY_MATRIX_SHA256, "0" * 64),
        ):
            with self.subTest(new=new):
                self.path.write_text(self._valid_manifest().replace(old, new), encoding="utf-8")
                self.assertIn("stale-authority-matrix-binding", self.codes())

    def test_authority_binding_is_part_of_evidence_cache_key(self) -> None:
        metadata, _ = _parse_metadata(self._valid_manifest())
        original = _cache_key(metadata)
        metadata["Authority matrix locator"] = "AGENTS.md#legacy-authority"
        self.assertNotEqual(original, _cache_key(metadata))
        metadata["Authority matrix locator"] = "AGENTS.md#machine-enforced-authority-matrix"
        metadata["Authority matrix SHA-256"] = "0" * 64
        self.assertNotEqual(original, _cache_key(metadata))

    def test_root_authority_matrix_drift_and_symlink_fail_closed(self) -> None:
        root_agents = self.root / "AGENTS.md"
        root_agents.write_text(root_agents.read_text(encoding="utf-8").replace(
            '"scope_binding":"effective-root-agents"', '"scope_binding":"legacy"',
        ), encoding="utf-8")
        self.assertIn("stale-authority-matrix-binding", self.codes())
        root_agents.unlink()
        policy = self.root / "authority.md"
        policy.write_text("linked", encoding="utf-8")
        root_agents.symlink_to(policy)
        self.assertIn("unsafe-authority-matrix-path", self.codes())

    def test_effective_agents_hardlink_alias_fails_closed(self) -> None:
        scoped = self.root / "src/AGENTS.md"
        os.link(self.root / "AGENTS.md", scoped)
        self.path.write_text(self._valid_manifest("AGENTS.md, src/AGENTS.md"), encoding="utf-8")
        self.assertIn("ambiguous-authority-policy-identity", self.codes())

    def test_public_reuse_source_context_template_matches_compact_contract(self) -> None:
        cache_key = "a" * 64
        template = (SKILL_ROOT / "assets/reuse-source-context.template.md").read_text(encoding="utf-8")
        text = template.replace("{{SUCCESSFUL_REUSED_RUN_ID}}", "prior-run").replace(
            "{{CURRENT_EVIDENCE_CACHE_KEY}}", cache_key,
        )
        path = self.root / "source-context.md"
        path.write_text(text, encoding="utf-8")
        source = {"context_path": "source-context.md", "context_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.assertTrue(_valid_source_context(source, self.root, "prior-run", cache_key))

    def test_compact_reuse_context_cannot_omit_or_drift_authority_binding(self) -> None:
        cache_key = "a" * 64
        template = (SKILL_ROOT / "assets/reuse-source-context.template.md").read_text(encoding="utf-8")
        text = template.replace("{{SUCCESSFUL_REUSED_RUN_ID}}", "prior-run").replace(
            "{{CURRENT_EVIDENCE_CACHE_KEY}}", cache_key,
        )
        for old, new in (
            ("- Authority matrix locator: AGENTS.md#machine-enforced-authority-matrix\n", ""),
            (AUTHORITY_MATRIX_SHA256, "0" * 64),
        ):
            with self.subTest(new=new):
                path = self.root / "source-context.md"
                path.write_text(text.replace(old, new), encoding="utf-8")
                source = {"context_path": "source-context.md", "context_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                self.assertFalse(_valid_source_context(source, self.root, "prior-run", cache_key))

    def test_reuse_record_schema_version_must_be_exact_integer(self) -> None:
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["schema_version"] = True
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-record", self.codes())

    def test_reuse_must_bind_existing_successful_source_run(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("reuse: prior-run", "reuse: ghost-run")
        self.path.write_text(text, encoding="utf-8")
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["run_id"] = "ghost-run"
        data["source_run_record"] = {
            "module": "module",
            "path": "docs/module_execution_log_directory/module/run-ghost-run.md",
            "sha256": "0" * 64,
            "context_path": "docs/module_execution_log_directory/module/context-prior-run.md",
            "context_sha256": data["source_run_record"]["context_sha256"],
        }
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-reuse-source-run", self.codes())

    def test_reuse_source_run_uses_strict_execution_record_schema(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "- Delivered result: fabricated\nUNVERIFIED\n",
            encoding="utf-8",
        )
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_rejects_conflicting_failed_status(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(
            source.read_text(encoding="utf-8").replace("- Status: completed", "- Status: failed"),
            encoding="utf-8",
        )
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_accepts_delivery_style_and_separated_evidence(self) -> None:
        extra = self.root / "evidence/rock and roll.txt"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("second evidence", encoding="utf-8")
        text = self.path.read_text(encoding="utf-8").replace(
            "Evidence paths: evidence/test.txt", "Evidence paths: evidence/test.txt, evidence/rock and roll.txt",
        )
        metadata, _ = _parse_metadata(text)
        text = text.replace(metadata["Evidence fingerprint"], _paths_fingerprint(
            "evidence/test.txt, evidence/rock and roll.txt", self.root.resolve(), [], "reuse-evidence",
        ))
        metadata, _ = _parse_metadata(text)
        text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.path.write_text(text, encoding="utf-8")
        metadata, _ = _parse_metadata(text)
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(reusable_execution_run(
            "prior-run", metadata["Evidence cache key"], "evidence/test.txt, evidence/rock and roll.txt",
            baseline_sha=metadata["Baseline SHA-256"], risk_reason=metadata["Risk / expansion reason"],
        ), encoding="utf-8")
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["evidence_cache_key"] = metadata["Evidence cache key"]
        self._sync_source_context(data, metadata["Evidence cache key"])
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        data["evidence_paths"].append({
            "path": "evidence/rock and roll.txt", "sha256": hashlib.sha256(extra.read_bytes()).hexdigest(),
        })
        data["evidence_paths"] = sorted(data["evidence_paths"], key=lambda item: item["path"])
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("stale-reuse-source-run", self.codes())
    def test_reuse_source_run_applies_formal_completion_semantics(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(
            source.read_text(encoding="utf-8").replace("Remaining risks: none", "Remaining risks: critical unresolved"),
            encoding="utf-8",
        )
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_accepts_formal_localized_heading(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(
            source.read_text(encoding="utf-8").replace("# Run prior-run", "# 执行 prior-run"), encoding="utf-8",
        )
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_binds_current_context_identity_fields(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(
            source.read_text(encoding="utf-8").replace("Code version: code-v1", "Code version: unrelated-v9"),
            encoding="utf-8",
        )
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_binds_module_build_and_environment(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        for old, new in (
            ("Module: module", "Module: ghost"),
            ("Build ID and acceptance environment: build-1 / local-test",
             "Build ID and acceptance environment: fabricated / wrong-env"),
        ):
            with self.subTest(new=new):
                self.path.write_text(self._valid_manifest(), encoding="utf-8")
                source.write_text(source.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                record = self.root / "evidence/reuse-prior-run.json"
                data = json.loads(record.read_text(encoding="utf-8"))
                data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
                record.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_record_module_must_match_current_workset(self) -> None:
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["module"] = "ghost"
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_run_binds_historical_context_provenance(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "docs/module_execution_log_directory/module/context-prior-run.md / ", "missing.md / wrong-",
        ), encoding="utf-8")
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_context_file_must_bind_run_and_cache(self) -> None:
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        context = self.root / data["source_run_record"]["context_path"]
        context.write_text(
            "# Context Workset ghost\n\n- Run ID: ghost\n- Evidence cache key: wrong\n", encoding="utf-8",
        )
        data["source_run_record"]["context_sha256"] = hashlib.sha256(context.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_reuse_source_context_rejects_duplicate_fields(self) -> None:
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        context = self.root / data["source_run_record"]["context_path"]
        context.write_text(
            context.read_text(encoding="utf-8") + "- Run ID: prior-run\n",
            encoding="utf-8",
        )
        data["source_run_record"]["context_sha256"] = hashlib.sha256(context.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_multi_module_reuse_requires_rerun(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("Modules: module", "Modules: module, other")
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("multi-module-reuse-requires-rerun", self.codes())

    def test_build_id_changes_invalidate_cache(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("Build ID: build-1", "Build ID: build-2")
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-evidence-cache-key", self.codes())

    def test_reuse_source_canonicalizes_requirement_and_module_file_order(self) -> None:
        (self.root / "src/other.py").write_text("other", encoding="utf-8")
        text = self._valid_manifest().replace(
            "Module changed files: module=src/module.py",
            "Module changed files: module=src/module.py,src/other.py",
        ).replace("Changed files: src/module.py", "Changed files: src/other.py, src/module.py").replace(
            "Requirement IDs: REQ-001", "Requirement IDs: REQ-002, REQ-001",
        )
        metadata, _ = _parse_metadata(text)
        code_fingerprint = _paths_fingerprint(
            metadata["Changed files"], self.root.resolve(), [], "changed-file",
        )
        text = text.replace(metadata["Code fingerprint"], code_fingerprint)
        metadata, _ = _parse_metadata(text)
        text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.path.write_text(text, encoding="utf-8")
        metadata, _ = _parse_metadata(text)
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_text(reusable_execution_run(
            "prior-run", metadata["Evidence cache key"], "evidence/test.txt",
            baseline_sha=metadata["Baseline SHA-256"], risk_reason=metadata["Risk / expansion reason"],
            changed_files="src/module.py, src/other.py", requirement_ids="REQ-001, REQ-002",
        ), encoding="utf-8")
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["evidence_cache_key"] = metadata["Evidence cache key"]
        self._sync_source_context(data, metadata["Evidence cache key"])
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("stale-reuse-source-run", self.codes())
        source.write_text(source.read_text(encoding="utf-8").replace(
            "Traceability IDs: REQ-001, REQ-002", "Traceability IDs: REQ-002, REQ-001",
        ).replace(
            "Changed files: src/module.py, src/other.py", "Changed files: src/other.py, src/module.py",
        ), encoding="utf-8")
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("stale-reuse-source-run", self.codes())

    def test_invalid_utf8_reuse_source_run_fails_closed(self) -> None:
        source = self.root / "docs/module_execution_log_directory/module/run-prior-run.md"
        source.write_bytes(b"\xff\xfeinvalid")
        record = self.root / "evidence/reuse-prior-run.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["source_run_record"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale-reuse-source-run", self.codes())

    def test_current_run_cannot_reuse_itself(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("reuse: prior-run", "reuse: run-1")
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("reuse-current-run", self.codes())

    def test_requirement_ids_must_be_unique(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("Requirement IDs: REQ-001", "Requirement IDs: REQ-001, REQ-001")
        metadata, _ = _parse_metadata(text)
        text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("invalid-requirement-ids", self.codes())

    def test_risk_expansion_requires_exactly_three_segments(self) -> None:
        for value in ("small; direct module only", "small; direct module only; none; extra"):
            with self.subTest(value=value):
                text = self._valid_manifest().replace(
                    "small; direct module only; no expansion", value,
                )
                metadata, _ = _parse_metadata(text)
                text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
                self.path.write_text(text, encoding="utf-8")
                self.assertIn("invalid-risk-expansion", self.codes())

    def test_template_mode_rejects_unsafe_run_and_invalid_module_map(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("{{RUN_ID}}", "../escape")
        text = text.replace("{{MODULE_EQUALS_COMMA_SEPARATED_CHANGED_FILES_SEMICOLON_DELIMITED}}", "garbage")
        self.path.write_text(text, encoding="utf-8")
        codes = {item.code for item in validate_context_manifest(self.path, project_root=self.root, template=True)}
        self.assertTrue({"invalid-run-id", "invalid-module-changed-files"} <= codes)

    def test_template_mode_rejects_unsafe_baseline_path_and_reuse(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("{{BASELINE_ARTIFACT_PATH}}", "../../outside")
        text = text.replace("{{RERUN_OR_REUSE_RUN_ID}}", "reuse: prior-run")
        self.path.write_text(text, encoding="utf-8")
        codes = {item.code for item in validate_context_manifest(self.path, project_root=self.root, template=True)}
        self.assertTrue({"unsafe-baseline-artifact", "invalid-template-reuse"} <= codes)

    def test_valid_manifest_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_module_changed_files_must_map_every_changed_file(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "Module changed files: module=src/module.py",
            "Module changed files: module=evidence/test.txt",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-module-changed-files", self.codes())

    def test_module_file_map_change_invalidates_cache_key(self) -> None:
        first = {"Requirement IDs": "REQ-001", "Module changed files": "a=src/a.py; b=src/b.py"}
        second = {"Requirement IDs": "REQ-001", "Module changed files": "a=src/b.py; b=src/a.py"}
        self.assertNotEqual(_cache_key(first), _cache_key(second))

    def test_module_file_ownership_rejects_overlap_and_path_aliases(self) -> None:
        (self.root / "src/other.py").write_text("other", encoding="utf-8")
        cases = (
            "module=src/module.py; module2=src/module.py,src/other.py",
            "module=src/module.py; module2=src/./module.py,src/other.py",
        )
        for mapping in cases:
            with self.subTest(mapping=mapping):
                text = self._valid_manifest().replace("- Modules: module", "- Modules: module, module2")
                text = text.replace("- Module changed files: module=src/module.py", f"- Module changed files: {mapping}")
                changed = "src/module.py, src/other.py"
                if "src/./module.py" in mapping:
                    changed = "src/module.py, src/./module.py, src/other.py"
                text = text.replace("- Changed files: src/module.py", f"- Changed files: {changed}")
                metadata, _ = _parse_metadata(text)
                code_hash = _paths_fingerprint(metadata["Changed files"], self.root.resolve(), [], "changed-file")
                text = text.replace(metadata["Code fingerprint"], code_hash)
                metadata["Code fingerprint"] = code_hash
                text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
                self.path.write_text(text, encoding="utf-8")
                self.assertTrue({"ambiguous-module-changed-file", "unsafe-module-changed-file"} & self.codes())
        # Distinct canonical paths can still alias the same physical input.
        os.link(self.root / "src/module.py", self.root / "src/linked.py")
        metadata, _ = _parse_metadata(self._valid_manifest())
        metadata.update({
            "Modules": "module, module2",
            "Changed files": "src/module.py, src/linked.py",
            "Module changed files": "module=src/module.py; module2=src/linked.py",
        })
        from validate_context_manifest import _module_mapping_issues
        self.assertEqual(
            ["ambiguous-module-changed-file"],
            [issue.code for issue in _module_mapping_issues(metadata, self.root.resolve())],
        )

    def test_single_module_rejects_dot_path_alias(self) -> None:
        text = self._valid_manifest().replace("module=src/module.py", "module=./src/module.py")
        text = text.replace("Changed files: src/module.py", "Changed files: ./src/module.py")
        metadata, _ = _parse_metadata(text)
        code_hash = _paths_fingerprint(metadata["Changed files"], self.root.resolve(), [], "changed-file")
        text = text.replace(metadata["Code fingerprint"], code_hash)
        metadata["Code fingerprint"] = code_hash
        text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("unsafe-module-changed-file", self.codes())

    def test_duplicate_module_ids_are_rejected(self) -> None:
        self.path.write_text(
            self.path.read_text(encoding="utf-8").replace("Modules: module", "Modules: module, module"),
            encoding="utf-8",
        )
        self.assertIn("invalid-modules", self.codes())

    def test_duplicate_workset_paths_are_rejected(self) -> None:
        text = self._valid_manifest().replace(
            "Changed files: src/module.py", "Changed files: src/module.py, src/module.py",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("duplicate-workset-path", self.codes())

    def test_public_cache_formula_includes_canonical_module_map(self) -> None:
        text = PUBLIC_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Requirement IDs, canonical module map, risk/expansion reason, direct dependency boundaries", text)

    def test_changed_fingerprint_invalidates_cache(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "- Environment ID: local-test",
            "- Environment ID: changed-environment",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-evidence-cache-key", self.codes())

    def test_changed_code_invalidates_code_fingerprint(self) -> None:
        (self.root / "src/module.py").write_text("changed code", encoding="utf-8")
        self.assertIn("stale-code-fingerprint", self.codes())

    def test_changed_command_invalidates_command_fingerprint(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "- Required commands: python3 -m unittest",
            "- Required commands: python3 -m unittest -v",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-command-fingerprint", self.codes())

    def test_changed_agents_invalidates_agents_fingerprint(self) -> None:
        (self.root / "AGENTS.md").write_text("# Changed project instructions\n", encoding="utf-8")
        self.assertIn("stale-effective-agents-fingerprint", self.codes())

    def test_new_scoped_agents_invalidates_declared_effective_chain(self) -> None:
        (self.root / "src/AGENTS.md").write_text("# Scoped instructions\n", encoding="utf-8")
        self.assertIn("stale-effective-agents-set", self.codes())

    def test_changed_and_deleted_scoped_agents_invalidate_chain(self) -> None:
        scoped = self.root / "src/AGENTS.md"
        scoped.write_text("# Scoped instructions\n", encoding="utf-8")
        self.path.write_text(self._valid_manifest("AGENTS.md, src/AGENTS.md"), encoding="utf-8")
        self.assertEqual(set(), self.codes())
        scoped.write_text("# Changed scoped instructions\n", encoding="utf-8")
        self.assertIn("stale-effective-agents-fingerprint", self.codes())
        self.path.write_text(self._valid_manifest("AGENTS.md, src/AGENTS.md"), encoding="utf-8")
        scoped.unlink()
        self.assertTrue({"missing-agents-file", "stale-effective-agents-set"} & self.codes())

    def test_symlinked_scoped_agents_fails_closed(self) -> None:
        policy = self.root / "policy.md"
        policy.write_text("# Linked policy\n", encoding="utf-8")
        (self.root / "src/AGENTS.md").symlink_to(policy)
        self.assertIn("unsafe-effective-agents-symlink", self.codes())

    def test_symlinked_workset_parent_fails_closed(self) -> None:
        real = self.root / "real"
        real.mkdir()
        (real / "module.py").write_text("linked module", encoding="utf-8")
        (self.root / "linked").symlink_to(real, target_is_directory=True)
        text = self.path.read_text(encoding="utf-8").replace("src/module.py", "linked/module.py")
        from validate_context_manifest import _parse_metadata
        metadata, _ = _parse_metadata(text)
        code_hash = _paths_fingerprint("linked/module.py", self.root.resolve(), [], "changed-file")
        text = text.replace(metadata["Code fingerprint"], code_hash)
        metadata["Code fingerprint"] = code_hash
        text = text.replace(metadata["Evidence cache key"], _cache_key(metadata))
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("unsafe-workset-symlink", self.codes())

    def test_symlinked_workset_leaf_cannot_hide_scoped_agents(self) -> None:
        real = self.root / "real"
        real.mkdir()
        (real / "module.py").write_text("linked module", encoding="utf-8")
        (real / "AGENTS.md").write_text("# Hidden scoped policy\n", encoding="utf-8")
        (self.root / "src/module.py").unlink()
        (self.root / "src/module.py").symlink_to("../real/module.py")
        self.path.write_text(self._valid_manifest(), encoding="utf-8")
        self.assertIn("unsafe-workset-symlink", self.codes())

    def test_reuse_requires_existing_evidence(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("evidence/test.txt", "evidence/missing.txt")
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("missing-reuse-evidence", self.codes())

    def test_reuse_run_must_bind_successful_provenance_record(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "Reuse decision: reuse: prior-run", "Reuse decision: reuse: nonexistent-run",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-reuse-record", self.codes())

    def test_duplicate_field_fails(self) -> None:
        self.path.write_text(
            self.path.read_text(encoding="utf-8") + "\n- Code version: contradictory\n",
            encoding="utf-8",
        )
        self.assertIn("duplicate-field", self.codes())

    def test_requirement_ids_change_invalidates_cache_key(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "Requirement IDs: REQ-001", "Requirement IDs: REQ-999",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("stale-evidence-cache-key", self.codes())

    def test_risk_and_dependency_boundaries_invalidate_cache_key(self) -> None:
        for old, new in (
            ("small; direct module only; no expansion", "high-risk; unknown; cross-module expansion"),
            ("direct callers and tests", "unrelated boundary only"),
        ):
            with self.subTest(new=new):
                self.path.write_text(self._valid_manifest().replace(old, new), encoding="utf-8")
                self.assertIn("stale-evidence-cache-key", self.codes())

    def test_baseline_change_invalidates_cache_key(self) -> None:
        old_key = _cache_key({
            "Baseline artifact": "requirements/baseline.md",
            "Baseline version": "req-v1",
            "Baseline SHA-256": "1" * 64,
        })
        new_key = _cache_key({
            "Baseline artifact": "requirements/baseline.md",
            "Baseline version": "req-v2",
            "Baseline SHA-256": "2" * 64,
        })
        self.assertNotEqual(old_key, new_key)

    def test_run_id_must_be_a_stable_path_segment(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace(
            "Run ID: run-1", "Run ID: x/../../../escaped-run",
        )
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("invalid-run-id", self.codes())

    def test_module_ids_must_be_stable_path_segments(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("Modules: module", "Modules: ..")
        self.path.write_text(text, encoding="utf-8")
        self.assertIn("invalid-modules", self.codes())

    def test_directories_cannot_masquerade_as_hashed_files(self) -> None:
        text = self.path.read_text(encoding="utf-8").replace("requirements/baseline.md", ".").replace("src/module.py", ".")
        self.path.write_text(text, encoding="utf-8")
        self.assertTrue(any(code.startswith("nonfile-") for code in self.codes()))

    def test_modified_reuse_evidence_invalidates_cache(self) -> None:
        (self.root / "evidence/test.txt").write_text("changed evidence", encoding="utf-8")
        self.assertIn("stale-evidence-fingerprint", self.codes())


if __name__ == "__main__":
    unittest.main()
