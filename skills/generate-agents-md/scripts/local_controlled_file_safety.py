from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Callable


def has_exact_path_spelling(path: Path) -> bool:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        try:
            names = {entry.name for entry in os.scandir(current)}
        except OSError:
            return False
        if component not in names:
            return False
        current /= component
    return True


def fsync_directory(path: Path, expected_identity: tuple[int, int]) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not (
            stat.S_ISDIR(opened.st_mode)
            and (opened.st_dev, opened.st_ino) == expected_identity
        ):
            raise OSError("unsafe-directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def directory_identity(path: Path) -> tuple[int, int]:
    try:
        if (
            not has_exact_path_spelling(path)
            or path.resolve(strict=True) != path
            or path.is_symlink()
        ):
            raise OSError("unsafe-directory")
        value = os.stat(path, follow_symlinks=False)
    except (OSError, RuntimeError) as error:
        raise OSError("unsafe-directory") from error
    if not stat.S_ISDIR(value.st_mode):
        raise OSError("unsafe-directory")
    return value.st_dev, value.st_ino


def atomic_replace_text(
    path: Path, payload: str, verify_parent: Callable[[], None],
    expected_parent_identity: tuple[int, int],
    verify_target_before_replace: Callable[[], None] | None = None,
) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        verify_parent()
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        verify_parent()
        if verify_target_before_replace is not None:
            verify_target_before_replace()
        os.replace(temporary, path)
        verify_parent()
        fsync_directory(path.parent, expected_parent_identity)
        verify_parent()
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
