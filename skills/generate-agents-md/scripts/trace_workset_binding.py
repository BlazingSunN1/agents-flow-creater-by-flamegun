from __future__ import annotations

from pathlib import Path

from traceability_common import LINK_RE, TRACE_COLUMNS
from traceability_parsing import _parse_table
from validate_context_manifest import _parse_module_file_map, _split_paths
from validate_context_manifest import _parse_metadata, _context_deleted_files
from delivery_gate_planner import GatePlanError
from traceability_common import Issue


def trace_deleted_files(context_path: Path | None, root: Path, issues: list[Issue]) -> set[str]:
    if context_path is None:
        return set()
    try:
        context, duplicates = _parse_metadata(context_path.read_text(encoding="utf-8"))
        if duplicates:
            raise GatePlanError("duplicate deletion context fields")
        return _context_deleted_files(context, root)
    except (OSError, UnicodeError, GatePlanError) as error:
        issues.append(Issue("error", "invalid-deleted-files", str(error)))
        return set()


def binding_issue_codes(trace_text: str, context: dict[str, str], root: Path) -> set[str]:
    selected = _selected_rows(trace_text, context)
    changed = _resolved_paths(_split_paths(context.get("Changed files", "")), root)
    code_artifacts = _row_code_paths(selected, root)
    if not changed or not code_artifacts or any(not _covered(path, code_artifacts) for path in changed):
        return {"bundle-requirement-code-mismatch"}
    return set()


def module_requirement_ids(
    trace_text: str, context: dict[str, str], root: Path,
) -> dict[str, str]:
    rows = _selected_rows(trace_text, context)
    selected_ids = _selected_requirement_ids(context)
    row_bindings = [(_row_requirement_ids(row) & selected_ids, _row_code_paths([row], root)) for row in rows]
    result: dict[str, str] = {}
    for module, raw_paths in _parse_module_file_map(context.get("Module changed files", "")).items():
        module_paths = _resolved_paths(raw_paths, root)
        ids = {
            requirement_id
            for requirement_ids, code_paths in row_bindings
            if any(_covered(path, code_paths) for path in module_paths)
            for requirement_id in requirement_ids
        }
        result[module] = ", ".join(sorted(ids))
    return result


def encode_module_requirement_ids(mapping: dict[str, str]) -> str:
    return "; ".join(f"{module}={ids}" for module, ids in sorted(mapping.items()))


def _selected_rows(trace_text: str, context: dict[str, str]) -> list[dict[str, str]]:
    rows, _, _ = _parse_table(trace_text, "Traceability", TRACE_COLUMNS)
    selected = _selected_requirement_ids(context)
    return [row for row in rows or [] if _row_requirement_ids(row) & selected]


def _selected_requirement_ids(context: dict[str, str]) -> set[str]:
    return {item.strip() for item in context.get("Requirement IDs", "").split(",") if item.strip()}


def _row_requirement_ids(row: dict[str, str]) -> set[str]:
    return {identifier for identifier, _ in LINK_RE.findall(row.get("Requirement", ""))}


def _row_code_paths(rows: list[dict[str, str]], root: Path) -> list[Path]:
    raw_paths = [path.strip() for row in rows for _, path in LINK_RE.findall(row.get("Code module", ""))]
    return _resolved_paths(raw_paths, root)


def _resolved_paths(raw_paths: list[str], root: Path) -> list[Path]:
    resolved_root = root.resolve()
    result: list[Path] = []
    for raw in raw_paths:
        candidate = (resolved_root / raw).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        result.append(candidate)
    return result


def _covered(changed: Path, artifacts: list[Path]) -> bool:
    for artifact in artifacts:
        if artifact == changed:
            return True
        if artifact.is_dir():
            try:
                changed.relative_to(artifact)
                return True
            except ValueError:
                pass
    return False
