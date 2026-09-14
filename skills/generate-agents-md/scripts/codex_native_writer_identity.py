from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


POLICY = "codex-native-sol-writer-v1"
SUPPORTED_PROVIDER = "codex-native-agent"
SUPPORTED_RAW_PROVIDER = "openai"
SUPPORTED_MODEL = "gpt-5.6-sol"
SUPPORTED_EFFORT = "medium"
SUPPORTED_RUNTIME = "codex-rollout-jsonl"
EVIDENCE_KIND = "codex-native-writer-invocation-evidence"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,127}")
IDENTITY_FIELDS = {
    "provider", "requested_model", "recorded_model",
    "requested_reasoning_effort", "recorded_reasoning_effort",
    "runtime_kind", "writer_agent_id", "writer_run_id",
    "evidence_path", "evidence_sha256",
}
EVIDENCE_FIELDS = {
    "schema_version", "evidence_kind", "provider", "raw_model_provider",
    "requested_model", "recorded_model", "requested_reasoning_effort",
    "recorded_reasoning_effort", "runtime_kind", "writer_agent_id",
    "writer_run_id", "invocation_id", "source_agent_path", "source_path",
    "source_sha256", "source_capture",
}
EVIDENCE_V2_FIELDS = EVIDENCE_FIELDS | {"source_parent_thread_id"}
KNOWN_ROLLOUT_TYPES = {
    "session_meta", "turn_context", "event_msg", "response_item",
    "world_state", "token_usage_record", "inter_agent_communication_metadata",
    "compacted",
}


def validate_writer_identity(
    root: Path, identity: object, agent_id: str, run_id: str,
) -> dict[str, Any]:
    if not isinstance(identity, dict) or set(identity) != IDENTITY_FIELDS:
        raise RuntimeError("invalid-writer-identity")
    expected = {
        "provider": SUPPORTED_PROVIDER,
        "requested_model": SUPPORTED_MODEL,
        "recorded_model": SUPPORTED_MODEL,
        "requested_reasoning_effort": SUPPORTED_EFFORT,
        "recorded_reasoning_effort": SUPPORTED_EFFORT,
        "runtime_kind": SUPPORTED_RUNTIME,
        "writer_agent_id": agent_id,
        "writer_run_id": run_id,
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise RuntimeError("invalid-writer-identity")
    return _validate_identity_evidence(root, identity, expected, run_id)


def _validate_identity_evidence(
    root: Path, identity: dict[str, Any], expected: dict[str, Any], run_id: str,
) -> dict[str, Any]:
    evidence, evidence_sha256 = _load_writer_evidence(root, identity)
    (invocation_id, source_agent_path,
     source_parent_thread_id, source_sha256) = _validate_writer_evidence(
        evidence, expected,
    )
    _validate_rollout_source(
        root, evidence.get("source_path"), source_sha256, run_id,
        invocation_id, source_agent_path, source_parent_thread_id,
    )
    return {
        **expected,
        "evidence_path": str(identity["evidence_path"]),
        "evidence_sha256": evidence_sha256,
        "invocation_id": invocation_id,
        "source_agent_path": source_agent_path,
        "source_parent_thread_id": source_parent_thread_id,
        "source_path": evidence["source_path"],
        "source_sha256": source_sha256,
        "raw_model_provider": SUPPORTED_RAW_PROVIDER,
    }


def _load_writer_evidence(
    root: Path, identity: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    evidence_path = _bound_file(root, identity.get("evidence_path"), "writer-evidence")
    evidence_sha256 = identity.get("evidence_sha256")
    if type(evidence_sha256) is not str or not SHA256_RE.fullmatch(evidence_sha256):
        raise RuntimeError("invalid-writer-identity")
    payload = evidence_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != evidence_sha256:
        raise RuntimeError("writer-evidence-hash-mismatch")
    return _closed_json(payload, "invalid-writer-evidence"), evidence_sha256


def _validate_writer_evidence(
    evidence: dict[str, Any], expected: dict[str, Any],
) -> tuple[str, str | None, str | None, str]:
    schema_version = evidence.get("schema_version")
    if (type(schema_version) is not int or schema_version not in (1, 2)
            or set(evidence) != (EVIDENCE_FIELDS if schema_version == 1 else EVIDENCE_V2_FIELDS)):
        raise RuntimeError("invalid-writer-evidence")
    evidence_expected = {
        "evidence_kind": EVIDENCE_KIND,
        **expected,
        "raw_model_provider": SUPPORTED_RAW_PROVIDER,
        "source_capture": "immutable-local-snapshot",
    }
    if any(evidence.get(key) != value for key, value in evidence_expected.items()):
        raise RuntimeError("invalid-writer-evidence")
    invocation_id = evidence.get("invocation_id")
    source_agent_path = evidence.get("source_agent_path")
    source_parent_thread_id = evidence.get("source_parent_thread_id")
    source_sha256 = evidence.get("source_sha256")
    if (type(invocation_id) is not str or not IDENTITY_RE.fullmatch(invocation_id)
            or type(source_sha256) is not str or not SHA256_RE.fullmatch(source_sha256)):
        raise RuntimeError("invalid-writer-evidence")
    if schema_version == 1:
        if type(source_agent_path) is not str or not source_agent_path.startswith("/root/"):
            raise RuntimeError("invalid-writer-evidence")
    elif ((source_agent_path is not None and type(source_agent_path) is not str)
          or type(source_parent_thread_id) is not str
          or not IDENTITY_RE.fullmatch(source_parent_thread_id)):
        raise RuntimeError("invalid-writer-evidence")
    return invocation_id, source_agent_path, source_parent_thread_id, source_sha256


def _validate_rollout_source(
    root: Path, relative: object, expected_sha256: str, writer_run_id: str,
    invocation_id: str, source_agent_path: str | None,
    source_parent_thread_id: str | None,
) -> None:
    path = _bound_file(root, relative, "writer-source")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RuntimeError("writer-source-hash-mismatch")
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise RuntimeError("invalid-writer-source") from error
    _validate_rollout_records(
        text, writer_run_id, invocation_id, source_agent_path, source_parent_thread_id,
    )


def _validate_rollout_records(
    text: str, writer_run_id: str, invocation_id: str,
    source_agent_path: str | None, source_parent_thread_id: str | None,
) -> None:
    session_seen = False
    target_seen = False
    seen_turns: dict[str, tuple[object, object]] = {}
    for line in text.splitlines():
        if not line:
            continue
        record = _rollout_record(line)
        kind = record.get("type")
        if kind == "session_meta":
            if session_seen:
                raise RuntimeError("duplicate-writer-source-session")
            session_seen = True
            _validate_rollout_session(
                record["payload"], writer_run_id,
                source_agent_path, source_parent_thread_id,
            )
        elif kind == "turn_context":
            if not session_seen:
                raise RuntimeError("invalid-writer-source")
            turn = record["payload"]
            turn_id = _rollout_turn_id(turn)
            turn_identity = (turn.get("model"), turn.get("effort"))
            previous = seen_turns.get(turn_id)
            if previous is not None and previous != turn_identity:
                raise RuntimeError("writer-source-turn-mismatch")
            seen_turns[turn_id] = turn_identity
            if turn_id == invocation_id:
                if (turn.get("model") != SUPPORTED_MODEL
                        or turn.get("effort") != SUPPORTED_EFFORT):
                    raise RuntimeError("writer-source-turn-mismatch")
                target_seen = True
        elif kind not in KNOWN_ROLLOUT_TYPES:
            raise RuntimeError("invalid-writer-source")
    if not session_seen or not target_seen:
        raise RuntimeError("invalid-writer-source")


def _rollout_record(line: str) -> dict[str, Any]:
    try:
        record = json.loads(line, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("invalid-writer-source") from error
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        raise RuntimeError("invalid-writer-source")
    return record


def _validate_rollout_session(
    meta: dict[str, Any], writer_run_id: str,
    source_agent_path: str | None, source_parent_thread_id: str | None,
) -> None:
    source = meta.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    thread_spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    nested_path = thread_spawn.get("agent_path") if isinstance(thread_spawn, dict) else None
    nested_parent = thread_spawn.get("parent_thread_id") if isinstance(thread_spawn, dict) else None
    if (meta.get("id") != writer_run_id
            or meta.get("model_provider") != SUPPORTED_RAW_PROVIDER):
        raise RuntimeError("writer-source-session-mismatch")
    if source_parent_thread_id is None:
        if meta.get("agent_path") != source_agent_path or nested_path != source_agent_path:
            raise RuntimeError("writer-source-session-mismatch")
    elif (nested_parent != source_parent_thread_id
          or meta.get("parent_thread_id") not in (None, source_parent_thread_id)
          or meta.get("agent_path") != source_agent_path
          or nested_path != source_agent_path):
        raise RuntimeError("writer-source-session-mismatch")


def _rollout_turn_id(turn: dict[str, Any]) -> str:
    turn_id = turn.get("turn_id")
    if type(turn_id) is not str or not IDENTITY_RE.fullmatch(turn_id):
        raise RuntimeError("writer-source-turn-mismatch")
    return turn_id


def _bound_file(root: Path, relative: object, label: str) -> Path:
    if type(relative) is not str or not relative:
        raise RuntimeError(f"invalid-{label}")
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        raise RuntimeError(f"invalid-{label}")
    current = root
    for part in value.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"unsafe-{label}-path")
    try:
        stat = os.stat(current, follow_symlinks=False)
    except FileNotFoundError as error:
        raise RuntimeError(f"missing-{label}") from error
    if not current.is_file() or stat.st_nlink != 1:
        raise RuntimeError(f"unsafe-{label}-path")
    return current


def _closed_json(payload: bytes, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError(error_code) from error
    if not isinstance(value, dict):
        raise RuntimeError(error_code)
    return value


def _no_duplicate_keys(raw: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in raw:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result
