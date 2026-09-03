#!/usr/bin/env python3
"""Validate one final Kimi -> DeepSeek -> Codex GPT review-loop bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from clarification_validation import validate_clarification_register
from validate_contract import (
    BEHAVIORS,
    load_contract,
    strict_json_loads,
    validate_common,
    validate_kimi,
    validate_review,
)
from spawn_external_agent import has_symlink_component, task_root
from provider_manifest_validation import validate_spawn_manifest


SCOPE_FIELDS = {
    "schema_version", "task_id", "objective", "acceptance_criteria",
    "context_artifacts", "clarification_register", "max_rounds",
}
CRITERION_FIELDS = {"id", "text", "behaviors"}
HISTORY_FIELDS = {"schema_version", "task_id", "max_rounds", "rounds"}
ROUND_FIELDS = {
    "round", "candidate_version", "status", "kimi_path", "kimi_sha256",
    "kimi_manifest_path", "kimi_manifest_sha256", "deepseek_path", "deepseek_sha256",
    "deepseek_manifest_path", "deepseek_manifest_sha256", "gpt_path", "gpt_sha256",
    "gpt_evidence_path", "gpt_evidence_sha256",
}
GPT_EVIDENCE_FIELDS = {
    "schema_version", "task_id", "provider", "role", "run_id", "candidate_version",
    "scope_sha256", "candidate_sha256", "deepseek_review_sha256", "input_manifest_path",
    "input_manifest_sha256", "output_path", "output_sha256",
}
GPT_INPUT_FIELDS = {
    "schema_version", "task_id", "provider", "role", "run_id", "candidate_version",
    "scope_sha256", "artifacts",
}
GPT_CHECK_FIELDS = {
    "schema_version", "task_id", "provider", "role", "run_id", "check_id",
    "candidate_version", "scope_sha256", "candidate_sha256", "deepseek_review_sha256",
    "method", "status", "observations",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--kimi", required=True, type=Path)
    parser.add_argument("--deepseek", required=True, type=Path)
    parser.add_argument("--gpt", required=True, type=Path)
    parser.add_argument("--gpt-evidence", required=True, type=Path)
    parser.add_argument("--kimi-manifest", required=True, type=Path)
    parser.add_argument("--deepseek-manifest", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    return parser.parse_args()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def _nonempty_strings(items: Any, label: str) -> list[str]:
    if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{label} must be a string array")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must not contain duplicates")
    return items


def validate_scope(scope: dict[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
    if set(scope) != SCOPE_FIELDS or type(scope.get("schema_version")) is not int or scope["schema_version"] != 1:
        raise ValueError("scope must use the exact schema_version 1 fields")
    if any(not isinstance(scope.get(name), str) or not scope[name].strip() for name in ("task_id", "objective")):
        raise ValueError("scope task_id and objective must be non-empty strings")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
           for character in scope["task_id"]):
        raise ValueError("scope task_id must be one stable path segment")
    rounds = scope.get("max_rounds")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 6:
        raise ValueError("max_rounds must be an integer from 1 through 6")
    criteria = scope.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("acceptance_criteria must not be empty")
    behaviors: dict[str, set[str]] = {}
    for item in criteria:
        if not isinstance(item, dict) or set(item) != CRITERION_FIELDS:
            raise ValueError("acceptance criteria must use the exact required fields")
        identifier, text = item.get("id"), item.get("text")
        if not isinstance(identifier, str) or not identifier.strip() or not isinstance(text, str) or not text.strip():
            raise ValueError("acceptance criteria IDs and text must be non-empty strings")
        required = set(_nonempty_strings(item.get("behaviors"), f"behaviors for {identifier}"))
        if not required or not required <= BEHAVIORS or identifier in behaviors:
            raise ValueError("criterion behaviors must be unique supported categories")
        behaviors[identifier] = required
    artifacts = scope.get("context_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) > 64:
        raise ValueError("scope context_artifacts must be a bounded array")
    identifiers = []
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"id", "content", "sha256"}:
            raise ValueError("scope context artifacts must use the exact required fields")
        if not isinstance(item["id"], str) or not item["id"].strip() or not isinstance(item["content"], str):
            raise ValueError("scope context artifact ID/content types are invalid")
        if item["sha256"] != hashlib.sha256(item["content"].encode("utf-8")).hexdigest():
            raise ValueError("scope context artifact content hash is stale")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("scope context artifact IDs must be unique")
    criterion_text = {item["id"]: item["text"] for item in criteria}
    register = scope.get("clarification_register")
    validate_clarification_register(register, allow_open=False, criteria=criterion_text)
    if register["resolved_objective"] != scope["objective"]:
        raise ValueError("scope objective differs from the resolved clarification objective")
    return set(behaviors), behaviors


def _validate_versions(scope: dict[str, Any], contracts: list[dict[str, Any]]) -> int:
    versions = {value["candidate_version"] for value in contracts}
    if len(versions) != 1:
        raise ValueError("all reviewers must bind the same candidate version")
    version = versions.pop()
    if version > scope["max_rounds"]:
        raise ValueError("candidate version exceeds max_rounds")
    return version


def _validate_criteria(
    criteria: set[str], behaviors: dict[str, set[str]], kimi: dict[str, Any],
    deepseek: dict[str, Any], require_exact: bool,
) -> None:
    mapped = [item["criterion"] for item in kimi["acceptance_criteria_mapping"]]
    if len(mapped) != len(set(mapped)) or set(mapped) != criteria:
        raise ValueError("Kimi acceptance criteria mapping must exactly cover the scope")
    coverage = deepseek["coverage"]
    if len(coverage) != len(set(coverage)) or not set(coverage) <= criteria:
        raise ValueError("DeepSeek coverage must contain only unique scope criteria")
    actual: dict[str, set[str]] = {identifier: set() for identifier in criteria}
    for case in deepseek["black_box_tests"]:
        if case["requirement"] not in actual:
            raise ValueError("black-box test references an unknown acceptance criterion")
        actual[case["requirement"]].add(case["behavior"])
    if require_exact and (set(coverage) != criteria or any(behaviors[key] != actual[key] for key in criteria)):
        raise ValueError("black-box behavior coverage is incomplete")


def _validate_provenance(
    scope: dict[str, Any], kimi: dict[str, Any], deepseek: dict[str, Any], gpt: dict[str, Any],
) -> None:
    scope_hash = canonical_sha256(scope)
    if any(value["scope_sha256"] != scope_hash for value in (kimi, deepseek, gpt)):
        raise ValueError("review contract is stale for the current scope")
    candidate_hash = canonical_sha256(kimi)
    if deepseek["candidate_sha256"] != candidate_hash or gpt["candidate_sha256"] != candidate_hash:
        raise ValueError("review contract is stale for the current candidate")
    if gpt["deepseek_review_sha256"] != canonical_sha256(deepseek):
        raise ValueError("GPT contract is stale for the current DeepSeek review")


def _validate_adjudication(deepseek: dict[str, Any], gpt: dict[str, Any], require_pass: bool) -> None:
    defect_ids = [item["id"] for item in deepseek["defects"]]
    adjudicated = [item["defect_id"] for item in gpt["deepseek_adjudication"]]
    if len(defect_ids) != len(set(defect_ids)) or len(adjudicated) != len(set(adjudicated)):
        raise ValueError("defect and adjudication IDs must be unique")
    if set(adjudicated) != set(defect_ids):
        raise ValueError("GPT must adjudicate every DeepSeek defect exactly once")
    if require_pass and (deepseek["verdict"] != "pass" or gpt["verdict"] != "pass"):
        raise ValueError("final loop bundle requires both reviewers to pass")


def _sha256_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("spawn result must bind a regular normalized contract file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_history_path(root: Path, raw: Any, digest: Any) -> Path:
    if not isinstance(raw, str) or not raw or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("history artifact path and SHA-256 are invalid")
    path = Path(raw)
    if task_root(path) != root or has_symlink_component(path, root) or _sha256_file(path) != digest:
        raise ValueError("history artifact is missing, unsafe, or stale")
    return path


def _round_paths(root: Path, row: dict[str, Any]) -> dict[str, Path]:
    names = ("kimi", "kimi_manifest", "deepseek", "deepseek_manifest", "gpt", "gpt_evidence")
    return {
        name: _bound_history_path(root, row[f"{name}_path"], row[f"{name}_sha256"])
        for name in names
    }


def _accepted_corrections(gpt: dict[str, Any]) -> set[str]:
    accepted = {
        item["defect_id"] for item in gpt["deepseek_adjudication"]
        if item["decision"] == "accepted"
    }
    accepted.update(item["id"] for item in gpt["additional_defects"])
    return accepted


def _accepted_correction_details(
    deepseek: dict[str, Any], gpt: dict[str, Any],
) -> list[dict[str, Any]]:
    accepted_ids = {
        item["defect_id"] for item in gpt["deepseek_adjudication"]
        if item["decision"] == "accepted"
    }
    details = [
        dict(item) for item in deepseek["defects"]
        if item["id"] in accepted_ids
    ]
    details.extend(dict(item) for item in gpt["additional_defects"])
    return sorted(details, key=lambda item: item["id"])


def _native_identity(value: dict[str, Any], scope: dict[str, Any], gpt: dict[str, Any]) -> tuple[str, str]:
    expected_task = f"{scope['task_id']}-v{gpt['candidate_version']}-gpt"
    if value.get("task_id") != expected_task or value.get("provider") != "codex-native-agent":
        raise ValueError("GPT evidence must identify the active Codex native provider and task")
    if value.get("role") != "orchestrator-independent-reviewer":
        raise ValueError("GPT evidence role is invalid")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in run_id):
        raise ValueError("GPT evidence run_id must be one stable path segment")
    return expected_task, run_id


def _validate_gpt_check(
    path: Path, expected: dict[str, Any], task: str, run_id: str,
    scope: dict[str, Any], kimi: dict[str, Any], deepseek: dict[str, Any],
) -> None:
    value = strict_json_loads(path.read_text("utf-8"))
    if not isinstance(value, dict) or set(value) != GPT_CHECK_FIELDS:
        raise ValueError("GPT independent check evidence must use the exact schema")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("GPT independent check schema_version must be integer 1")
    if _native_identity(value, scope, {"candidate_version": kimi["candidate_version"]}) != (task, run_id):
        raise ValueError("GPT independent check run identity mismatch")
    bound = {
        "check_id": expected["check_id"], "candidate_version": kimi["candidate_version"],
        "scope_sha256": canonical_sha256(scope), "candidate_sha256": canonical_sha256(kimi),
        "deepseek_review_sha256": canonical_sha256(deepseek), "method": expected["method"],
        "status": expected["status"],
    }
    if any(value.get(key) != wanted for key, wanted in bound.items()):
        raise ValueError("GPT independent check evidence is stale or mismatched")
    _nonempty_strings(value.get("observations"), "GPT independent check observations")


def _validate_gpt_input_artifacts(
    artifacts: object, root: Path, paths: dict[str, Path],
) -> None:
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("GPT input manifest must bind exactly Kimi and DeepSeek artifacts")
    wanted = {"kimi-candidate": paths["kimi"], "deepseek-review": paths["deepseek"]}
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"role", "path", "sha256"} or item.get("role") not in wanted:
            raise ValueError("GPT input artifact uses an invalid role or schema")
        bound = _bound_history_path(root, item.get("path"), item.get("sha256"))
        if bound.resolve() != wanted[item["role"]].resolve() or item["role"] in seen:
            raise ValueError("GPT input artifact path is stale, duplicated, or mismatched")
        seen.add(item["role"])


def validate_native_gpt_evidence(
    evidence_path: Path, paths: dict[str, Path], scope: dict[str, Any],
    kimi: dict[str, Any], deepseek: dict[str, Any], gpt: dict[str, Any],
) -> None:
    value = strict_json_loads(evidence_path.read_text("utf-8"))
    if not isinstance(value, dict) or set(value) != GPT_EVIDENCE_FIELDS:
        raise ValueError("GPT native evidence must use the exact schema")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("GPT native evidence schema_version must be integer 1")
    task, run_id = _native_identity(value, scope, gpt)
    expected = {
        "candidate_version": kimi["candidate_version"], "scope_sha256": canonical_sha256(scope),
        "candidate_sha256": canonical_sha256(kimi),
        "deepseek_review_sha256": canonical_sha256(deepseek),
        "output_sha256": _sha256_file(paths["gpt"]),
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise ValueError("GPT native evidence is stale for the reviewed bundle")
    root = task_root(evidence_path)
    input_path = _bound_history_path(root, value.get("input_manifest_path"), value.get("input_manifest_sha256"))
    output_path = _bound_history_path(root, value.get("output_path"), value.get("output_sha256"))
    if output_path.resolve() != paths["gpt"].resolve():
        raise ValueError("GPT native evidence output does not bind the GPT contract")
    manifest = strict_json_loads(input_path.read_text("utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != GPT_INPUT_FIELDS:
        raise ValueError("GPT input manifest must use the exact schema")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("GPT input manifest schema_version must be integer 1")
    if _native_identity(manifest, scope, gpt) != (task, run_id):
        raise ValueError("GPT input manifest run identity mismatch")
    if manifest.get("candidate_version") != kimi["candidate_version"] or manifest.get("scope_sha256") != canonical_sha256(scope):
        raise ValueError("GPT input manifest is stale for the current scope or candidate")
    _validate_gpt_input_artifacts(manifest.get("artifacts"), root, paths)
    check_paths = []
    for check in gpt["independent_checks"]:
        check_path = _bound_history_path(root, check["evidence_path"], check["evidence_sha256"])
        _validate_gpt_check(check_path, check, task, run_id, scope, kimi, deepseek)
        check_paths.append(check_path)
    role_paths = [path for name, path in paths.items() if name != "gpt_evidence"]
    identities = [(path.stat().st_dev, path.stat().st_ino) for path in [evidence_path, input_path, *check_paths, *role_paths]]
    if len(identities) != len(set(identities)):
        raise ValueError("GPT evidence and external review artifacts must have unique file identities")


def _load_round(
    scope: dict[str, Any], root: Path, row: dict[str, Any], expected_change_ids: set[str],
    expected_correction_details: list[dict[str, Any]],
    previous_candidate: tuple[str, str],
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = _round_paths(root, row)
    kimi = load_contract(paths["kimi"], "kimi")
    deepseek = load_contract(paths["deepseek"], "deepseek")
    gpt = load_contract(paths["gpt"], "gpt")
    validate_bundle(
        scope, kimi, deepseek, gpt, require_pass=row["status"] == "passed",
        expected_change_ids=expected_change_ids,
    )
    validate_native_gpt_evidence(paths["gpt_evidence"], paths, scope, kimi, deepseek, gpt)
    candidate_hash = canonical_sha256(kimi)
    kimi_manifest = strict_json_loads(paths["kimi_manifest"].read_text("utf-8"))
    deepseek_manifest = strict_json_loads(paths["deepseek_manifest"].read_text("utf-8"))
    if not isinstance(kimi_manifest, dict) or not isinstance(deepseek_manifest, dict):
        raise ValueError("history spawn manifests must be JSON objects")
    validate_spawn_manifest(
        kimi_manifest, paths["kimi"], "kimi", scope, kimi, candidate_hash,
        expected_prompt_candidate=previous_candidate,
        expected_corrections=expected_change_ids,
        expected_correction_details=expected_correction_details,
    )
    validate_spawn_manifest(
        deepseek_manifest, paths["deepseek"], "deepseek", scope, deepseek, candidate_hash,
        expected_prompt_candidate=(canonical_json(kimi), candidate_hash),
        expected_corrections=set(), expected_correction_details=[],
    )
    return paths, kimi, deepseek, gpt, kimi_manifest


def validate_history(history: dict[str, Any], history_path: Path, scope: dict[str, Any],
                     final_paths: dict[str, Path], *, allow_revised_tail: bool = False) -> str:
    if set(history) != HISTORY_FIELDS or type(history.get("schema_version")) is not int or history["schema_version"] != 1:
        raise ValueError("history must use the exact schema_version 1 fields")
    if history.get("task_id") != scope["task_id"] or history.get("max_rounds") != scope["max_rounds"]:
        raise ValueError("history task or max_rounds differs from the immutable scope")
    rounds = history.get("rounds")
    if not isinstance(rounds, list) or not rounds or len(rounds) > scope["max_rounds"]:
        raise ValueError("history rounds must be non-empty and within max_rounds")
    root, expected = task_root(history_path), set()
    expected_details: list[dict[str, Any]] = []
    previous_candidate = ("NOT_APPLICABLE", "NOT_APPLICABLE")
    loaded: list[tuple[dict[str, Path], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for index, row in enumerate(rounds, 1):
        if not isinstance(row, dict) or set(row) != ROUND_FIELDS:
            raise ValueError("history round must use the exact required fields")
        if (type(row.get("round")) is not int or row["round"] != index
                or type(row.get("candidate_version")) is not int or row["candidate_version"] != index):
            raise ValueError("history rounds and candidate versions must be continuous from 1")
        if row.get("status") not in {"revised", "passed", "incomplete"}:
            raise ValueError("history round status must be revised, passed, or incomplete")
        item = _load_round(
            scope, root, row, expected, expected_details, previous_candidate,
        )
        if item[1]["candidate_version"] != index:
            raise ValueError("history contract candidate version mismatch")
        loaded.append(item)
        previous_candidate = (canonical_json(item[1]), canonical_sha256(item[1]))
        expected = _accepted_corrections(item[3])
        expected_details = _accepted_correction_details(item[2], item[3])
        if row["status"] == "revised" and not expected:
            raise ValueError("a revised round must have GPT-accepted corrections")
        if row["status"] == "passed" and index != len(rounds):
            raise ValueError("only the final history round may pass")
        if row["status"] == "incomplete" and index != len(rounds):
            raise ValueError("only the final history round may be incomplete")
    final_status = rounds[-1]["status"]
    if final_status == "revised" and allow_revised_tail:
        pass
    elif final_status not in {"passed", "incomplete"}:
        raise ValueError("final history round must pass or be incomplete")
    if final_status == "incomplete":
        last_deepseek, last_gpt = loaded[-1][2], loaded[-1][3]
        if len(rounds) != scope["max_rounds"] or (last_deepseek["verdict"], last_gpt["verdict"]) == ("pass", "pass"):
            raise ValueError("incomplete is valid only at max_rounds with an unresolved reviewer result")
    last_paths = loaded[-1][0]
    if any(last_paths[name].resolve() != final_paths[name].resolve() for name in final_paths):
        raise ValueError("final CLI artifacts do not match the final history round")
    return final_status


def validate_bundle(
    scope: dict[str, Any], kimi: dict[str, Any], deepseek: dict[str, Any], gpt: dict[str, Any],
    *, require_pass: bool = True, expected_change_ids: set[str] | None = None,
) -> None:
    criteria, behaviors = validate_scope(scope)
    for name, value in (("kimi", kimi), ("deepseek", deepseek), ("gpt", gpt)):
        validate_common(value, name)
        validate_kimi(value) if name == "kimi" else validate_review(value, name)
    version = _validate_versions(scope, [kimi, deepseek, gpt])
    raw_change_ids = [item["defect_id"] for item in kimi["change_map"]]
    change_ids = set(raw_change_ids)
    if len(raw_change_ids) != len(change_ids):
        raise ValueError("Kimi change_map defect IDs must be unique")
    if (version == 1 and change_ids) or (expected_change_ids is not None and change_ids != expected_change_ids):
        raise ValueError("Kimi change_map must exactly match accepted revision defects")
    _validate_criteria(criteria, behaviors, kimi, deepseek, require_pass)
    _validate_provenance(scope, kimi, deepseek, gpt)
    _validate_adjudication(deepseek, gpt, require_pass)


def main() -> int:
    args = parse_args()
    try:
        scope = strict_json_loads(args.scope.read_text("utf-8"))
        if not isinstance(scope, dict):
            raise ValueError("scope must be one JSON object")
        kimi = load_contract(args.kimi, "kimi")
        deepseek = load_contract(args.deepseek, "deepseek")
        gpt = load_contract(args.gpt, "gpt")
        history = strict_json_loads(args.history.read_text("utf-8"))
        if not isinstance(history, dict):
            raise ValueError("history must be one JSON object")
        status = validate_history(history, args.history, scope, {
            "kimi": args.kimi,
            "kimi_manifest": args.kimi_manifest,
            "deepseek": args.deepseek,
            "deepseek_manifest": args.deepseek_manifest,
            "gpt": args.gpt,
            "gpt_evidence": args.gpt_evidence,
        })
        print(json.dumps({"valid": True, "status": status}))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "status": "blocked", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
