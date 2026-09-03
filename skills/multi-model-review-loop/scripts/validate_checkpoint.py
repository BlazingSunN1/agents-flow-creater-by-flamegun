#!/usr/bin/env python3
"""Validate an atomic resumable checkpoint inside one review-loop round."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from provider_manifest_validation import validate_spawn_manifest
from spawn_external_agent import has_symlink_component, task_root
from validate_contract import load_contract, strict_json_loads, validate_common, validate_kimi, validate_review
from validate_loop_bundle import (
    _accepted_correction_details,
    _accepted_corrections,
    _round_paths,
    _validate_criteria,
    canonical_json,
    canonical_sha256,
    validate_bundle,
    validate_history,
    validate_native_gpt_evidence,
    validate_scope,
)


CHECKPOINT_FIELDS = {
    "schema_version", "task_id", "round", "candidate_version", "stage",
    "scope_path", "scope_file_sha256", "history_path", "history_sha256",
    "artifacts", "next_action",
}
ARTIFACT_FIELDS = {"role", "path", "sha256"}
STAGE_ROLES = {
    "scope": (),
    "kimi": ("kimi", "kimi-manifest"),
    "deepseek": ("kimi", "kimi-manifest", "deepseek", "deepseek-manifest"),
    "gpt": ("kimi", "kimi-manifest", "deepseek", "deepseek-manifest", "gpt", "gpt-evidence"),
}
NEXT_ACTIONS = {
    "scope": "run-kimi", "kimi": "run-deepseek",
    "deepseek": "run-gpt", "gpt": "record-history",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    return parser.parse_args()


def _bound_file(root: Path, raw: Any, digest: Any, label: str) -> Path:
    return _bound_payload(root, raw, digest, label)[0]


def _bound_payload(root: Path, raw: Any, digest: Any, label: str) -> tuple[Path, bytes]:
    if not isinstance(raw, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} path or SHA-256 is invalid")
    path = Path(raw)
    if task_root(path) != root or has_symlink_component(path, root) or not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError(f"{label} is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
    finally:
        os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} is stale")
    return path, payload


def _checkpoint_identity(value: dict[str, Any]) -> tuple[str, int, str]:
    if set(value) != CHECKPOINT_FIELDS or type(value.get("schema_version")) is not int \
            or value["schema_version"] != 1:
        raise ValueError("checkpoint must use the exact schema_version 1 fields")
    stage = value.get("stage")
    round_number = value.get("round")
    if stage not in STAGE_ROLES or value.get("next_action") != NEXT_ACTIONS.get(stage):
        raise ValueError("checkpoint stage or next_action is invalid")
    if type(round_number) is not int or type(value.get("candidate_version")) is not int \
            or round_number < 1 or value["candidate_version"] != round_number:
        raise ValueError("checkpoint round and candidate_version must be equal positive integers")
    task_id = value.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("checkpoint task_id must be a non-empty string")
    return stage, round_number, task_id


def _artifact_paths(value: dict[str, Any], root: Path, stage: str) -> dict[str, Path]:
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("checkpoint artifacts must be an array")
    expected = STAGE_ROLES[stage]
    if len(artifacts) != len(expected):
        raise ValueError("checkpoint artifacts do not exactly match the completed stage")
    paths: dict[str, Path] = {}
    for item, role in zip(artifacts, expected):
        if not isinstance(item, dict) or set(item) != ARTIFACT_FIELDS or item.get("role") != role:
            raise ValueError("checkpoint artifact role or schema is invalid")
        paths[role.replace("-", "_")] = _bound_file(root, item.get("path"), item.get("sha256"), role)
    return paths


def _previous_round(
    value: dict[str, Any], root: Path, scope: dict[str, Any], round_number: int,
) -> tuple[set[str], list[dict[str, Any]], tuple[str, str]]:
    if round_number == 1:
        if value.get("history_path") != "NOT_APPLICABLE" or value.get("history_sha256") != "NOT_APPLICABLE":
            raise ValueError("round one checkpoint history must be NOT_APPLICABLE")
        return set(), [], ("NOT_APPLICABLE", "NOT_APPLICABLE")
    history_path, history_payload = _bound_payload(
        root, value.get("history_path"), value.get("history_sha256"), "history",
    )
    history = strict_json_loads(history_payload.decode("utf-8"))
    if not isinstance(history, dict) or not isinstance(history.get("rounds"), list) \
            or len(history["rounds"]) != round_number - 1:
        raise ValueError("checkpoint history must end at the immediately preceding round")
    row = history["rounds"][-1]
    if not isinstance(row, dict):
        raise ValueError("checkpoint prior history row is invalid")
    paths = _round_paths(root, row)
    validate_history(history, history_path, scope, paths, allow_revised_tail=True)
    if row.get("status") != "revised":
        raise ValueError("a continued round requires a revised prior history row")
    kimi = load_contract(paths["kimi"], "kimi")
    deepseek = load_contract(paths["deepseek"], "deepseek")
    gpt = load_contract(paths["gpt"], "gpt")
    return (
        _accepted_corrections(gpt), _accepted_correction_details(deepseek, gpt),
        (canonical_json(kimi), canonical_sha256(kimi)),
    )


def _validate_kimi_stage(
    paths: dict[str, Path], scope: dict[str, Any], version: int,
    corrections: set[str], details: list[dict[str, Any]], previous: tuple[str, str],
) -> dict[str, Any]:
    kimi = load_contract(paths["kimi"], "kimi")
    validate_common(kimi, "kimi")
    validate_kimi(kimi)
    if kimi["candidate_version"] != version or kimi["scope_sha256"] != canonical_sha256(scope):
        raise ValueError("Kimi checkpoint is stale for the current scope or round")
    change_ids = [item["defect_id"] for item in kimi["change_map"]]
    if len(change_ids) != len(set(change_ids)) or set(change_ids) != corrections:
        raise ValueError("Kimi checkpoint change_map differs from prior accepted corrections")
    manifest = strict_json_loads(paths["kimi_manifest"].read_text("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Kimi checkpoint manifest must be one JSON object")
    validate_spawn_manifest(
        manifest, paths["kimi"], "kimi", scope, kimi, canonical_sha256(kimi),
        expected_prompt_candidate=previous, expected_corrections=corrections,
        expected_correction_details=details,
    )
    return kimi


def _validate_deepseek_stage(
    paths: dict[str, Path], scope: dict[str, Any], criteria: set[str],
    behaviors: dict[str, set[str]], kimi: dict[str, Any], version: int,
) -> dict[str, Any]:
    deepseek = load_contract(paths["deepseek"], "deepseek")
    validate_common(deepseek, "deepseek")
    validate_review(deepseek, "deepseek")
    if deepseek["candidate_version"] != version or deepseek["scope_sha256"] != canonical_sha256(scope) \
            or deepseek["candidate_sha256"] != canonical_sha256(kimi):
        raise ValueError("DeepSeek checkpoint is stale for the current scope, candidate, or round")
    _validate_criteria(criteria, behaviors, kimi, deepseek, False)
    manifest = strict_json_loads(paths["deepseek_manifest"].read_text("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("DeepSeek checkpoint manifest must be one JSON object")
    validate_spawn_manifest(
        manifest, paths["deepseek"], "deepseek", scope, deepseek, canonical_sha256(kimi),
        expected_prompt_candidate=(canonical_json(kimi), canonical_sha256(kimi)),
        expected_corrections=set(), expected_correction_details=[],
    )
    return deepseek


def _validate_gpt_stage(
    paths: dict[str, Path], scope: dict[str, Any], kimi: dict[str, Any],
    deepseek: dict[str, Any], corrections: set[str],
) -> None:
    gpt = load_contract(paths["gpt"], "gpt")
    validate_bundle(
        scope, kimi, deepseek, gpt, require_pass=False,
        expected_change_ids=corrections,
    )
    final_paths = {
        "kimi": paths["kimi"], "kimi_manifest": paths["kimi_manifest"],
        "deepseek": paths["deepseek"], "deepseek_manifest": paths["deepseek_manifest"],
        "gpt": paths["gpt"], "gpt_evidence": paths["gpt_evidence"],
    }
    validate_native_gpt_evidence(paths["gpt_evidence"], final_paths, scope, kimi, deepseek, gpt)


def _recheck_files(value: dict[str, Any], root: Path) -> None:
    _bound_file(root, value.get("scope_path"), value.get("scope_file_sha256"), "scope")
    if value.get("history_path") != "NOT_APPLICABLE":
        _bound_file(root, value.get("history_path"), value.get("history_sha256"), "history")
    for item in value["artifacts"]:
        _bound_file(root, item.get("path"), item.get("sha256"), item.get("role", "artifact"))


def validate_checkpoint(value: dict[str, Any], checkpoint_path: Path) -> str:
    stage, round_number, task_id = _checkpoint_identity(value)
    root = task_root(checkpoint_path)
    if checkpoint_path.is_symlink() or has_symlink_component(checkpoint_path, root):
        raise ValueError("checkpoint path is unsafe")
    on_disk = strict_json_loads(checkpoint_path.read_text("utf-8"))
    if on_disk != value:
        raise ValueError("checkpoint content is stale")
    scope_path, scope_payload = _bound_payload(
        root, value.get("scope_path"), value.get("scope_file_sha256"), "scope",
    )
    scope = strict_json_loads(scope_payload.decode("utf-8"))
    if not isinstance(scope, dict):
        raise ValueError("checkpoint scope must be one JSON object")
    criteria, behaviors = validate_scope(scope)
    if scope["task_id"] != task_id or round_number > scope["max_rounds"]:
        raise ValueError("checkpoint task or round differs from the immutable scope")
    corrections, details, previous = _previous_round(value, root, scope, round_number)
    paths = _artifact_paths(value, root, stage)
    if stage != "scope":
        kimi = _validate_kimi_stage(paths, scope, round_number, corrections, details, previous)
        if stage != "kimi":
            deepseek = _validate_deepseek_stage(paths, scope, criteria, behaviors, kimi, round_number)
            if stage == "gpt":
                _validate_gpt_stage(paths, scope, kimi, deepseek, corrections)
    _recheck_files(value, root)
    return stage


def main() -> int:
    args = parse_args()
    try:
        value = strict_json_loads(args.checkpoint.read_text("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("checkpoint must be one JSON object")
        stage = validate_checkpoint(value, args.checkpoint)
        print(json.dumps({"valid": True, "stage": stage, "next_action": value["next_action"]}))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "status": "blocked", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
