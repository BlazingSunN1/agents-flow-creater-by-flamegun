from __future__ import annotations

import json


def loads(text: str) -> object:
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
