from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

SUPPORTED_PROVIDER = "ollama_local"
SUPPORTED_MODEL = "qwen3.8:27b-bf16"
SUPPORTED_MODELS = frozenset({SUPPORTED_MODEL, "qwen3.8:27b-q8_0"})
SUPPORTED_EFFORTS = frozenset({"none", "xhigh"})
SUPPORTED_RUNTIME = "local-qwen-codex-exec"
SUPPORTED_ENDPOINT = "http://127.0.0.1:11434/v1/"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,127}")
EVIDENCE_KIND = "local-qwen-invocation-evidence"
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_FIELDS = (
    "schema_version", "evidence_kind", "provider", "requested_model",
    "reported_model", "runtime_kind", "endpoint", "writer_agent_id",
    "writer_run_id", "invocation_id", "source_path", "source_sha256",
)
EFFORT_FIELDS = ("requested_reasoning_effort", "reported_reasoning_effort")

# Same-user coordination record only: NOT OS authentication. The evidence file
# is a hashed runtime metadata artifact written by the local Qwen run.


def _invalid() -> str:
    raise RuntimeError("invalid-writer-identity")


def _closed_object(payload: bytes, error: str) -> dict[str, Any]:
    try:
        def hook(raw: list[tuple[str, Any]]) -> dict[str, Any]:
            seen: set[str] = set()
            for key, _ in raw:
                if key in seen:
                    raise ValueError("duplicate")
                seen.add(key)
            return dict(raw)

        value = json.loads(payload.decode("utf-8"), object_pairs_hook=hook)
    except (ValueError, UnicodeError):
        raise RuntimeError(error)
    if not isinstance(value, dict):
        raise RuntimeError(error)
    return value


def validate_writer_identity(
    root: Path, identity: object, agent_id: str, run_id: str,
) -> dict[str, Any]:
    if not isinstance(identity, dict) or set(identity) not in ({
        "provider", "requested_model", "reported_model", "runtime_kind",
        "endpoint", "writer_agent_id", "writer_run_id",
        "evidence_path", "evidence_sha256",
    }, {
        "policy", "provider", "requested_model", "reported_model", "runtime_kind",
        "endpoint", "writer_agent_id", "writer_run_id",
        "evidence_path", "evidence_sha256",
    }, {
        "provider", "requested_model", "reported_model", "runtime_kind",
        "endpoint", "writer_agent_id", "writer_run_id", *EFFORT_FIELDS,
        "evidence_path", "evidence_sha256",
    }, {
        "policy", "provider", "requested_model", "reported_model", "runtime_kind",
        "endpoint", "writer_agent_id", "writer_run_id", *EFFORT_FIELDS,
        "evidence_path", "evidence_sha256",
    }):
        _invalid()
    requested_effort = identity.get("requested_reasoning_effort", "none")
    reported_effort = identity.get("reported_reasoning_effort", "none")
    requested_model = identity["requested_model"]
    reported_model = identity["reported_model"]
    if any(type(value) is not str for value in (
        requested_model, reported_model, requested_effort, reported_effort,
    )):
        _invalid()
    if (("policy" in identity and identity["policy"] != "local-qwen-writer-v1")
            or identity["provider"] != SUPPORTED_PROVIDER
            or requested_model not in SUPPORTED_MODELS
            or reported_model != requested_model
            or requested_effort not in SUPPORTED_EFFORTS
            or reported_effort != requested_effort
            or identity["runtime_kind"] != SUPPORTED_RUNTIME
            or identity["endpoint"] != SUPPORTED_ENDPOINT
            or identity["writer_agent_id"] != agent_id
            or identity["writer_run_id"] != run_id):
        _invalid()
    return _validate_identity_evidence(root, identity, agent_id, run_id)


def _validate_identity_evidence(root: Path, identity: dict[str, Any],
                                agent_id: str, run_id: str) -> dict[str, Any]:
    evidence, sha = _load_identity_evidence(root, identity)
    requested_model = identity["requested_model"]
    requested_effort = identity.get("requested_reasoning_effort", "none")
    invocation_id, source_path, source_sha256 = _validate_evidence_binding(
        evidence, requested_model, requested_effort, agent_id, run_id,
    )
    _bound_source(
        root, source_path, source_sha256, run_id,
        invocation_id, requested_model, requested_effort,
    )
    return {
        "provider": SUPPORTED_PROVIDER,
        "requested_model": requested_model,
        "reported_model": requested_model,
        "requested_reasoning_effort": requested_effort,
        "reported_reasoning_effort": requested_effort,
        "runtime_kind": SUPPORTED_RUNTIME,
        "endpoint": SUPPORTED_ENDPOINT,
        "writer_agent_id": agent_id,
        "writer_run_id": run_id,
        "evidence_path": str(identity["evidence_path"]),
        "evidence_sha256": sha,
        "invocation_id": invocation_id,
        "source_path": source_path,
        "source_sha256": source_sha256,
    }


def _load_identity_evidence(
    root: Path, identity: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    evidence_relative = identity["evidence_path"]
    if type(evidence_relative) is not str or not evidence_relative:
        _invalid()
    evidence_path = _bound_evidence_path(root, Path(evidence_relative))
    sha = identity["evidence_sha256"]
    if type(sha) is not str or not SHA256_RE.fullmatch(sha):
        _invalid()
    try:
        payload = evidence_path.read_bytes()
    except OSError:
        _invalid()
    if hashlib.sha256(payload).hexdigest() != sha:
        raise RuntimeError("writer-evidence-hash-mismatch")
    return _closed_object(payload, "invalid-writer-evidence"), sha


def _validate_evidence_binding(
    evidence: dict[str, Any], requested_model: str, requested_effort: str,
    agent_id: str, run_id: str,
) -> tuple[str, object, str]:
    evidence_fields = set(evidence)
    if evidence_fields not in (set(EVIDENCE_FIELDS), set(EVIDENCE_FIELDS) | set(EFFORT_FIELDS)):
        raise RuntimeError("invalid-writer-evidence")
    evidence_requested_effort = evidence.get("requested_reasoning_effort", "none")
    evidence_reported_effort = evidence.get("reported_reasoning_effort", "none")
    if (type(evidence["schema_version"]) is not int
            or evidence["schema_version"] is True
            or evidence["schema_version"] != EVIDENCE_SCHEMA_VERSION
            or evidence["evidence_kind"] != EVIDENCE_KIND
            or evidence["provider"] != SUPPORTED_PROVIDER
            or evidence["requested_model"] != requested_model
            or evidence["reported_model"] != requested_model
            or evidence_requested_effort != requested_effort
            or evidence_reported_effort != requested_effort
            or evidence["runtime_kind"] != SUPPORTED_RUNTIME
            or evidence["endpoint"] != SUPPORTED_ENDPOINT
            or evidence["writer_agent_id"] != agent_id
            or evidence["writer_run_id"] != run_id):
        raise RuntimeError("invalid-writer-evidence")
    if not isinstance(evidence["invocation_id"], str) or not IDENTITY_RE.fullmatch(evidence["invocation_id"]):
        raise RuntimeError("invalid-writer-evidence")
    if not isinstance(evidence["source_sha256"], str) or not SHA256_RE.fullmatch(evidence["source_sha256"]):
        raise RuntimeError("invalid-writer-evidence")
    return evidence["invocation_id"], evidence["source_path"], evidence["source_sha256"]


# Real Codex rollout shape (read-only inspected from
# /Users/kinglone/.codex/sessions/.../rollout-*.jsonl):
#   top-level keys per line: timestamp, ordinal, type, payload
#   session_meta payload: id/session_id (uuid), model_provider, ... (open set)
#   turn_context payload: turn_id (uuid), model, effort ("none"), ... (open set)
#   ordinary event lines (event_msg/response_item/world_state/token_usage_record)
# carry no identity constraints and are tolerated as-is.
SESSION_META_REQUIRED = {"id", "session_id", "model_provider"}
TURN_CONTEXT_REQUIRED = {"turn_id", "model", "effort"}
KNOWN_ROLLOUT_TYPES = {
    "session_meta", "turn_context", "event_msg", "response_item",
    "world_state", "token_usage_record", "compacted",
    "inter_agent_communication_metadata",
}


def _bound_source(root: Path, source_path: Any, source_sha256: str,
                  writer_run_id: str, invocation_id: str,
                  requested_model: str, requested_effort: str) -> str:
    if (type(source_path) is not str or not source_path
            or source_path.startswith("/") or ".." in Path(source_path).parts
            or not Path(source_path).parts):
        raise RuntimeError("invalid-writer-source")
    path = _bound_evidence_path(root, Path(source_path))
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source_sha256:
        raise RuntimeError("writer-source-hash-mismatch")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        raise RuntimeError("invalid-writer-source")
    _validate_source_records(
        text, writer_run_id, invocation_id, requested_model, requested_effort,
    )
    return source_sha256


def _validate_source_records(
    text: str, writer_run_id: str, invocation_id: str,
    requested_model: str, requested_effort: str,
) -> None:
    session_seen = False
    target_seen = False
    seen_turns: dict[str, tuple[object, object]] = {}
    for line in text.splitlines():
        if not line:
            continue
        record = _source_record(line)
        record_type = record.get("type")
        if record_type == "session_meta":
            if session_seen:
                raise RuntimeError("duplicate-writer-source-session")
            session_seen = True
            _validate_source_session(record["payload"], writer_run_id)
        elif record_type == "turn_context":
            if not session_seen:
                raise RuntimeError("invalid-writer-source")
            turn = record["payload"]
            turn_id = _source_turn_id(turn)
            turn_identity = (turn.get("model"), turn.get("effort"))
            previous = seen_turns.get(turn_id)
            if previous is not None and previous != turn_identity:
                raise RuntimeError("writer-source-turn-mismatch")
            seen_turns[turn_id] = turn_identity
            if turn_id == invocation_id:
                if (turn.get("model") != requested_model
                        or turn.get("effort") != requested_effort):
                    raise RuntimeError("writer-source-turn-mismatch")
                target_seen = True
        elif record_type not in KNOWN_ROLLOUT_TYPES:
            raise RuntimeError("invalid-writer-source")
    if not session_seen or not seen_turns or not target_seen:
        raise RuntimeError("invalid-writer-source")


def _source_record(line: str) -> dict[str, Any]:
    try:
        record = json.loads(line, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeError):
        raise RuntimeError("invalid-writer-source")
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        raise RuntimeError("invalid-writer-source")
    return record


def _validate_source_session(meta: dict[str, Any], writer_run_id: str) -> None:
    if not SESSION_META_REQUIRED <= set(meta):
        raise RuntimeError("invalid-writer-source-session")
    if meta["id"] != meta["session_id"]:
        raise RuntimeError("writer-source-session-mismatch")
    if meta["id"] != writer_run_id or meta["model_provider"] != SUPPORTED_PROVIDER:
        raise RuntimeError("writer-source-session-mismatch")


def _source_turn_id(turn: dict[str, Any]) -> str:
    if not TURN_CONTEXT_REQUIRED <= set(turn):
        raise RuntimeError("invalid-writer-source-turn")
    turn_id = turn["turn_id"]
    if not isinstance(turn_id, str) or not IDENTITY_RE.fullmatch(turn_id):
        raise RuntimeError("writer-source-turn-mismatch")
    return turn_id


def _no_duplicate_keys(raw: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in raw:
        if key in seen:
            raise ValueError("duplicate")
        seen.add(key)
    return dict(raw)


def _bound_evidence_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _invalid()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _invalid()
    try:
        stat = os.stat(current, follow_symlinks=False)
    except FileNotFoundError:
        _invalid()
    if not current.is_file() or stat.st_nlink != 1:
        _invalid()
    return current
