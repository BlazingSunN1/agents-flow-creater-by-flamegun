from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import secrets
from pathlib import Path


MISSING_SHA = "missing"


def update_record(
    target: Path,
    *,
    project_root: Path,
    content: bytes,
    expected_sha256: str,
) -> str:
    root = project_root.resolve()
    expected_root = os.stat(root, follow_symlinks=False)
    _resolve_target(target, root)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened_root = os.fstat(root_fd)
    if (opened_root.st_dev, opened_root.st_ino) != (expected_root.st_dev, expected_root.st_ino):
        os.close(root_fd)
        raise RuntimeError("project-root-changed")
    parent_fd = _open_parent_dir(root_fd, target.parent.parts)
    try:
        lock_fd = os.open(f".{target.name}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        with os.fdopen(lock_fd, "a+b", closefd=True) as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            current_sha, mode = _read_current(parent_fd, target.name)
            if current_sha != expected_sha256.casefold():
                raise RuntimeError(f"stale-write expected={expected_sha256} actual={current_sha}")
            return _atomic_replace_at(parent_fd, target.name, content, mode)
    finally:
        os.close(parent_fd)
        os.close(root_fd)


def _resolve_target(target: Path, root: Path) -> Path:
    if target.is_absolute() or ".." in target.parts or not target.parts:
        raise ValueError("target 必须是项目内相对路径")
    resolved = (root / target).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("target 越出项目根") from error
    return resolved


def _open_parent_dir(root_fd: int, parts: tuple[str, ...]) -> int:
    current = os.dup(root_fd)
    try:
        for part in parts:
            if part in {"", "."}:
                continue
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=current)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _read_current(parent_fd: int, name: str) -> tuple[str, int | None]:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError:
        return MISSING_SHA, None
    with os.fdopen(fd, "rb") as current:
        payload = current.read()
        return hashlib.sha256(payload).hexdigest(), os.fstat(current.fileno()).st_mode & 0o777


def _atomic_replace_at(parent_fd: int, name: str, content: bytes, mode: int | None) -> str:
    temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
    fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode or 0o600, dir_fd=parent_fd)
    try:
        with os.fdopen(fd, "wb", closefd=True) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    except Exception:
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        raise
    return hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="使用文件锁、期望 SHA-256 和原子替换更新项目状态记录")
    parser.add_argument("target", type=Path, help="相对 project-root 的目标路径")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--content-file", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True, help="当前文件 SHA-256；新文件使用 missing")
    arguments = parser.parse_args()
    try:
        new_sha = update_record(
            arguments.target,
            project_root=arguments.project_root,
            content=arguments.content_file.read_bytes(),
            expected_sha256=arguments.expected_sha256,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR atomic-record-update {error}")
        return 1
    print(f"updated={arguments.target} sha256={new_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
