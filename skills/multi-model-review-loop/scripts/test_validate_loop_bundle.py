from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_validate_contract import valid_deepseek, valid_kimi
from spawn_external_agent import PROVIDER_REQUEST_PROFILES, SYSTEM_PROMPTS
from validate_loop_bundle import canonical_sha256, validate_bundle, validate_history, validate_spawn_manifest


EXECUTION_PROFILE = {
    "transport": "bounded-sse-v1", "idle_timeout_seconds": 180.0,
    "deadline_seconds": 1800.0, "max_output_tokens": 32768, "retry_limit": 1,
}


def valid_scope() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": "task-1",
        "objective": "Produce and independently review the complete implementation plan.",
        "acceptance_criteria": [{
            "id": "AC-001",
            "text": "The workflow is complete and independently verified.",
            "behaviors": ["success"],
        }],
        "context_artifacts": [],
        "clarification_register": {
            "schema_version": 1,
            "draft_objective": "Produce and independently review the complete implementation plan.",
            "resolved_objective": "Produce and independently review the complete implementation plan.",
            "no_questions_reason": "The objective and acceptance criterion are already explicit.",
            "questions": [],
        },
        "max_rounds": 6,
    }


def valid_bundle() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    scope = valid_scope()
    kimi = valid_kimi()
    kimi["scope_sha256"] = canonical_sha256(scope)
    deepseek = valid_deepseek()
    deepseek["scope_sha256"] = canonical_sha256(scope)
    deepseek["candidate_sha256"] = canonical_sha256(kimi)
    deepseek["coverage"] = ["AC-001"]
    deepseek["black_box_tests"][0]["requirement"] = "AC-001"
    gpt = {
        "candidate_version": 1,
        "scope_sha256": canonical_sha256(scope),
        "candidate_sha256": canonical_sha256(kimi),
        "deepseek_review_sha256": canonical_sha256(deepseek),
        "verdict": "pass",
        "deepseek_adjudication": [],
        "additional_defects": [],
        "independent_checks": [
            {"check_id": "CHK-001", "method": "candidate-inspection",
             "evidence_path": "/pending/native-check-1.json", "evidence_sha256": "d" * 64,
             "status": "passed"},
            {"check_id": "CHK-002", "method": "deepseek-coverage-review",
             "evidence_path": "/pending/native-check-2.json", "evidence_sha256": "e" * 64,
             "status": "passed"},
        ],
        "blockers": [],
    }
    return scope, kimi, deepseek, gpt


class LoopBundleTests(unittest.TestCase):
    def test_same_candidate_and_complete_coverage_pass(self) -> None:
        validate_bundle(*valid_bundle())

    def test_changed_candidate_invalidates_old_reviews(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        kimi["artifact"] = "A changed complete candidate that was never reviewed."
        with self.assertRaisesRegex(ValueError, "candidate"):
            validate_bundle(scope, kimi, deepseek, gpt)

    def test_criteria_and_behavior_coverage_are_exact(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        scope["acceptance_criteria"][0]["behaviors"] = ["success", "failure"]
        new_scope_hash = canonical_sha256(scope)
        kimi["scope_sha256"] = deepseek["scope_sha256"] = gpt["scope_sha256"] = new_scope_hash
        deepseek["candidate_sha256"] = gpt["candidate_sha256"] = canonical_sha256(kimi)
        gpt["deepseek_review_sha256"] = canonical_sha256(deepseek)
        with self.assertRaisesRegex(ValueError, "behavior"):
            validate_bundle(scope, kimi, deepseek, gpt)

    def test_failed_review_round_can_record_nonexact_behavior_coverage(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        deepseek["black_box_tests"].append({
            "id": "BB-002", "requirement": "AC-001", "behavior": "permission",
            "preconditions": ["review is ready"], "steps": ["inspect permission behavior"],
            "expected": ["extra behavior is reported"], "evidence_required": ["review record"],
        })
        gpt["verdict"] = "fail"
        gpt["additional_defects"] = [{
            "id": "G-001", "severity": "P1", "criterion": "AC-001", "location": "coverage",
            "evidence": "An extra behavior is present.", "impact": "Exact coverage is blocked.",
            "correction": "Remove the extra behavior.", "verification": "Re-run coverage review.",
        }]
        gpt["deepseek_review_sha256"] = canonical_sha256(deepseek)
        validate_bundle(scope, kimi, deepseek, gpt, require_pass=False)
        with self.assertRaisesRegex(ValueError, "coverage"):
            validate_bundle(scope, kimi, deepseek, gpt, require_pass=True)

    def test_revision_change_map_matches_accepted_defects(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        kimi["candidate_version"] = deepseek["candidate_version"] = gpt["candidate_version"] = 2
        kimi["change_map"] = []
        new_scope_hash = canonical_sha256(scope)
        kimi["scope_sha256"] = deepseek["scope_sha256"] = gpt["scope_sha256"] = new_scope_hash
        deepseek["candidate_sha256"] = gpt["candidate_sha256"] = canonical_sha256(kimi)
        gpt["deepseek_review_sha256"] = canonical_sha256(deepseek)
        with self.assertRaisesRegex(ValueError, "change_map"):
            validate_bundle(scope, kimi, deepseek, gpt, expected_change_ids={"D-001"})

    def test_scope_schema_boolean_and_duplicate_change_ids_are_rejected(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        scope["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_bundle(scope, kimi, deepseek, gpt)
        scope, kimi, deepseek, gpt = valid_bundle()
        kimi["candidate_version"] = deepseek["candidate_version"] = gpt["candidate_version"] = 2
        kimi["change_map"] = [{
            "defect_id": "D-001", "change": "fixed", "verification": "NOT_VERIFIED",
        }] * 2
        deepseek["candidate_sha256"] = gpt["candidate_sha256"] = canonical_sha256(kimi)
        gpt["deepseek_review_sha256"] = canonical_sha256(deepseek)
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_bundle(scope, kimi, deepseek, gpt, expected_change_ids={"D-001"})

    def test_history_requires_round_one_and_current_prompt_files(self) -> None:
        from tempfile import TemporaryDirectory

        scope, kimi, deepseek, gpt = valid_bundle()
        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            root = Path(temporary)
            files = self.write_round_files(root, scope, kimi, deepseek, gpt)
            history_path = root / "history.json"
            history = {
                "schema_version": 1, "task_id": "task-1", "max_rounds": 6,
                "rounds": [self.history_row(1, files)],
            }
            history_path.write_text(json.dumps(history), encoding="utf-8")
            final_paths = {name: files[name] for name in (
                "kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence",
            )}
            validate_history(history, history_path, scope, final_paths)
            history["rounds"][0]["round"] = 2
            with self.assertRaisesRegex(ValueError, "continuous"):
                validate_history(history, history_path, scope, final_paths)
            history["rounds"][0]["round"] = 1
            files["kimi_prompt"].write_text("changed after spawn", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                validate_history(history, history_path, scope, final_paths)

    def test_history_requires_raw_provider_and_native_gpt_evidence(self) -> None:
        from tempfile import TemporaryDirectory

        scope, kimi, deepseek, gpt = valid_bundle()
        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            root = Path(temporary)
            files = self.write_round_files(root, scope, kimi, deepseek, gpt)
            history_path = root / "history.json"
            history = {"schema_version": 1, "task_id": "task-1", "max_rounds": 6,
                       "rounds": [self.history_row(1, files)]}
            final = {name: files[name] for name in (
                "kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence",
            )}
            raw_path = Path(json.loads(files["kimi_manifest"].read_text())["raw_path"])
            raw_path.unlink()
            with self.assertRaisesRegex(ValueError, "regular|missing|stale"):
                validate_history(history, history_path, scope, final)
        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            root = Path(temporary)
            files = self.write_round_files(root, scope, kimi, deepseek, gpt)
            history_path = root / "history.json"
            history = {"schema_version": 1, "task_id": "task-1", "max_rounds": 6,
                       "rounds": [self.history_row(1, files)]}
            final = {name: files[name] for name in (
                "kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence",
            )}
            check_path = Path(gpt["independent_checks"][0]["evidence_path"])
            check_path.unlink()
            with self.assertRaisesRegex(ValueError, "regular|missing|stale"):
                validate_history(history, history_path, scope, final)

    def test_max_rounds_can_end_in_machine_validated_incomplete(self) -> None:
        from tempfile import TemporaryDirectory

        scope, kimi, deepseek, gpt = valid_bundle()
        scope["max_rounds"] = 1
        scope_hash = canonical_sha256(scope)
        kimi["scope_sha256"] = deepseek["scope_sha256"] = gpt["scope_sha256"] = scope_hash
        deepseek["verdict"] = "fail"
        deepseek["defects"] = [{
            "id": "D-001", "severity": "P1", "criterion": "AC-001", "location": "candidate",
            "evidence": "The result remains incomplete.", "impact": "Acceptance is blocked.",
            "correction": "Complete AC-001.", "verification": "Repeat BB-001.",
        }]
        deepseek["candidate_sha256"] = gpt["candidate_sha256"] = canonical_sha256(kimi)
        gpt["verdict"] = "fail"
        gpt["deepseek_adjudication"] = [{
            "defect_id": "D-001", "decision": "accepted", "reason": "Evidence confirms the gap.",
        }]
        gpt["deepseek_review_sha256"] = canonical_sha256(deepseek)
        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            root = Path(temporary)
            files = self.write_round_files(root, scope, kimi, deepseek, gpt)
            history_path = root / "history.json"
            history = {"schema_version": 1, "task_id": "task-1", "max_rounds": 1,
                       "rounds": [self.history_row(1, files)]}
            history["rounds"][0]["status"] = "incomplete"
            final = {name: files[name] for name in (
                "kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence",
            )}
            self.assertEqual("incomplete", validate_history(history, history_path, scope, final))

    @staticmethod
    def write_round_files(root: Path, scope: dict[str, object], kimi: dict[str, object], deepseek: dict[str, object], gpt: dict[str, object]) -> dict[str, Path]:
        files = {name: root / f"{name}.json" for name in ("kimi", "deepseek", "gpt")}
        for provider in ("kimi", "deepseek"):
            files[f"{provider}_system"] = root / f"{provider}-system.txt"
            files[f"{provider}_prompt"] = root / f"{provider}-prompt.json"
        files["kimi_system"].write_text(SYSTEM_PROMPTS["kimi"], encoding="utf-8")
        files["deepseek_system"].write_text(SYSTEM_PROMPTS["deepseek"], encoding="utf-8")
        for name, value in (("kimi", kimi), ("deepseek", deepseek)):
            files[name].write_text(json.dumps(value), encoding="utf-8")
        task, run_id = "task-1-v1-gpt", "gpt-run-1"
        gpt["independent_checks"] = []
        for number, method in enumerate(("candidate-inspection", "deepseek-coverage-review"), 1):
            check_path = root / f"gpt-check-{number}.json"
            check = {
                "schema_version": 1, "task_id": task, "provider": "codex-native-agent",
                "role": "orchestrator-independent-reviewer", "run_id": run_id,
                "check_id": f"CHK-00{number}", "candidate_version": 1,
                "scope_sha256": canonical_sha256(scope), "candidate_sha256": canonical_sha256(kimi),
                "deepseek_review_sha256": canonical_sha256(deepseek), "method": method,
                "status": "passed", "observations": [f"{method} completed against AC-001."],
            }
            check_path.write_text(json.dumps(check), encoding="utf-8")
            gpt["independent_checks"].append({
                "check_id": check["check_id"], "method": method, "evidence_path": str(check_path),
                "evidence_sha256": hashlib.sha256(check_path.read_bytes()).hexdigest(), "status": "passed",
            })
        files["gpt"].write_text(json.dumps(gpt), encoding="utf-8")
        for provider, contract in (("kimi", kimi), ("deepseek", deepseek)):
            manifest_path = root / f"{provider}-manifest.json"
            files[f"{provider}_manifest"] = manifest_path
            raw_path = root / f"{provider}-response.json"
            raw_path.write_text(json.dumps({
                "provider": provider, "request_model": f"{provider}-model",
                "model": f"{provider}-model",
                "content": json.dumps(contract), "usage": {"total_tokens": 10},
                "response_id": f"{provider}-response-1", "finish_reason": "stop",
                **EXECUTION_PROFILE,
            }), encoding="utf-8")
            candidate_hash = canonical_sha256(kimi)
            prompt = {
                "schema_version": 1, "task_id": f"task-1-v1-{provider}", "provider": provider,
                "candidate_version": 1, "scope_sha256": contract["scope_sha256"],
                "objective": scope["objective"], "acceptance_criteria": scope["acceptance_criteria"],
                "context_artifacts": scope["context_artifacts"],
                "clarification_register": scope["clarification_register"],
                "candidate": (
                    "NOT_APPLICABLE" if provider == "kimi"
                    else json.dumps(
                        kimi, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
                "candidate_sha256": "NOT_APPLICABLE" if provider == "kimi" else candidate_hash,
                "correction_ids": [], "corrections": [],
            }
            files[f"{provider}_prompt"].write_text(json.dumps(prompt), encoding="utf-8")
            manifest = {
                "schema_version": 1, "task_id": f"task-1-v1-{provider}", "provider": provider,
                "role": "solution-and-revision-author" if provider == "kimi" else "black-box-author-and-defect-reviewer",
                "system_sha256": hashlib.sha256(files[f"{provider}_system"].read_bytes()).hexdigest(),
                "prompt_sha256": hashlib.sha256(files[f"{provider}_prompt"].read_bytes()).hexdigest(),
                "system_path": str(files[f"{provider}_system"]),
                "prompt_path": str(files[f"{provider}_prompt"]),
                "raw_path": str(raw_path),
                "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "model": f"{provider}-model", "response_id": f"{provider}-response-1",
                "usage": {"total_tokens": 10},
                "request_model": f"{provider}-model", "finish_reason": "stop",
                "request_profile": PROVIDER_REQUEST_PROFILES[provider],
                "transport": "bounded-sse-v1", "idle_timeout_seconds": 180.0,
                "deadline_seconds": 1800.0, "max_output_tokens": 32768,
                "retry_limit": 1,
                "candidate_version": 1, "scope_sha256": contract["scope_sha256"],
                "candidate_sha256": candidate_hash, "normalized_path": files[provider].name,
                "normalized_sha256": hashlib.sha256(files[provider].read_bytes()).hexdigest(),
                "verdict": contract.get("verdict", "candidate"),
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        input_path = root / "gpt-input.json"
        input_manifest = {
            "schema_version": 1, "task_id": task, "provider": "codex-native-agent",
            "role": "orchestrator-independent-reviewer", "run_id": run_id,
            "candidate_version": 1, "scope_sha256": canonical_sha256(scope),
            "artifacts": [
                {"role": "kimi-candidate", "path": str(files["kimi"]),
                 "sha256": hashlib.sha256(files["kimi"].read_bytes()).hexdigest()},
                {"role": "deepseek-review", "path": str(files["deepseek"]),
                 "sha256": hashlib.sha256(files["deepseek"].read_bytes()).hexdigest()},
            ],
        }
        input_path.write_text(json.dumps(input_manifest), encoding="utf-8")
        evidence_path = root / "gpt-evidence.json"
        gpt_evidence = {
            "schema_version": 1, "task_id": task, "provider": "codex-native-agent",
            "role": "orchestrator-independent-reviewer", "run_id": run_id,
            "candidate_version": 1, "scope_sha256": canonical_sha256(scope),
            "candidate_sha256": canonical_sha256(kimi),
            "deepseek_review_sha256": canonical_sha256(deepseek),
            "input_manifest_path": str(input_path),
            "input_manifest_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "output_path": str(files["gpt"]),
            "output_sha256": hashlib.sha256(files["gpt"].read_bytes()).hexdigest(),
        }
        evidence_path.write_text(json.dumps(gpt_evidence), encoding="utf-8")
        files["gpt_evidence"] = evidence_path
        return files

    @staticmethod
    def history_row(round_number: int, files: dict[str, Path]) -> dict[str, object]:
        row: dict[str, object] = {"round": round_number, "candidate_version": round_number, "status": "passed"}
        for name in ("kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence"):
            row[f"{name}_path"] = str(files[name])
            row[f"{name}_sha256"] = hashlib.sha256(files[name].read_bytes()).hexdigest()
        return row

    def test_provider_wrapper_cannot_impersonate_kimi(self) -> None:
        from tempfile import TemporaryDirectory
        from validate_contract import load_contract

        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            path = Path(temporary) / "raw.json"
            path.write_text(json.dumps({
                "provider": "deepseek", "request_model": "not-kimi", "model": "not-kimi",
                "content": json.dumps(valid_kimi()), "usage": None, "response_id": None,
                "finish_reason": "stop",
                **EXECUTION_PROFILE,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provider"):
                load_contract(path, "kimi")

    def test_spawn_manifest_binds_task_version_and_normalized_bytes(self) -> None:
        from tempfile import TemporaryDirectory

        scope, kimi, _, _ = valid_bundle()
        with TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp") as temporary:
            normalized = Path(temporary) / "kimi-normalized.json"
            payload = json.dumps(kimi, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            normalized.write_bytes(payload)
            manifest = {
                "schema_version": 1,
                "task_id": "task-1-v1-kimi",
                "provider": "kimi",
                "role": "solution-and-revision-author",
                "system_sha256": "1" * 64,
                "prompt_sha256": "2" * 64,
                "system_path": str(Path(temporary) / "system.txt"),
                "prompt_path": str(Path(temporary) / "prompt.txt"),
                "raw_path": str(Path(temporary) / "raw.json"),
                "raw_sha256": "3" * 64,
                "request_model": "k3", "model": "k3", "response_id": "response-1",
                "finish_reason": "stop", "usage": None,
                "request_profile": PROVIDER_REQUEST_PROFILES["kimi"],
                "transport": "bounded-sse-v1", "idle_timeout_seconds": 180.0,
                "deadline_seconds": 1800.0, "max_output_tokens": 32768,
                "retry_limit": 1,
                "candidate_version": 1,
                "scope_sha256": kimi["scope_sha256"],
                "candidate_sha256": canonical_sha256(kimi),
                "normalized_path": normalized.name,
                "normalized_sha256": hashlib.sha256(payload).hexdigest(),
                "verdict": "candidate",
            }
            system_text = SYSTEM_PROMPTS["kimi"]
            prompt_value = {
                "schema_version": 1, "task_id": "task-1-v1-kimi", "provider": "kimi",
                "candidate_version": 1, "scope_sha256": kimi["scope_sha256"],
                "objective": scope["objective"], "acceptance_criteria": scope["acceptance_criteria"],
                "context_artifacts": scope["context_artifacts"],
                "clarification_register": scope["clarification_register"],
                "candidate": "NOT_APPLICABLE", "candidate_sha256": "NOT_APPLICABLE",
                "correction_ids": [], "corrections": [],
            }
            Path(manifest["system_path"]).write_text(system_text, encoding="utf-8")
            Path(manifest["prompt_path"]).write_text(json.dumps(prompt_value), encoding="utf-8")
            Path(manifest["raw_path"]).write_text(json.dumps({
                "provider": "kimi", "request_model": "k3", "model": "k3",
                "content": json.dumps(kimi), "usage": None,
                "response_id": "response-1", "finish_reason": "stop",
                **EXECUTION_PROFILE,
            }), encoding="utf-8")
            manifest["system_sha256"] = hashlib.sha256(system_text.encode()).hexdigest()
            manifest["prompt_sha256"] = hashlib.sha256(Path(manifest["prompt_path"]).read_bytes()).hexdigest()
            manifest["raw_sha256"] = hashlib.sha256(Path(manifest["raw_path"]).read_bytes()).hexdigest()
            validate_spawn_manifest(manifest, normalized, "kimi", scope, kimi, canonical_sha256(kimi))
            manifest["request_profile"] = "legacy-or-unreviewed-profile"
            with self.assertRaisesRegex(ValueError, "request profile"):
                validate_spawn_manifest(manifest, normalized, "kimi", scope, kimi, canonical_sha256(kimi))
            manifest["request_profile"] = PROVIDER_REQUEST_PROFILES["kimi"]
            manifest["task_id"] = "unrelated-v1-kimi"
            with self.assertRaisesRegex(ValueError, "task"):
                validate_spawn_manifest(manifest, normalized, "kimi", scope, kimi, canonical_sha256(kimi))
            manifest["task_id"] = "task-1-v1-kimi"
            manifest["deadline_seconds"] = 0
            with self.assertRaisesRegex(ValueError, "execution profile"):
                validate_spawn_manifest(manifest, normalized, "kimi", scope, kimi, canonical_sha256(kimi))


if __name__ == "__main__":
    unittest.main()
