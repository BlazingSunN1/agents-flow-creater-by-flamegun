from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


FULL_RECEIPT_SCHEMA_VERSION = 2
INVALID_RECEIPT = object()
_FULL_STATUSES = {"frozen", "running", "pass", "fail"}
_DISTRIBUTION_STATUSES = {"not_requested", "running", "pass", "fail"}


@dataclass(frozen=True)
class VerifiedReceipt:
    payload: dict[str, object]


def candidate_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in {".git", "__pycache__"} for part in relative.parts):
            continue
        if path.name == ".DS_Store" or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
        elif path.is_file():
            payload = path.read_bytes()
        else:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def default_full_receipt_path(root: Path) -> Path:
    state_root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    root_key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return state_root / "agents-flow-creater-by-flamegun" / "full-validation" / f"{root_key}.json"


def validate_receipt_path(path: Path, skill_root: Path) -> None:
    try:
        path.resolve().relative_to(skill_root.resolve())
    except ValueError:
        return
    raise ValueError("full receipt must be outside the candidate skill root")


def read_full_receipt(path: Path) -> object:
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return INVALID_RECEIPT
    if not isinstance(document, dict):
        return INVALID_RECEIPT
    signature = document.pop("integrity_hmac_sha256", None)
    try:
        key = _read_integrity_key(path)
    except OSError:
        return INVALID_RECEIPT
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, _receipt_signature(document, key),
    ):
        return INVALID_RECEIPT
    return VerifiedReceipt(document)


def write_full_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {**payload, "integrity_hmac_sha256": _receipt_signature(
        payload, _load_or_create_integrity_key(path),
    )}
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


@contextmanager
def exclusive_receipt_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def full_execution_action(
    receipt: object,
    candidate_fingerprint: str,
    *,
    distribution: bool,
    skill_root: Path,
    required_full_checks: tuple[str, ...],
) -> str:
    if receipt is None:
        return "blocked"
    if not isinstance(receipt, VerifiedReceipt):
        return "blocked"
    receipt = receipt.payload
    if not _valid_receipt_shape(receipt, skill_root, required_full_checks):
        return "blocked"
    if receipt["candidate_sha256"] != candidate_fingerprint:
        return "blocked"
    if receipt["full_status"] == "frozen":
        return "run-full"
    if receipt["full_status"] != "pass":
        return "blocked"
    if distribution and receipt["distribution_status"] != "pass":
        return "distribution-only"
    if distribution and not _checks_passed(receipt, ("plugin-distribution",)):
        return "blocked"
    return "reuse-full"


def receipt_payload(receipt: object) -> dict[str, object]:
    return dict(receipt.payload) if isinstance(receipt, VerifiedReceipt) else {}


def _integrity_key_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.key")


def _read_integrity_key(path: Path) -> bytes:
    key_path = _integrity_key_path(path)
    key = key_path.read_bytes()
    if len(key) != 32 or key_path.stat().st_mode & 0o077:
        raise OSError("invalid full-receipt integrity key")
    return key


def _load_or_create_integrity_key(path: Path) -> bytes:
    key_path = _integrity_key_path(path)
    try:
        descriptor = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _read_integrity_key(path)
    key = secrets.token_bytes(32)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key)
        stream.flush()
        os.fsync(stream.fileno())
    return key


def _receipt_signature(payload: dict[str, object], key: bytes) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _valid_receipt_shape(
    receipt: object, skill_root: Path, required_full_checks: tuple[str, ...],
) -> bool:
    if not isinstance(receipt, dict):
        return False
    if receipt.get("schema_version") != FULL_RECEIPT_SCHEMA_VERSION:
        return False
    if receipt.get("skill_root") != str(skill_root.resolve()):
        return False
    fingerprint = receipt.get("candidate_sha256")
    if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
        return False
    if receipt.get("full_status") not in _FULL_STATUSES:
        return False
    if not isinstance(receipt.get("frozen_at"), str) or not receipt["frozen_at"].strip():
        return False
    if receipt.get("distribution_status") not in _DISTRIBUTION_STATUSES:
        return False
    if receipt["full_status"] == "pass" and not _checks_passed(receipt, required_full_checks):
        return False
    return True


def _checks_passed(receipt: dict[str, object], required: tuple[str, ...]) -> bool:
    checks = receipt.get("checks")
    if not isinstance(checks, list):
        return False
    passed: dict[str, int] = {}
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return False
        name, returncode = item["name"], item.get("returncode")
        if name in passed or not isinstance(returncode, int):
            return False
        passed[name] = returncode
    return all(passed.get(name) == 0 for name in required)
