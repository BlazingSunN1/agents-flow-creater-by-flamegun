from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import secrets
from pathlib import Path

from implementation_agent_validation import HostAttestationVerifier
from project_record_authorization import (
    AUTHORIZATION_MODES,
    DELIVERY_FIRST_MODE,
    STRICT_SECURITY_MODE,
    authorize_project_record_write,
    binding_is_current,
)


MISSING_SHA = "missing"


def update_record(
    target: Path,
    *,
    project_root: Path,
    content: bytes,
    expected_sha256: str,
    module_key: str,
    agent_id: str,
    run_id: str,
    agents_path: Path,
    lease_path: Path,
    lease_sha256: str,
    authorization_mode: str = DELIVERY_FIRST_MODE,
) -> str:
    return _update_record_impl(
        target, project_root=project_root, content=content,
        expected_sha256=expected_sha256, module_key=module_key,
        agent_id=agent_id, run_id=run_id, agents_path=agents_path,
        lease_path=lease_path, lease_sha256=lease_sha256, verifier=None,
        authorization_mode=authorization_mode,
    )


def _test_only_update_record(
    target: Path, *, project_root: Path, content: bytes, expected_sha256: str,
    module_key: str, agent_id: str, run_id: str, agents_path: Path,
    lease_path: Path, lease_sha256: str,
    _test_only_host_attestation_verifier: HostAttestationVerifier,
    authorization_mode: str = STRICT_SECURITY_MODE,
) -> str:
    return _update_record_impl(
        target, project_root=project_root, content=content,
        expected_sha256=expected_sha256, module_key=module_key,
        agent_id=agent_id, run_id=run_id, agents_path=agents_path,
        lease_path=lease_path, lease_sha256=lease_sha256,
        verifier=_test_only_host_attestation_verifier,
        authorization_mode=authorization_mode,
    )


def _update_record_impl(
    target: Path, *, project_root: Path, content: bytes, expected_sha256: str,
    module_key: str, agent_id: str, run_id: str, agents_path: Path,
    lease_path: Path, lease_sha256: str, verifier: HostAttestationVerifier | None,
    authorization_mode: str,
) -> str:
    root = project_root.resolve()
    expected_root = os.stat(root, follow_symlinks=False)
    _resolve_target(target, root)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (expected_root.st_dev, expected_root.st_ino):
            raise RuntimeError("project-root-changed")
        authority_fd = _open_lock_at(root_fd, ".project-record-authority.lock")
        with os.fdopen(authority_fd, "a+b", closefd=True) as authority_lock:
            fcntl.flock(authority_lock.fileno(), fcntl.LOCK_EX)
            binding = authorize_project_record_write(
                root=root, target=target, module_key=module_key,
                agent_id=agent_id, run_id=run_id, agents_path=agents_path,
                lease_path=lease_path, lease_sha256=lease_sha256,
                verifier=verifier, authorization_mode=authorization_mode,
            )
            return _write_bound_record(
                root, root_fd, target, content, expected_sha256, binding,
            )
    finally:
        os.close(root_fd)


def _write_bound_record(
    root: Path, root_fd: int, target: Path, content: bytes,
    expected_sha256: str, binding: object,
) -> str:
    parent_fd = _open_parent_dir(root_fd, target.parent.parts)
    try:
        lock_fd = _open_lock_at(parent_fd, f".{target.name}.lock")
        with os.fdopen(lock_fd, "a+b", closefd=True) as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if not binding_is_current(root, binding):
                raise RuntimeError("ownership-or-lease-drift")
            current_sha, mode = _read_current(parent_fd, target.name)
            if current_sha != expected_sha256.casefold():
                raise RuntimeError(f"stale-write expected={expected_sha256} actual={current_sha}")
            return _atomic_replace_at(parent_fd, target.name, content, mode)
    finally:
        os.close(parent_fd)


def _open_lock_at(directory_fd: int, name: str) -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    try:
        return os.open(name, flags, 0o600, dir_fd=directory_fd)
    except FileNotFoundError:
        return os.open(name, flags, 0o600, dir_fd=directory_fd)


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
    parser = argparse.ArgumentParser(description="使用模块租约、所有权、文件锁和 CAS 更新项目状态记录")
    parser.add_argument("target", type=Path, help="相对 project-root 的目标路径")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--content-file", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True, help="当前文件 SHA-256；新文件使用 missing")
    parser.add_argument("--module-key", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agents-path", type=Path, default=Path("AGENTS.md"))
    parser.add_argument("--lease-path", type=Path, required=True)
    parser.add_argument("--lease-sha256", required=True)
    parser.add_argument(
        "--authorization-mode", choices=AUTHORIZATION_MODES,
        default=DELIVERY_FIRST_MODE,
        help="默认本地协调优先；高风险或合规场景显式选择 strict-security",
    )
    arguments = parser.parse_args()
    try:
        new_sha = update_record(
            arguments.target,
            project_root=arguments.project_root,
            content=arguments.content_file.read_bytes(),
            expected_sha256=arguments.expected_sha256,
            module_key=arguments.module_key,
            agent_id=arguments.agent_id,
            run_id=arguments.run_id,
            agents_path=arguments.agents_path,
            lease_path=arguments.lease_path,
            lease_sha256=arguments.lease_sha256,
            authorization_mode=arguments.authorization_mode,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR atomic-record-update {error}")
        return 1
    assurance = (
        "host-attested"
        if arguments.authorization_mode == STRICT_SECURITY_MODE
        else "local-coordination-not-security-attested"
    )
    print(f"updated={arguments.target} sha256={new_sha} assurance={assurance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
