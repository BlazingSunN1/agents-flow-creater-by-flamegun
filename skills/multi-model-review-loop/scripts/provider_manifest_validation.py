"""Validate immutable external-provider request, response, and contract provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from spawn_external_agent import (
    PROVIDER_REQUEST_PROFILES,
    has_symlink_component,
    task_root,
    validate_external_input_files,
    validate_usage,
)
from validate_contract import PROVIDER_WRAPPER_FIELDS, strict_json_loads


MANIFEST_FIELDS = {
    "schema_version", "task_id", "provider", "role", "system_sha256", "prompt_sha256",
    "system_path", "prompt_path", "raw_path", "raw_sha256", "request_model", "model",
    "response_id", "finish_reason", "usage", "request_profile", "candidate_version",
    "transport", "idle_timeout_seconds", "deadline_seconds", "max_output_tokens",
    "retry_limit", "scope_sha256", "candidate_sha256", "normalized_path",
    "normalized_sha256", "verdict",
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_file(root: Path, raw: Any, digest: Any) -> Path:
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise ValueError("spawn manifest path/hash types are invalid")
    path = Path(raw)
    if task_root(path) != root or has_symlink_component(path, root) or not path.is_file():
        raise ValueError("spawn manifest must bind a regular task-root file")
    if _sha256_file(path) != digest:
        raise ValueError("spawn manifest file hash is stale")
    return path


def _validate_identity(manifest: dict[str, Any], provider: str, scope: dict[str, Any],
                       contract: dict[str, Any], candidate_hash: str) -> None:
    expected_role = "solution-and-revision-author" if provider == "kimi" else "black-box-author-and-defect-reviewer"
    expected_task = f"{scope['task_id']}-v{contract['candidate_version']}-{provider}"
    if manifest.get("provider") != provider or manifest.get("role") != expected_role:
        raise ValueError("spawn result provider or role mismatch")
    if manifest.get("request_profile") != PROVIDER_REQUEST_PROFILES[provider]:
        raise ValueError("spawn result request profile is not the reviewed provider integration")
    if (manifest.get("task_id") != expected_task or type(manifest.get("candidate_version")) is not int
            or manifest["candidate_version"] != contract["candidate_version"]):
        raise ValueError("spawn result task or candidate version mismatch")
    if manifest.get("scope_sha256") != contract["scope_sha256"] or manifest.get("candidate_sha256") != candidate_hash:
        raise ValueError("spawn result scope or candidate hash mismatch")


def _validate_response_fields(manifest: dict[str, Any], provider: str) -> None:
    for field in ("system_sha256", "prompt_sha256", "normalized_sha256", "raw_sha256"):
        raw = manifest.get(field)
        if not isinstance(raw, str) or len(raw) != 64 or any(c not in "0123456789abcdef" for c in raw):
            raise ValueError(f"spawn result {field} must be a lowercase SHA-256")
    for field in ("request_model", "model", "response_id"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"spawn result {field} must be a non-empty string")
    if provider == "deepseek" and manifest["request_model"] != manifest["model"]:
        raise ValueError("DeepSeek spawn response model differs from its request")
    if manifest.get("finish_reason") != "stop":
        raise ValueError("spawn result finish_reason must be stop")
    if manifest.get("transport") != "bounded-sse-v1":
        raise ValueError("spawn result transport is not the reviewed bounded stream")
    idle, deadline = manifest.get("idle_timeout_seconds"), manifest.get("deadline_seconds")
    tokens, retries = manifest.get("max_output_tokens"), manifest.get("retry_limit")
    if type(idle) not in (int, float) or type(deadline) not in (int, float) \
            or not 1 <= idle <= 600 or not idle <= deadline <= 7200:
        raise ValueError("spawn result timeout/deadline execution profile is invalid")
    if type(tokens) is not int or not 1 <= tokens <= 262_144 \
            or type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("spawn result token/retry execution profile is invalid")
    validate_usage(manifest.get("usage"))


def _validate_prompt(manifest: dict[str, Any], provider: str, scope: dict[str, Any],
                     contract: dict[str, Any], root: Path,
                     expected_prompt_candidate: tuple[str, str] | None,
                     expected_corrections: set[str] | None,
                     expected_correction_details: list[dict[str, Any]] | None) -> None:
    system_path = _bound_file(root, manifest.get("system_path"), manifest.get("system_sha256"))
    prompt_path = _bound_file(root, manifest.get("prompt_path"), manifest.get("prompt_sha256"))
    prompt = validate_external_input_files(system_path, prompt_path, provider, manifest["task_id"])
    if prompt["scope_sha256"] != contract["scope_sha256"] or prompt["objective"] != scope["objective"]:
        raise ValueError("spawn prompt is stale for the immutable scope")
    if (prompt["acceptance_criteria"] != scope["acceptance_criteria"]
            or prompt["context_artifacts"] != scope["context_artifacts"]
            or prompt["clarification_register"] != scope["clarification_register"]
            or prompt["candidate_version"] != contract["candidate_version"]):
        raise ValueError("spawn prompt criteria or candidate version mismatch")
    if expected_prompt_candidate and (prompt["candidate"], prompt["candidate_sha256"]) != expected_prompt_candidate:
        raise ValueError("spawn prompt did not contain the expected candidate")
    if expected_corrections is not None and set(prompt["correction_ids"]) != expected_corrections:
        raise ValueError("spawn prompt correction IDs do not match the prior GPT decision")
    if expected_correction_details is not None and prompt["corrections"] != expected_correction_details:
        raise ValueError("spawn prompt correction details do not match the prior GPT decision")


def validate_spawn_manifest(
    manifest: dict[str, Any], path: Path, provider: str, scope: dict[str, Any],
    contract: dict[str, Any], candidate_hash: str,
    *, expected_prompt_candidate: tuple[str, str] | None = None,
    expected_corrections: set[str] | None = None,
    expected_correction_details: list[dict[str, Any]] | None = None,
) -> None:
    if set(manifest) != MANIFEST_FIELDS or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("spawn result manifest must use the exact schema_version 1 fields")
    _validate_identity(manifest, provider, scope, contract, candidate_hash)
    _validate_response_fields(manifest, provider)
    root = task_root(path)
    _validate_prompt(
        manifest, provider, scope, contract, root, expected_prompt_candidate,
        expected_corrections, expected_correction_details,
    )
    if manifest.get("normalized_path") != path.name or manifest["normalized_sha256"] != _sha256_file(path):
        raise ValueError("spawn result is stale for the normalized contract")
    raw_path = _bound_file(root, manifest.get("raw_path"), manifest.get("raw_sha256"))
    wrapper = strict_json_loads(raw_path.read_text("utf-8"))
    if not isinstance(wrapper, dict) or set(wrapper) != PROVIDER_WRAPPER_FIELDS:
        raise ValueError("spawn raw response must use the exact provider wrapper")
    pairs = (("provider", provider), ("request_model", manifest["request_model"]),
             ("model", manifest["model"]), ("finish_reason", manifest["finish_reason"]),
             ("response_id", manifest["response_id"]), ("usage", manifest["usage"]))
    if any(wrapper.get(field) != expected for field, expected in pairs):
        raise ValueError("spawn raw response provenance differs from its manifest")
    execution = ("transport", "idle_timeout_seconds", "deadline_seconds", "max_output_tokens", "retry_limit")
    if any(wrapper.get(field) != manifest.get(field) for field in execution):
        raise ValueError("spawn raw response execution profile differs from its manifest")
    if strict_json_loads(wrapper.get("content", "")) != contract:
        raise ValueError("spawn normalized contract is not derived from the raw provider response")
    if raw_path.stat().st_ino == path.stat().st_ino and raw_path.stat().st_dev == path.stat().st_dev:
        raise ValueError("raw provider response and normalized contract must be distinct files")
    if manifest.get("verdict") != contract.get("verdict", "candidate"):
        raise ValueError("spawn result verdict mismatch")
