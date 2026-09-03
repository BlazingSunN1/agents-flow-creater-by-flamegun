from __future__ import annotations


def normalized_project_path(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value != raw or "\\" in value or value.startswith("/") or value.endswith("/") or "//" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    canonical = "/".join(parts)
    return canonical if value == canonical else None
