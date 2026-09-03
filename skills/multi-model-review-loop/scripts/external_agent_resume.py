"""Resume publication from complete provider bytes without recalling the provider."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from validate_contract import (
    load_contract, strict_json_loads, validate_common, validate_kimi,
    validate_review, write_new_private_file,
)


def _output_paths(root: Path, provider: str) -> tuple[Path, Path, Path]:
    return (
        root / f"{provider}-response.json",
        root / f"{provider}-normalized.json",
        root / f"{provider}-spawn-result.json",
    )


def _validate_normalized(path: Path, provider: str) -> None:
    value = load_contract(path, provider)
    validate_common(value, provider)
    validate_kimi(value) if provider == "kimi" else validate_review(value, provider)


def resume_existing(
    args: Any, validate: list[str], environment: dict[str, str],
    manifest_factory: Callable[[Any, Path, tuple[bytes, tuple[int, int]]], dict[str, object]],
    snapshot_reader: Callable[[Path], tuple[bytes, tuple[int, int]]], skill_root: Path,
) -> Path:
    raw, normalized, manifest = _output_paths(args.output_dir, args.provider)
    if not raw.is_file() or raw.is_symlink():
        raise ValueError("resume requires one complete regular raw response; never recall the provider implicitly")
    raw_snapshot = snapshot_reader(raw)
    if not normalized.exists():
        checked = subprocess.run(
            validate, cwd=skill_root, text=True, capture_output=True,
            check=False, env=environment, timeout=60,
        )
        if checked.returncode:
            raise ValueError(checked.stderr.strip() or "existing raw response contract is invalid")
    if not normalized.is_file() or normalized.is_symlink():
        raise ValueError("resume normalized contract is missing or unsafe")
    _validate_normalized(normalized, args.provider)
    expected = manifest_factory(args, normalized, raw_snapshot)
    if manifest.exists():
        if not manifest.is_file() or manifest.is_symlink() \
                or strict_json_loads(manifest.read_text("utf-8")) != expected:
            raise ValueError("resume manifest is unsafe or stale")
        return manifest
    write_new_private_file(manifest, json.dumps(expected, ensure_ascii=False, indent=2) + "\n")
    return manifest
