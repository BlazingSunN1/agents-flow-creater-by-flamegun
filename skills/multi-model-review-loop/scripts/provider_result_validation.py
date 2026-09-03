"""Validate raw provider response identity and immutable execution settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from validate_contract import PROVIDER_WRAPPER_FIELDS, strict_json_loads


def validate_raw_result(
    args: Any, raw: Path, normalized: dict[str, object],
    raw_snapshot: tuple[bytes, tuple[int, int]] | None,
    snapshot_reader: Callable[[Path], tuple[bytes, tuple[int, int]]],
    usage_validator: Callable[[object], None],
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    raw_payload, raw_identity = raw_snapshot or snapshot_reader(raw)
    wrapper = strict_json_loads(raw_payload.decode("utf-8"))
    if not isinstance(wrapper, dict) or set(wrapper) != PROVIDER_WRAPPER_FIELDS:
        raise ValueError("raw provider response wrapper is invalid")
    if wrapper.get("provider") != args.provider or strict_json_loads(wrapper.get("content", "")) != normalized:
        raise ValueError("raw provider response does not produce the normalized contract")
    for field in ("model", "request_model", "response_id"):
        if not isinstance(wrapper.get(field), str) or not wrapper[field].strip():
            raise ValueError(f"raw provider {field} is invalid")
    if args.provider == "deepseek" and wrapper["request_model"] != wrapper["model"]:
        raise ValueError("DeepSeek response model differs from the requested model")
    if wrapper.get("finish_reason") != "stop":
        raise ValueError("raw provider finish_reason must be stop")
    usage_validator(wrapper.get("usage"))
    execution = {
        "transport": "bounded-sse-v1", "idle_timeout_seconds": args.timeout,
        "deadline_seconds": args.deadline, "max_output_tokens": args.max_tokens,
        "retry_limit": args.retries,
    }
    if any(wrapper.get(field) != expected for field, expected in execution.items()):
        raise ValueError("raw provider execution profile differs from the requested resume profile")
    current = raw.stat()
    if raw.is_symlink() or (current.st_dev, current.st_ino) != raw_identity:
        raise ValueError("raw provider response changed identity during validation")
    return wrapper, raw_payload, execution
