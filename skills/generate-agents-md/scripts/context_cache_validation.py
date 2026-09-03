from __future__ import annotations

import hashlib
import re


STABLE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _parse_module_file_map(value: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in value.split(";"):
        module, separator, raw_paths = item.strip().partition("=")
        path_items = [path.strip() for path in raw_paths.split(",") if path.strip()]
        paths = set(path_items)
        if not separator or len(path_items) != len(paths) or not STABLE_ID_RE.fullmatch(module) or module in result:
            return {}
        result[module] = paths
    return result


def _canonical_module_file_map(value: str) -> str:
    mapping = _parse_module_file_map(value)
    return ";".join(f'{module}={",".join(sorted(mapping[module]))}' for module in sorted(mapping))


def _cache_key_from_requirement_ids(
    metadata: dict[str, str], requirement_ids: str, cache_scope: tuple[str, ...],
) -> str:
    baseline_artifact, baseline_version, baseline_sha, module_map, risk, dependency, code_version, build_id = cache_scope
    values = (
        baseline_artifact,
        baseline_version,
        baseline_sha.casefold(),
        metadata.get("Authority matrix locator", ""),
        metadata.get("Authority matrix SHA-256", "").casefold(),
        requirement_ids,
        module_map,
        risk,
        dependency,
        code_version,
        build_id,
        metadata.get("Code fingerprint", "").casefold(),
        metadata.get("Command fingerprint", "").casefold(),
        metadata.get("Effective AGENTS fingerprint", "").casefold(),
        metadata.get("Command manifest fingerprint", "").casefold(),
        metadata.get("Configuration fingerprint", "").casefold(),
        metadata.get("Environment ID", ""),
        metadata.get("Input fingerprint", "").casefold(),
        metadata.get("Evidence fingerprint", "").casefold(),
    )
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()
