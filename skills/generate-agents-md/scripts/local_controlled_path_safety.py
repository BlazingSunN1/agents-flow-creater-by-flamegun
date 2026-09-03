from __future__ import annotations

import os
import stat
from pathlib import Path

from local_controlled_file_safety import has_exact_path_spelling


FileIdentity = tuple[int, int]


class LocalControlledTrustError(RuntimeError):
    pass


def canonical_directory(path: Path, code: str) -> Path:
    require(
        path.is_absolute() and is_normalized_path(str(path))
        and has_exact_path_spelling(path),
        code,
    )
    resolved = resolve_strict(path, code)
    try:
        value = os.lstat(path)
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    require(resolved == path and stat.S_ISDIR(value.st_mode), code)
    return resolved


def read_external_regular_file(
    path: Path, root: Path, label: str,
) -> tuple[Path, bytes]:
    code = f"unsafe-{label}-path"
    require(
        path.is_absolute() and is_normalized_path(str(path))
        and has_exact_path_spelling(path),
        code,
    )
    resolved = resolve_strict(path, code)
    require(resolved == path and not is_within(resolved, root), code)
    payload, identity = read_bound_regular_file(path, code)
    require(has_exact_path_spelling(path), code)
    after = resolve_strict(path, code)
    try:
        named = os.lstat(path)
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    require(
        after == path
        and not is_within(after, root)
        and (named.st_dev, named.st_ino) == identity,
        code,
    )
    return path, payload


def read_bound_regular_file(path: Path, code: str) -> tuple[bytes, FileIdentity]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    try:
        before_opened = os.fstat(descriptor)
        before_named = os.lstat(path)
        require(has_exact_path_spelling(path), code)
        require(
            stat.S_ISREG(before_opened.st_mode)
            and stat.S_ISREG(before_named.st_mode)
            and before_opened.st_nlink == 1
            and before_named.st_nlink == 1
            and (before_opened.st_dev, before_opened.st_ino)
            == (before_named.st_dev, before_named.st_ino),
            code,
        )
        payload = read_descriptor(descriptor)
        after_opened = os.fstat(descriptor)
        after_named = os.lstat(path)
        require(has_exact_path_spelling(path), code)
        identity = before_opened.st_dev, before_opened.st_ino
        require(
            stat.S_ISREG(after_opened.st_mode)
            and stat.S_ISREG(after_named.st_mode)
            and after_opened.st_nlink == 1
            and after_named.st_nlink == 1
            and (after_opened.st_dev, after_opened.st_ino) == identity
            and (after_named.st_dev, after_named.st_ino) == identity,
            code,
        )
        return payload, identity
    except LocalControlledTrustError:
        raise
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    finally:
        os.close(descriptor)


def named_regular_identity(path: Path, code: str) -> FileIdentity:
    try:
        value = os.lstat(path)
    except OSError as error:
        raise LocalControlledTrustError(code) from error
    require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, code)
    return value.st_dev, value.st_ino


def read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def open_unique_lock(lock_path: Path) -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise LocalControlledTrustError("unsafe-replay-lock-path") from error
    try:
        verify_unique_lock(descriptor, lock_path)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def verify_unique_lock(descriptor: int, lock_path: Path) -> None:
    try:
        opened = os.fstat(descriptor)
        named = os.lstat(lock_path)
    except OSError as error:
        raise LocalControlledTrustError("unsafe-replay-lock-path") from error
    require(
        has_exact_path_spelling(lock_path)
        and is_normalized_path(str(lock_path))
        and stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(named.st_mode)
        and opened.st_nlink == 1
        and named.st_nlink == 1
        and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino),
        "unsafe-replay-lock-path",
    )


def is_exact_owned_path(value: object) -> bool:
    if type(value) is not str or not is_normalized_path(value):
        return False
    path = Path(value)
    if not path.is_absolute() or not has_exact_path_spelling(path):
        return False
    try:
        resolved = path.resolve(strict=True)
        value_stat = os.lstat(path)
    except (OSError, RuntimeError):
        return False
    if resolved != path:
        return False
    if stat.S_ISREG(value_stat.st_mode):
        return value_stat.st_nlink == 1
    return stat.S_ISDIR(value_stat.st_mode)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_normalized_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and ".." not in path.parts and str(path) == value


def resolve_strict(path: Path, code: str) -> Path:
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise LocalControlledTrustError(code) from error


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LocalControlledTrustError(code)
