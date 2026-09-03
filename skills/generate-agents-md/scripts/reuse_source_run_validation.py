from __future__ import annotations

import hashlib
import re
from pathlib import Path

from delivery_record_io import RECORD_SCHEMAS, _read_record, _record_fields, _validate_record, split_record_paths
from authority_binding_validation import AUTHORITY_MATRIX_LOCATOR
from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256


def valid_reuse_source_run(
    raw_path: str, root: Path, run_id: str, cache_key: object,
    evidence_paths: list[dict[str, str]], metadata: dict[str, str], source: dict[str, object],
) -> bool:
    if not _valid_source_context(source, root, run_id, str(cache_key)):
        return False
    issues = _validate_record(
        raw_path, root, "execution-run", _expected(
            run_id, cache_key, metadata, str(source["context_path"]),
        ),
        tuple(RECORD_SCHEMAS["execution-run"]), {"completed"}, "Remaining risks",
    )
    if issues:
        return False
    _, text = _read_record(raw_path, root, "execution-run")
    fields, _, _, _ = _record_fields(text)
    declared = set(split_record_paths(fields.get("verification evidence", "")))
    return (declared == {item["path"] for item in evidence_paths}
            and _source_scope_matches(fields, metadata))


def _expected(
    run_id: str, cache_key: object, metadata: dict[str, str], source_context_path: str,
) -> dict[str, str]:
    module = metadata["Modules"].strip()
    return {
        "Run ID": run_id,
        "Module": module,
        "Status": "completed",
        "Context cache key": str(cache_key),
        "Code version": metadata["Code version"],
        "Baseline version and SHA-256": f'{metadata["Baseline version"]} / {metadata["Baseline SHA-256"]}',
        "Build ID and acceptance environment": f'{metadata["Build ID"]} / {metadata["Environment ID"]}',
        "Risk level and reason": metadata["Risk / expansion reason"],
        "Context workset manifest and reused evidence fingerprints": f"{source_context_path} / {cache_key}",
    }


def _canonical_csv(value: str) -> str:
    return ", ".join(sorted(item.strip() for item in value.split(",") if item.strip()))


def _module_files(value: str, module: str) -> str:
    for item in value.split(";"):
        name, separator, paths = item.partition("=")
        if separator and name.strip() == module:
            return _canonical_csv(paths)
    return ""


def _source_scope_matches(fields: dict[str, str], metadata: dict[str, str]) -> bool:
    module = metadata["Modules"].strip()
    return (
        _canonical_csv(fields.get("traceability ids", "")) == _canonical_csv(metadata["Requirement IDs"])
        and _canonical_csv(fields.get("changed files", "")) == _module_files(
            metadata["Module changed files"], module,
        )
    )


def _valid_source_context(source: dict[str, object], root: Path, run_id: str, cache_key: str) -> bool:
    raw_path, expected_hash = source.get("context_path"), source.get("context_sha256")
    if type(raw_path) is not str or type(expected_hash) is not str:
        return False
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    declared = root / candidate
    if any((root / Path(*candidate.parts[:depth])).is_symlink() for depth in range(1, len(candidate.parts) + 1)):
        return False
    try:
        payload = declared.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError):
        return False
    if hashlib.sha256(payload).hexdigest() != expected_hash.casefold():
        return False
    raw_lines = [line for line in text.splitlines() if line.strip()]
    if not raw_lines or raw_lines[0] != f"# Context Workset {run_id}":
        return False
    pairs = [re.fullmatch(
        r"- (Run ID|Authority matrix locator|Authority matrix SHA-256|Evidence cache key):\s*(.+)",
        line,
    ) for line in raw_lines[1:]]
    if any(match is None for match in pairs):
        return False
    fields = {match.group(1): match.group(2) for match in pairs if match is not None}
    expected = {
        "Run ID": run_id,
        "Authority matrix locator": AUTHORITY_MATRIX_LOCATOR,
        "Authority matrix SHA-256": AUTHORITY_MATRIX_SHA256,
        "Evidence cache key": cache_key,
    }
    lines = [raw_lines[0], f"declared={len(pairs)}", f"unique={len(fields)}"]
    if len(pairs) != len(fields):
        lines.append("duplicate")
    if not lines or lines[0] != f"# Context Workset {run_id}" or len(lines) != 3:
        return False
    return fields == expected
