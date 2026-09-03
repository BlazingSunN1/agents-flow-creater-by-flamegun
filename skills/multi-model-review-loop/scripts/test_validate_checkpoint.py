from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_validate_loop_bundle import LoopBundleTests, valid_bundle
from validate_checkpoint import _bound_payload, validate_checkpoint
from validate_loop_bundle import validate_scope


write_round_files = LoopBundleTests.write_round_files
history_row = LoopBundleTests.history_row
del LoopBundleTests


class CheckpointValidatorTests(unittest.TestCase):
    def fixture(self) -> tuple[Path, dict[str, object], dict[str, Path], tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp")
        root = Path(temporary.name)
        scope, kimi, deepseek, gpt = valid_bundle()
        scope_path = root / "scope.json"
        scope_path.write_text(json.dumps(scope), encoding="utf-8")
        files = write_round_files(root, scope, kimi, deepseek, gpt)
        files["scope"] = scope_path
        return root, scope, files, temporary

    @staticmethod
    def checkpoint(root: Path, scope: dict[str, object], files: dict[str, Path], stage: str) -> dict[str, object]:
        roles = ["kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence"]
        counts = {"scope": 0, "kimi": 2, "deepseek": 4, "gpt": 6}
        artifacts = [{
            "role": role.replace("_", "-"), "path": str(files[role]),
            "sha256": hashlib.sha256(files[role].read_bytes()).hexdigest(),
        } for role in roles[:counts[stage]]]
        return {
            "schema_version": 1, "task_id": scope["task_id"], "round": 1,
            "candidate_version": 1, "stage": stage,
            "scope_path": str(files["scope"]),
            "scope_file_sha256": hashlib.sha256(files["scope"].read_bytes()).hexdigest(),
            "history_path": "NOT_APPLICABLE", "history_sha256": "NOT_APPLICABLE",
            "artifacts": artifacts,
            "next_action": {"scope": "run-kimi", "kimi": "run-deepseek",
                            "deepseek": "run-gpt", "gpt": "record-history"}[stage],
        }

    def test_each_partial_round_stage_is_machine_validated(self) -> None:
        root, scope, files, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        for stage in ("scope", "kimi", "deepseek", "gpt"):
            with self.subTest(stage=stage):
                value = self.checkpoint(root, scope, files, stage)
                path = root / f"checkpoint-{stage}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(stage, validate_checkpoint(value, path))

    def test_checkpoint_rejects_stale_or_missing_artifacts(self) -> None:
        root, scope, files, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        value = self.checkpoint(root, scope, files, "kimi")
        path = root / "checkpoint.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        value["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_checkpoint(value, path)

    def test_checkpoint_rechecks_files_after_semantic_validation(self) -> None:
        root, scope, files, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        value = self.checkpoint(root, scope, files, "scope")
        checkpoint = root / "checkpoint.json"
        checkpoint.write_text(json.dumps(value), encoding="utf-8")
        replaced = False

        def replace_after_scope_snapshot(root_path, raw, digest, label):
            nonlocal replaced
            result = _bound_payload(root_path, raw, digest, label)
            if label == "scope" and not replaced:
                replaced = True
                changed = json.loads(result[1].decode("utf-8"))
                changed["objective"] = "Atomically replaced after the first hash check."
                files["scope"].write_text(json.dumps(changed), encoding="utf-8")
            return result

        with patch("validate_checkpoint._bound_payload", side_effect=replace_after_scope_snapshot), \
                self.assertRaisesRegex(ValueError, "stale"):
            validate_checkpoint(value, checkpoint)

    def test_scope_task_id_must_be_a_stable_segment(self) -> None:
        _, scope, _, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        scope["task_id"] = "team/task"
        with self.assertRaisesRegex(ValueError, "stable path segment"):
            validate_scope(scope)

    def test_next_round_checkpoint_binds_validated_revised_history(self) -> None:
        root, scope, files, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        scope["max_rounds"] = 2
        scope_hash = hashlib.sha256(json.dumps(
            scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        files["scope"].write_text(json.dumps(scope), encoding="utf-8")
        kimi = json.loads(files["kimi"].read_text(encoding="utf-8"))
        deepseek = json.loads(files["deepseek"].read_text(encoding="utf-8"))
        gpt = json.loads(files["gpt"].read_text(encoding="utf-8"))
        kimi["scope_sha256"] = deepseek["scope_sha256"] = gpt["scope_sha256"] = scope_hash
        deepseek["verdict"] = "fail"
        deepseek["defects"] = [{
            "id": "D-001", "severity": "P1", "criterion": "AC-001", "location": "candidate",
            "evidence": "The boundary is missing.", "impact": "Acceptance is blocked.",
            "correction": "Add the boundary.", "verification": "Run BB-001.",
        }]
        deepseek["candidate_sha256"] = gpt["candidate_sha256"] = hashlib.sha256(json.dumps(
            kimi, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        gpt["verdict"] = "fail"
        gpt["deepseek_adjudication"] = [{
            "defect_id": "D-001", "decision": "accepted", "reason": "Evidence confirms it.",
        }]
        gpt["deepseek_review_sha256"] = hashlib.sha256(json.dumps(
            deepseek, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        files = write_round_files(root, scope, kimi, deepseek, gpt)
        files["scope"] = root / "scope.json"
        history = {"schema_version": 1, "task_id": "task-1", "max_rounds": 2,
                   "rounds": [history_row(1, files)]}
        history["rounds"][0]["status"] = "revised"
        history_path = root / "history.json"
        history_path.write_text(json.dumps(history), encoding="utf-8")
        value = self.checkpoint(root, scope, files, "scope")
        value.update({
            "round": 2, "candidate_version": 2,
            "history_path": str(history_path),
            "history_sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
        })
        checkpoint = root / "checkpoint-round-2.json"
        checkpoint.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual("scope", validate_checkpoint(value, checkpoint))


if __name__ == "__main__":
    unittest.main()
