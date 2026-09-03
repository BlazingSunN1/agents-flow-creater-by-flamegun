from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

from local_controlled_data_safety import require
from local_controlled_file_safety import atomic_replace_text, directory_identity
from local_controlled_module_lease_registry import ModuleLeaseRegistry
from local_controlled_path_safety import (
    FileIdentity,
    LocalControlledTrustError,
    canonical_directory,
    read_bound_regular_file,
    read_external_regular_file,
)


AUTHORITY_RE = re.compile(r"^authority_matrix_sha256:\s*([0-9a-f]{64})\s*$", re.MULTILINE)


def apply_module_write(
    payload: dict[str, object], registry_path: Path, target_path: Path,
    replacement_path: Path, action: str, now: datetime,
) -> dict[str, object]:
    root = canonical_directory(Path(str(payload["project_root"])), "project-root-mismatch")
    registry = ModuleLeaseRegistry(registry_path, root)
    registry.require_active(payload, now)
    require(action in payload.get("authorized_actions", []), "action-not-authorized")
    relative, target_record = _authorized_target(payload, root, target_path)
    _verify_project_bindings(payload, root, relative)
    replacement = _read_replacement(replacement_path, root, target_record)
    before, identity = read_bound_regular_file(target_path, "unsafe-module-target-path")
    _verify_target_payload(before, target_record, "pre")
    parent = target_path.parent
    parent_identity = _parent_identity(parent)
    _replace_target(
        target_path, replacement, identity, parent_identity,
        lambda: _verify_project_bindings(payload, root, relative),
    )
    stored, _ = read_bound_regular_file(target_path, "unsafe-module-target-path")
    _verify_target_payload(stored, target_record, "post")
    _verify_project_bindings(payload, root, relative)
    try:
        registry.record_apply(
            payload, relative, str(target_record["pre_sha256"]),
            str(target_record["post_sha256"]), now,
        )
    except LocalControlledTrustError as error:
        return {"status": "PARTIAL", "complete": False, "error": str(error)}
    return {"status": "APPLIED", "complete": True, "target": relative}


def _authorized_target(
    payload: dict[str, object], root: Path, target_path: Path,
) -> tuple[str, dict[str, object]]:
    require(target_path.is_absolute(), "target-not-authorized")
    try:
        relative = str(target_path.relative_to(root))
    except ValueError as error:
        raise LocalControlledTrustError("target-not-authorized") from error
    matches = [item for item in payload.get("targets", [])
               if isinstance(item, dict) and item.get("path") == relative]
    require(len(matches) == 1 and target_path == root / relative, "target-not-authorized")
    return relative, matches[0]


def _verify_project_bindings(
    payload: dict[str, object], root: Path, relative_target: str,
) -> None:
    agents_path = root / "AGENTS.md"
    agents, _ = read_bound_regular_file(agents_path, "unsafe-policy-path")
    require(hashlib.sha256(agents).hexdigest() == payload.get("policy_sha256"),
            "policy-drift")
    try:
        text = agents.decode("utf-8")
    except UnicodeError as error:
        raise LocalControlledTrustError("policy-drift") from error
    match = AUTHORITY_RE.search(text)
    require(match is not None and match.group(1) == payload.get("authority_matrix_sha256"),
            "authority-matrix-drift")
    _verify_ownership(payload, text, relative_target)
    baseline_path = root / str(payload.get("baseline_path"))
    baseline, _ = read_bound_regular_file(baseline_path, "unsafe-baseline-path")
    require(hashlib.sha256(baseline).hexdigest() == payload.get("baseline_sha256"),
            "baseline-drift")


def _verify_ownership(
    payload: dict[str, object], agents_text: str, relative_target: str,
) -> None:
    module = str(payload.get("module_key"))
    title = str(payload.get("stable_title"))
    rows = []
    for line in agents_text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] == module:
            rows.append(cells)
    require(len(rows) == 1 and rows[0][-1] == title, "ownership-drift")
    actual_owned = re.findall(r"`([^`]+)`", rows[0][2])
    expected_owned = payload.get("owned_paths")
    require(isinstance(expected_owned, list) and actual_owned == expected_owned,
            "ownership-drift")
    require(any(
        relative_target == item
        or Path(relative_target).is_relative_to(Path(str(item)))
        for item in expected_owned
    ), "target-not-authorized")


def _read_replacement(
    replacement_path: Path, root: Path, target: dict[str, object],
) -> str:
    _, payload = read_external_regular_file(replacement_path, root, "replacement")
    _verify_target_payload(payload, target, "post")
    try:
        return payload.decode("utf-8")
    except UnicodeError as error:
        raise LocalControlledTrustError("invalid-replacement") from error


def _verify_target_payload(
    payload: bytes, target: dict[str, object], prefix: str,
) -> None:
    require(len(payload) == target.get(f"{prefix}_size")
            and hashlib.sha256(payload).hexdigest() == target.get(f"{prefix}_sha256"),
            f"target-{prefix}-hash-drift")


def _parent_identity(path: Path) -> tuple[int, int]:
    try:
        return directory_identity(path)
    except OSError as error:
        raise LocalControlledTrustError("unsafe-module-target-parent") from error


def _replace_target(
    target_path: Path, replacement: str, expected: FileIdentity,
    parent_identity: tuple[int, int], verify_bindings: object,
) -> None:
    def verify_parent_and_bindings() -> None:
        require(_parent_identity(target_path.parent) == parent_identity,
                "unsafe-module-target-parent")
        verify_bindings()

    def verify_before_replace() -> None:
        verify_parent_and_bindings()
        _, identity = read_bound_regular_file(
            target_path, "unsafe-module-target-path",
        )
        require(identity == expected, "unsafe-module-target-path")

    try:
        atomic_replace_text(
            target_path, replacement, verify_parent_and_bindings,
            parent_identity, verify_before_replace,
        )
    except LocalControlledTrustError:
        raise
    except OSError as error:
        raise LocalControlledTrustError("target-persistence-failed") from error
