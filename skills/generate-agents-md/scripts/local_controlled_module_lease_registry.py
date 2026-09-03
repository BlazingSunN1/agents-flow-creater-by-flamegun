from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from local_controlled_data_safety import canonical_json, parse_utc, require
from local_controlled_file_safety import atomic_replace_text, directory_identity
from local_controlled_path_safety import (
    LocalControlledTrustError,
    canonical_directory,
    open_unique_lock,
    read_bound_regular_file,
    verify_unique_lock,
)
from strict_json import loads as strict_json_loads


ZERO_SHA = "0" * 64
EVENT_FIELDS = (
    "sequence", "event_type", "previous_event_sha256", "event_sha256", "lease_id",
    "receipt_id", "nonce", "project_root", "module_key", "agent_handle", "run_id",
    "target_path", "pre_sha256", "post_sha256", "occurred_at", "expires_at", "complete",
)


class ModuleLeaseRegistry:
    def __init__(self, state_path: Path, project_root: Path) -> None:
        self._root = canonical_directory(project_root, "project-root-mismatch")
        self._state_path = state_path
        self._parent = canonical_directory(state_path.parent, "unsafe-registry-path")
        require(not _within(self._parent, self._root), "unsafe-registry-path")
        self._parent_identity = directory_identity(self._parent)

    def activate(self, payload: dict[str, object], now: datetime) -> dict[str, object]:
        with self._locked() as lock:
            registry = self._read_registry()
            events = registry["events"]
            assert isinstance(events, list)
            self._check_unique_identifiers(events, payload)
            self._check_active_conflicts(events, payload, now)
            event = self._event(payload, events, "activated", "", ZERO_SHA, ZERO_SHA, now)
            events.append(event)
            self._persist(registry, lock)
        return {"status": "active", "complete": True, "lease_id": payload["lease_id"]}

    def require_active(self, payload: dict[str, object], now: datetime) -> None:
        registry = self._read_registry()
        events = registry["events"]
        assert isinstance(events, list)
        matches = [item for item in events if item["event_type"] == "activated"
                   and item["lease_id"] == payload.get("lease_id")]
        require(len(matches) == 1, "lease-not-active")
        item = matches[0]
        for field in (
            "receipt_id", "nonce", "project_root", "module_key", "agent_handle", "run_id",
        ):
            require(item[field] == payload.get(field), "lease-binding-mismatch")
        expires = parse_utc(str(item["expires_at"]), "invalid-lease-registry")
        require(now.astimezone(timezone.utc) < expires, "lease-expired")

    def record_apply(
        self, payload: dict[str, object], target: str, pre_sha: str,
        post_sha: str, now: datetime,
    ) -> None:
        with self._locked() as lock:
            registry = self._read_registry()
            events = registry["events"]
            assert isinstance(events, list)
            self._require_active_events(events, payload, now)
            events.append(self._event(
                payload, events, "applied", target, pre_sha, post_sha, now,
            ))
            self._persist(registry, lock)

    @contextmanager
    def _locked(self) -> Iterator[int]:
        self._verify_parent()
        lock_path = self._state_path.with_name(self._state_path.name + ".lock")
        descriptor = open_unique_lock(lock_path)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            verify_unique_lock(descriptor, lock_path)
            self._verify_parent()
            yield descriptor
            verify_unique_lock(descriptor, lock_path)
            self._verify_parent()
        except OSError as error:
            raise LocalControlledTrustError("registry-lock-failed") from error
        finally:
            os.close(descriptor)

    def _read_registry(self) -> dict[str, object]:
        self._verify_parent()
        try:
            payload, _ = read_bound_regular_file(self._state_path, "unsafe-registry-path")
        except LocalControlledTrustError:
            if not self._state_path.exists() and not self._state_path.is_symlink():
                return self._empty_registry()
            raise
        try:
            value = strict_json_loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise LocalControlledTrustError("invalid-lease-registry") from error
        require(isinstance(value, dict)
                and set(value) == {"schema_version", "registry_type", "registry_path", "events"},
                "invalid-lease-registry")
        require(type(value.get("schema_version")) is int and value.get("schema_version") == 1
                and value.get("registry_type") == "local_controlled_module_write_lease_registry"
                and value.get("registry_path") == str(self._state_path)
                and isinstance(value.get("events"), list), "invalid-lease-registry")
        self._validate_events(value["events"])
        return value

    def _validate_events(self, events: object) -> None:
        require(isinstance(events, list), "invalid-lease-registry")
        previous = ZERO_SHA
        for index, item in enumerate(events, start=1):
            require(isinstance(item, dict) and set(item) == set(EVENT_FIELDS),
                    "invalid-lease-registry")
            require(type(item.get("sequence")) is int and item["sequence"] == index,
                    "invalid-lease-registry")
            require(item.get("previous_event_sha256") == previous,
                    "invalid-lease-registry")
            claimed = item.get("event_sha256")
            unsigned = dict(item)
            unsigned.pop("event_sha256")
            actual = hashlib.sha256(canonical_json(unsigned)).hexdigest()
            require(claimed == actual, "invalid-lease-registry")
            require(item.get("event_type") in {"activated", "applied"}
                    and type(item.get("complete")) is bool, "invalid-lease-registry")
            parse_utc(str(item.get("occurred_at")), "invalid-lease-registry")
            parse_utc(str(item.get("expires_at")), "invalid-lease-registry")
            previous = str(claimed)

    def _check_unique_identifiers(
        self, events: list[object], payload: dict[str, object],
    ) -> None:
        activations = [item for item in events
                       if isinstance(item, dict) and item.get("event_type") == "activated"]
        for field in ("receipt_id", "nonce", "lease_id"):
            require(payload.get(field) not in {item[field] for item in activations},
                    "replayed-receipt")

    def _check_active_conflicts(
        self, events: list[object], payload: dict[str, object], now: datetime,
    ) -> None:
        for item in self._active_activations(events, now):
            same_module = (item["project_root"], item["module_key"]) == (
                payload.get("project_root"), payload.get("module_key"),
            )
            same_identity = (
                item["agent_handle"] == payload.get("agent_handle")
                or item["run_id"] == payload.get("run_id")
            )
            require(not (same_module or same_identity), "active-lease-conflict")

    def _active_activations(
        self, events: list[object], now: datetime,
    ) -> list[dict[str, object]]:
        current = now.astimezone(timezone.utc)
        return [item for item in events if isinstance(item, dict)
                and item.get("event_type") == "activated"
                and parse_utc(str(item.get("expires_at")), "invalid-lease-registry") > current]

    def _require_active_events(
        self, events: list[object], payload: dict[str, object], now: datetime,
    ) -> None:
        matches = [item for item in self._active_activations(events, now)
                   if item.get("lease_id") == payload.get("lease_id")]
        require(len(matches) == 1, "lease-not-active")

    def _event(
        self, payload: dict[str, object], events: list[object], event_type: str,
        target: str, pre_sha: str, post_sha: str, now: datetime,
    ) -> dict[str, object]:
        previous = ZERO_SHA if not events else str(events[-1]["event_sha256"])
        value: dict[str, object] = {
            "sequence": len(events) + 1, "event_type": event_type,
            "previous_event_sha256": previous, "lease_id": payload["lease_id"],
            "receipt_id": payload["receipt_id"], "nonce": payload["nonce"],
            "project_root": payload["project_root"], "module_key": payload["module_key"],
            "agent_handle": payload["agent_handle"], "run_id": payload["run_id"],
            "target_path": target, "pre_sha256": pre_sha, "post_sha256": post_sha,
            "occurred_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": payload["expires_at"], "complete": True,
        }
        value["event_sha256"] = hashlib.sha256(canonical_json(value)).hexdigest()
        return value

    def _persist(self, registry: dict[str, object], lock: int) -> None:
        lock_path = self._state_path.with_name(self._state_path.name + ".lock")
        payload = json.dumps(
            registry, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ) + "\n"

        def verify() -> None:
            self._verify_parent()
            verify_unique_lock(lock, lock_path)

        try:
            atomic_replace_text(
                self._state_path, payload, self._verify_parent,
                self._parent_identity, verify,
            )
        except OSError as error:
            raise LocalControlledTrustError("registry-persistence-failed") from error
        stored, _ = read_bound_regular_file(self._state_path, "unsafe-registry-path")
        require(stored == payload.encode("utf-8"), "registry-persistence-failed")

    def _empty_registry(self) -> dict[str, object]:
        return {"schema_version": 1,
                "registry_type": "local_controlled_module_write_lease_registry",
                "registry_path": str(self._state_path), "events": []}

    def _verify_parent(self) -> None:
        try:
            identity = directory_identity(self._parent)
        except OSError as error:
            raise LocalControlledTrustError("unsafe-registry-path") from error
        require(identity == self._parent_identity, "unsafe-registry-path")


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
