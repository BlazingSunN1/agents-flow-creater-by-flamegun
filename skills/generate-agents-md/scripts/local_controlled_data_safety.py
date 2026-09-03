from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from local_controlled_path_safety import LocalControlledTrustError


class ReplayGuard(Protocol):
    @property
    def state_path(self) -> Path:
        ...

    def consume(self, receipt_id: str, nonce: str, expires_at: datetime) -> bool:
        ...


class InMemoryReplayGuard:
    """Process-local test guard; never substitutes for durable authorization state."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._receipt_ids: set[str] = set()
        self._nonces: set[str] = set()

    @property
    def state_path(self) -> Path:
        return self._state_path

    def consume(self, receipt_id: str, nonce: str, expires_at: datetime) -> bool:
        if receipt_id in self._receipt_ids or nonce in self._nonces:
            return False
        self._receipt_ids.add(receipt_id)
        self._nonces.add(nonce)
        return True


def canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def parse_utc(value: str, code: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise LocalControlledTrustError(code) from error


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LocalControlledTrustError(code)
